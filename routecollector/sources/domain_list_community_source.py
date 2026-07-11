"""
Domain source plugin for v2fly/domain-list-community.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from routecollector.sources.base import (
    DomainSource,
    DomainSourceError,
    DomainSourceRequest,
    DomainSourceResult,
)


DEFAULT_BASE_URL = (
    "https://raw.githubusercontent.com/"
    "v2fly/domain-list-community/master/data"
)


@dataclass(slots=True, frozen=True)
class DomainListCommunityOptions:
    """Resolved plugin options."""

    list_name: str
    base_url: str
    timeout: float
    max_depth: int


class DomainListCommunitySource(DomainSource):
    """Load domain lists from v2fly/domain-list-community."""

    @property
    def name(self) -> str:
        """Return unique source name."""

        return "domain-list-community"

    def load(
        self,
        request: DomainSourceRequest,
    ) -> DomainSourceResult:
        """Load one list and all recursively included lists."""

        options = self._parse_options(request)
        loaded_lists: set[str] = set()
        domains: set[str] = set()

        self._load_list(
            list_name=options.list_name,
            options=options,
            loaded_lists=loaded_lists,
            domains=domains,
            depth=0,
        )

        normalized_domains = self.normalize_domains(domains)

        return DomainSourceResult(
            source_name=self.name,
            service_name=request.service_name,
            domains=normalized_domains,
            metadata={
                "root_list": options.list_name,
                "loaded_lists": tuple(sorted(loaded_lists)),
                "list_count": len(loaded_lists),
                "domain_count": len(normalized_domains),
                "base_url": options.base_url,
            },
        )

    def _load_list(
        self,
        *,
        list_name: str,
        options: DomainListCommunityOptions,
        loaded_lists: set[str],
        domains: set[str],
        depth: int,
    ) -> None:
        """Load and parse one list recursively."""

        normalized_list_name = list_name.strip().lower()

        if not normalized_list_name:
            raise DomainSourceError(
                "domain-list-community list name cannot be empty"
            )

        if normalized_list_name in loaded_lists:
            return

        if depth > options.max_depth:
            raise DomainSourceError(
                "domain-list-community include depth exceeded "
                f"for list: {normalized_list_name}"
            )

        loaded_lists.add(normalized_list_name)

        content = self._download(
            list_name=normalized_list_name,
            base_url=options.base_url,
            timeout=options.timeout,
        )

        for raw_line in content.splitlines():
            value = self._strip_comment_and_attributes(raw_line)

            if not value:
                continue

            if value.startswith("include:"):
                included_list = value.removeprefix("include:").strip()

                if included_list:
                    self._load_list(
                        list_name=included_list,
                        options=options,
                        loaded_lists=loaded_lists,
                        domains=domains,
                        depth=depth + 1,
                    )

                continue

            domain = self.normalize_domain(value)

            if domain is not None:
                domains.add(domain)

    @staticmethod
    def _strip_comment_and_attributes(raw_line: str) -> str:
        """Remove comments and trailing @attributes from one line."""

        value = raw_line.split("#", 1)[0].strip()

        if not value:
            return ""

        tokens = value.split()

        if not tokens:
            return ""

        return tokens[0].strip().lower()

    @staticmethod
    def _download(
        *,
        list_name: str,
        base_url: str,
        timeout: float,
    ) -> str:
        """Download one raw list file."""

        url = f"{base_url.rstrip('/')}/{list_name}"

        try:
            with urlopen(url, timeout=timeout) as response:
                raw_content = response.read()
        except HTTPError as exc:
            raise DomainSourceError(
                "Unable to download domain-list-community list "
                f"'{list_name}': HTTP {exc.code}"
            ) from exc
        except URLError as exc:
            raise DomainSourceError(
                "Unable to download domain-list-community list "
                f"'{list_name}': {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise DomainSourceError(
                "Timed out while downloading domain-list-community "
                f"list: {list_name}"
            ) from exc

        try:
            return raw_content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DomainSourceError(
                "domain-list-community returned invalid UTF-8 "
                f"for list: {list_name}"
            ) from exc

    @staticmethod
    def _parse_options(
        request: DomainSourceRequest,
    ) -> DomainListCommunityOptions:
        """Validate and resolve source request options."""

        raw_options = request.source_options

        list_name = str(
            raw_options.get("list", request.service_name)
        ).strip()

        base_url = str(
            raw_options.get("base_url", DEFAULT_BASE_URL)
        ).strip()

        try:
            timeout = float(raw_options.get("timeout", 20.0))
        except (TypeError, ValueError) as exc:
            raise DomainSourceError(
                "domain-list-community timeout must be numeric"
            ) from exc

        try:
            max_depth = int(raw_options.get("max_depth", 10))
        except (TypeError, ValueError) as exc:
            raise DomainSourceError(
                "domain-list-community max_depth must be an integer"
            ) from exc

        if not list_name:
            raise DomainSourceError(
                "domain-list-community list name cannot be empty"
            )

        if not base_url:
            raise DomainSourceError(
                "domain-list-community base_url cannot be empty"
            )

        if timeout <= 0:
            raise DomainSourceError(
                "domain-list-community timeout must be greater than zero"
            )

        if max_depth < 0:
            raise DomainSourceError(
                "domain-list-community max_depth cannot be negative"
            )

        return DomainListCommunityOptions(
            list_name=list_name,
            base_url=base_url,
            timeout=timeout,
            max_depth=max_depth,
        )
