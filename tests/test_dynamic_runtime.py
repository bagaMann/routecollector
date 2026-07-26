"""
Tests for dynamic runtime assembly and lifecycle.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import routecollector.dynamic.runtime as runtime_module
from routecollector.dynamic import (
    DnsProxyConfig,
    DynamicRuntime,
    DynamicRuntimeConfig,
)


class FakeServer:
    def __init__(
        self,
        **kwargs: Any,
    ) -> None:
        self.kwargs = kwargs
        self.running = False
        self.start_calls = 0
        self.stop_calls = 0

    def start(self) -> None:
        self.start_calls += 1
        self.running = True

    def stop(self) -> None:
        self.stop_calls += 1
        self.running = False


def make_app() -> SimpleNamespace:
    logger = logging.getLogger(
        "test-dynamic-runtime"
    )
    logger.handlers.clear()
    logger.addHandler(
        logging.NullHandler()
    )

    return SimpleNamespace(
        repository=object(),
        logger=logger,
    )


def patch_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matcher = object()
    store = object()
    publisher = object()
    processor = object()
    resolver = object()

    monkeypatch.setattr(
        runtime_module.DynamicConfigLoader,
        "build_matcher",
        lambda self: matcher,
    )
    monkeypatch.setattr(
        runtime_module,
        "DynamicObservationStore",
        lambda *args, **kwargs: store,
    )
    monkeypatch.setattr(
        runtime_module,
        "DynamicPublisher",
        lambda *args, **kwargs: publisher,
    )
    monkeypatch.setattr(
        runtime_module,
        "DynamicDnsProcessor",
        lambda **kwargs: processor,
    )
    monkeypatch.setattr(
        runtime_module,
        "ForwardingDynamicResolver",
        lambda **kwargs: resolver,
    )


def test_runtime_assembles_and_controls_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_components(monkeypatch)
    created: list[FakeServer] = []

    def server_factory(
        **kwargs: Any,
    ) -> FakeServer:
        server = FakeServer(**kwargs)
        created.append(server)
        return server

    runtime = DynamicRuntime(
        app=make_app(),  # type: ignore[arg-type]
        config=DynamicRuntimeConfig(
            dns_proxy=DnsProxyConfig(),
        ),
        server_factory=server_factory,  # type: ignore[arg-type]
    )

    assert runtime.running is False

    runtime.start()

    assert runtime.running is True
    assert created[0].start_calls == 1

    runtime.stop()

    assert runtime.running is False
    assert created[0].stop_calls == 1


def test_runtime_requires_repository() -> None:
    with pytest.raises(
        RuntimeError,
        match="repository",
    ):
        DynamicRuntime(
            app=SimpleNamespace(
                repository=None,
                logger=logging.getLogger(
                    "missing-repository"
                ),
            ),  # type: ignore[arg-type]
            config=DynamicRuntimeConfig(
                dns_proxy=DnsProxyConfig(),
            ),
        )


def test_runtime_requires_logger() -> None:
    with pytest.raises(
        RuntimeError,
        match="logger",
    ):
        DynamicRuntime(
            app=SimpleNamespace(
                repository=object(),
                logger=None,
            ),  # type: ignore[arg-type]
            config=DynamicRuntimeConfig(
                dns_proxy=DnsProxyConfig(),
            ),
        )


def test_runtime_config_rejects_confidence() -> None:
    with pytest.raises(
        ValueError,
        match="confidence",
    ):
        DynamicRuntimeConfig(
            dns_proxy=DnsProxyConfig(),
            dynamic_confidence=0,
        )


def test_runtime_config_preserves_paths() -> None:
    config = DynamicRuntimeConfig(
        dns_proxy=DnsProxyConfig(),
        services_dir=Path(
            "custom/services"
        ),
        generated_config=Path(
            "custom/generated.conf"
        ),
    )

    assert config.services_dir == Path(
        "custom/services"
    )
    assert config.generated_config == Path(
        "custom/generated.conf"
    )
