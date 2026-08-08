"""
Assemble and run the dynamic RouteCollector DNS pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import signal
from threading import Event
from types import FrameType
from typing import Callable

from routecollector.core.application import Application
from routecollector.dynamic.config_loader import DynamicConfigLoader
from routecollector.dynamic.dns_proxy import (
    DnsProxyConfig,
    DnsProxyEvent,
    DynamicDnsProxyServer,
    ForwardingDynamicResolver,
)
from routecollector.dynamic.lease import (
    DynamicLeaseManager,
    DynamicRouteLeaseStore,
)
from routecollector.dynamic.observation_store import DynamicObservationStore
from routecollector.dynamic.processor import DynamicDnsProcessor
from routecollector.dynamic.publish_queue import DynamicPublishQueue
from routecollector.dynamic.publisher import DynamicPublisher
from routecollector.dynamic.route_cache import DynamicRouteCache
from routecollector.planner.planner import RoutePlanner


@dataclass(slots=True, frozen=True)
class DynamicRuntimeConfig:
    dns_proxy: DnsProxyConfig
    services_dir: Path = Path("config/services")
    generated_config: Path = Path("bird/routecollector.conf")
    installed_config: Path = Path(
        "/etc/bird/routecollector.conf"
    )
    main_bird_config: Path = Path("/etc/bird/bird.conf")
    lease_state: Path = Path(
        "state/dynamic-route-leases.json"
    )
    dynamic_confidence: int = 100
    min_confidence_ipv4: int = 60
    min_confidence_ipv6: int = 60
    dynamic_min_confidence_ipv4: int = 25
    dynamic_min_confidence_ipv6: int = 25
    dynamic_min_source_trust: int = 50
    dynamic_lease_seconds: int = 86400
    dynamic_lease_check_seconds: float = 60.0
    max_age_days: int = 30
    enable_ipv6: bool = False
    global_only: bool = True
    debounce_seconds: float = 0.25
    publish_wait_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if self.dynamic_confidence <= 0:
            raise ValueError(
                "Dynamic confidence must be positive"
            )

        for name, value in (
            (
                "Dynamic IPv4 confidence",
                self.dynamic_min_confidence_ipv4,
            ),
            (
                "Dynamic IPv6 confidence",
                self.dynamic_min_confidence_ipv6,
            ),
            (
                "Dynamic source trust",
                self.dynamic_min_source_trust,
            ),
        ):
            if not 0 <= value <= 100:
                 raise ValueError(
                    f"{name} must be between 0 and 100"
                 )

        if self.dynamic_lease_seconds <= 0:
            raise ValueError(
                "Dynamic route lease must be greater than zero"
            )

        if self.dynamic_lease_check_seconds <= 0:
            raise ValueError(
                "Dynamic lease check interval must be positive"
            )


class DynamicRuntime:
    def __init__(
        self,
        *,
        app: Application,
        config: DynamicRuntimeConfig,
        server_factory: Callable[..., DynamicDnsProxyServer] = (
            DynamicDnsProxyServer
        ),
    ) -> None:
        if app.repository is None:
            raise RuntimeError(
                "Application repository is not initialized"
            )
        if app.logger is None:
            raise RuntimeError(
                "Application logger is not initialized"
            )

        self._config = config
        self._logger = app.logger
        self._stopped = Event()

        matcher = DynamicConfigLoader(
            config.services_dir
        ).build_matcher()

        store = DynamicObservationStore(
            app.repository,
            confidence=config.dynamic_confidence,
        )

        planner = RoutePlanner(
            repository=app.repository,
            min_confidence_ipv4=config.min_confidence_ipv4,
            min_confidence_ipv6=config.min_confidence_ipv6,
            max_age_days=config.max_age_days,
            enable_ipv6=config.enable_ipv6,
        )

        self._lease_store = DynamicRouteLeaseStore(
            config.lease_state,
            lease_seconds=config.dynamic_lease_seconds,
        )

        route_cache = DynamicRouteCache(
            route.prefix
            for route in planner.build_plan()
        )
        route_cache.add(
            self._lease_store.active_prefixes()
        )

        publisher = DynamicPublisher(
            app.repository,
            generated_config=config.generated_config,
            installed_config=config.installed_config,
            main_bird_config=config.main_bird_config,
            min_confidence_ipv4=config.min_confidence_ipv4,
            min_confidence_ipv6=config.min_confidence_ipv6,
            dynamic_min_confidence_ipv4=(
                config.dynamic_min_confidence_ipv4
            ),
            dynamic_min_confidence_ipv6=(
                config.dynamic_min_confidence_ipv6
            ),
            dynamic_min_source_trust=(
                config.dynamic_min_source_trust
            ),
            max_age_days=config.max_age_days,
            enable_ipv6=config.enable_ipv6,
        )

        self._publish_queue = DynamicPublishQueue(
            publisher=publisher,
            route_cache=route_cache,
            lease_store=self._lease_store,
            debounce_seconds=config.debounce_seconds,
            wait_timeout_seconds=(
                config.publish_wait_timeout_seconds
            ),
        )

        self._lease_manager = DynamicLeaseManager(
            store=self._lease_store,
            publisher=publisher,
            route_cache=route_cache,
            interval_seconds=(
                config.dynamic_lease_check_seconds
            ),
        )

        processor = DynamicDnsProcessor(
            matcher=matcher,
            store=store,
            publish_queue=self._publish_queue,
            enable_ipv6=config.enable_ipv6,
            global_only=config.global_only,
        )

        resolver = ForwardingDynamicResolver(
            processor=processor,
            config=config.dns_proxy,
            event_callback=self._handle_event,
        )

        self._server = server_factory(
            resolver=resolver,
            config=config.dns_proxy,
        )

    @property
    def running(self) -> bool:
        return self._server.running

    def start(self) -> None:
        self._lease_manager.start()
        self._server.start()

        self._logger.info(
            "Dynamic DNS proxy started on %s:%s; "
            "upstream=%s:%s lease=%ss",
            self._config.dns_proxy.listen_address,
            self._config.dns_proxy.listen_port,
            self._config.dns_proxy.upstream_address,
            self._config.dns_proxy.upstream_port,
            self._config.dynamic_lease_seconds,
        )

    def stop(self) -> None:
        if self._server.running:
            self._server.stop()

        if self._publish_queue.running:
            self._publish_queue.stop()

        if self._lease_manager.running:
            self._lease_manager.stop()

        self._stopped.set()
        self._logger.info(
            "Dynamic DNS proxy stopped"
        )

    def run(self) -> None:
        previous_handlers = self._install_signal_handlers()

        try:
            self.start()

            while not self._stopped.wait(1.0):
                if not self._server.running:
                    raise RuntimeError(
                        "Dynamic DNS proxy stopped unexpectedly"
                    )
        except KeyboardInterrupt:
            self._logger.info(
                "Dynamic DNS proxy interrupted"
            )
        finally:
            self.stop()
            self._restore_signal_handlers(
                previous_handlers
            )

    def _handle_event(
        self,
        event: DnsProxyEvent,
    ) -> None:
        if event.processing_error is not None:
            self._logger.error(
                "Dynamic DNS processing failed: "
                "query=%s protocol=%s error=%s",
                event.query_name,
                event.protocol,
                event.processing_error,
            )
            return

        result = event.process_result

        if result is None or not result.matched:
            return

        publish_result = result.publish_result

        self._logger.info(
            "Dynamic DNS processed: query=%s "
            "records=%s observations=%s "
            "publication_required=%s routes=%s "
            "dynamic_published=%s dynamic_rejected=%s "
            "reloaded=%s protocol=%s",
            event.query_name,
            event.record_count,
            result.observations_built,
            result.publication_required,
            (
                publish_result.planned_routes
                if publish_result is not None
                else 0
            ),
            (
                len(
                    publish_result.dynamic_published_prefixes
                )
                if publish_result is not None
                else 0
            ),
            (
                len(
                    publish_result.dynamic_rejected_prefixes
                )
                if publish_result is not None
                else 0
            ),
            (
                publish_result.bird_reloaded
                if publish_result is not None
                else False
            ),
            event.protocol,
        )

    def _install_signal_handlers(
        self,
    ) -> dict[int, signal.Handlers]:
        handlers: dict[int, signal.Handlers] = {}

        for signum in (
            signal.SIGINT,
            signal.SIGTERM,
        ):
            handlers[signum] = signal.getsignal(signum)
            signal.signal(
                signum,
                self._signal_handler,
            )

        return handlers

    @staticmethod
    def _restore_signal_handlers(
        handlers: dict[int, signal.Handlers],
    ) -> None:
        for signum, handler in handlers.items():
            signal.signal(
                signum,
                handler,
            )

    def _signal_handler(
        self,
        signum: int,
        frame: FrameType | None,
    ) -> None:
        del frame
        self._logger.info(
            "Dynamic DNS proxy received signal %s",
            signum,
        )
        self._stopped.set()
