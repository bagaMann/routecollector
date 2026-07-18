"""
HTTP text domain source plugin.
"""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from routecollector.sources.base import (
    DomainSource,
    DomainSourceError,
    DomainSourceRequest,
    DomainSourceResult,
)


DEFAULT_TIMEOUT = 20.0
DEFAULT_USER_AGENT = "RouteCollector/1.2"


@dataclass(slots=True, frozen=True)
class HttpTextOptions:
    """Validated HTTP text source options."""

    url: str
    timeout: float
    user_agent: str
    encoding: str


class HttpTextSource(DomainSource):
    """
    Load domains from a plain-text HTTP or HTTPS resource.

    Supported line formats include:

    example.com
    domain:example.com
    full:www.example.com
    *.example.com
    0.0.0.0 example.com
    127.0.0.1 example.com another.example.com
    """

    @property
    def name(self) -> str:
        """Return unique source name."""

        return "http-text"

    def load(
        self,
        request: DomainSourceRequest,
    ) -> DomainSourceResult:
        """Download, parse and normalize one text resource."""

        options = self._parse_options(request)
        content = self._download(options)

        parsed_values: list[str] = []

        for raw_line in content.splitlines():
            parsed_values.extend(
                self._parse_line(raw_line)
            )

        normalized_domains = self.normalize_domains(
            parsed_values
        )

        return DomainSourceResult(
            source_name=self.name,
            service_name=request.service_name,
            domains=normalized_domains,
            metadata={
                "url": options.url,
                "input_count": len(parsed_values),
                "domain_count": len(normalized_domains),
                "encoding": options.encoding,
            },
        )

    @staticmethod
    def _parse_line(raw_line: str) -> list[str]:
        """Extract possible domain values from one text line."""

        value = raw_line.split("#", 1)[0].strip()

        if not value:
            return []

        tokens = value.split()

        if not tokens:
            return []

        if HttpTextSource._is_ip_address(tokens[0]):
            return tokens[1:]

        return [tokens[0]]

    @staticmethod
    def _is_ip_address(value: str) -> bool:
        """Return whether value is an IPv4 or IPv6 address."""

        try:
            ip_address(value)
        except ValueError:
            return False

        return True

    @staticmethod
    def _download(options: HttpTextOptions) -> str:
        """Download and decode the configured text resource."""

        request = Request(
            options.url,
            headers={
                "User-Agent": options.user_agent,
                "Accept": "text/plain, */*;q=0.1",
            },
        )

        try:
            with urlopen(
                request,
                timeout=options.timeout,
            ) as response:
                raw_content = response.read()
        except HTTPError as exc:
            raise DomainSourceError(
                "Unable to download http-text source "
                f"'{options.url}': HTTP {exc.code}"
            ) from exc
        except URLError as exc:
            raise DomainSourceError(
                "Unable to download http-text source "
                f"'{options.url}': {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise DomainSourceError(
                "Timed out while downloading http-text "
                f"source: {options.url}"
            ) from exc

        try:
            return raw_content.decode(options.encoding)
        except (LookupError, UnicodeDecodeError) as exc:
            raise DomainSourceError(
                "Unable to decode http-text source "
                f"'{options.url}' using {options.encoding}"
            ) from exc

    @staticmethod
    def _parse_options(
        request: DomainSourceRequest,
    ) -> HttpTextOptions:
        """Validate and normalize source options."""

        raw_options = request.source_options

        url = str(
            raw_options.get("url", "")
        ).strip()

        if not url:
            raise DomainSourceError(
                "http-text source option 'url' cannot be empty"
            )

        if not url.startswith(
            ("http://", "https://")
        ):
            raise DomainSourceError(
                "http-text source URL must use HTTP or HTTPS"
            )

        try:
            timeout = float(
                raw_options.get(
                    "timeout",
                    DEFAULT_TIMEOUT,
                )
            )
        except (TypeError, ValueError) as exc:
            raise DomainSourceError(
                "http-text timeout must be numeric"
            ) from exc

        if timeout <= 0:
            raise DomainSourceError(
                "http-text timeout must be greater than zero"
            )

        user_agent = str(
            raw_options.get(
                "user_agent",
                DEFAULT_USER_AGENT,
            )
        ).strip()

        if not user_agent:
            raise DomainSourceError(
                "http-text user_agent cannot be empty"
            )

        encoding = str(
            raw_options.get(
                "encoding",
                "utf-8",
            )
        ).strip()

        if not encoding:
            raise DomainSourceError(
                "http-text encoding cannot be empty"
            )

        return HttpTextOptions(
            url=url,
            timeout=timeout,
            user_agent=user_agent,
            encoding=encoding,
        )
