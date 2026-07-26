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
from routecollector.dynamic.observation_store import (
    DynamicObservationStore,
    DynamicStoreResult,
)
from routecollector.dynamic.processor import (
    DynamicDnsProcessor,
    DynamicProcessResult,
)
from routecollector.dynamic.publisher import (
    DynamicPublishError,
    DynamicPublisher,
    DynamicPublishResult,
)
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
    "DynamicObservationStore",
    "DynamicProcessResult",
    "DynamicPublishError",
    "DynamicPublisher",
    "DynamicPublishResult",
    "DynamicRuntime",
    "DynamicRuntimeConfig",
    "DynamicStoreResult",
    "ForwardingDynamicResolver",
    "build_dynamic_observations",
]
