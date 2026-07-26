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

__all__ = [
    "DnsAnswerRecord",
    "DomainMatch",
    "DomainMatcher",
    "DomainMatchRule",
    "DynamicConfigError",
    "DynamicConfigLoader",
    "DynamicDnsObservation",
    "build_dynamic_observations",
]
