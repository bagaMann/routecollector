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
from routecollector.dynamic.domain_matcher import (
    DomainMatch,
    DomainMatcher,
    DomainMatchRule,
)
from routecollector.dynamic.observation_store import (
    DynamicObservationStore,
    DynamicStoreResult,
)

__all__ = [
    "DnsAnswerRecord",
    "DomainMatch",
    "DomainMatcher",
    "DomainMatchRule",
    "DynamicConfigError",
    "DynamicConfigLoader",
    "DynamicDnsObservation",
    "DynamicObservationStore",
    "DynamicStoreResult",
    "build_dynamic_observations",
]
