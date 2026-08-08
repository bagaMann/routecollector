"""Dynamic DNS observation support."""

from routecollector.dynamic.config_loader import (
    DynamicConfigError,
    DynamicConfigLoader,
)
from routecollector.dynamic.dns_observation import (
    DnsAnswerRecord,
    DynamicDnsObservation,
    build_dynamic_observations,
)
from routecollector.dynamic.dns_proxy import (
    DnsProxyConfig,
    DnsProxyError,
    DnsProxyEvent,
    DynamicDnsProxyServer,
    ForwardingDynamicResolver,
)
from routecollector.dynamic.domain_matcher import (
    DomainMatch,
    DomainMatcher,
    DomainMatchRule,
)
from routecollector.dynamic.fast_publish import (
    DynamicFastPublishPolicy,
    DynamicFastPublishResult,
)
from routecollector.dynamic.lease import (
    DynamicLeaseError,
    DynamicLeaseManager,
    DynamicRouteLease,
    DynamicRouteLeaseStore,
)
from routecollector.dynamic.observation_store import (
    DynamicObservationStore,
    DynamicStoreResult,
)
from routecollector.dynamic.processor import (
    DynamicDnsProcessor,
    DynamicProcessResult,
)
from routecollector.dynamic.publish_queue import (
    DynamicPublishQueue,
    DynamicPublishQueueError,
    DynamicQueueResult,
)
from routecollector.dynamic.publisher import (
    DynamicPublishError,
    DynamicPublisher,
    DynamicPublishResult,
)
from routecollector.dynamic.route_cache import DynamicRouteCache
from routecollector.dynamic.runtime import (
    DynamicRuntime,
    DynamicRuntimeConfig,
)

__all__ = [
    "DnsAnswerRecord",
    "DnsProxyConfig",
    "DnsProxyError",
    "DnsProxyEvent",
    "DomainMatch",
    "DomainMatcher",
    "DomainMatchRule",
    "DynamicConfigError",
    "DynamicConfigLoader",
    "DynamicDnsObservation",
    "DynamicDnsProcessor",
    "DynamicDnsProxyServer",
    "DynamicFastPublishPolicy",
    "DynamicFastPublishResult",
    "DynamicLeaseError",
    "DynamicLeaseManager",
    "DynamicObservationStore",
    "DynamicProcessResult",
    "DynamicPublishError",
    "DynamicPublishQueue",
    "DynamicPublishQueueError",
    "DynamicPublishResult",
    "DynamicPublisher",
    "DynamicQueueResult",
    "DynamicRouteCache",
    "DynamicRouteLease",
    "DynamicRouteLeaseStore",
    "DynamicRuntime",
    "DynamicRuntimeConfig",
    "DynamicStoreResult",
    "ForwardingDynamicResolver",
    "build_dynamic_observations",
]
