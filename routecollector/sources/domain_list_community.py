"""
v2fly/domain-list-community source support.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


DEFAULT_BASE_URL = (
    "https://raw.githubusercontent.com/v2fly/domain-list-community/master/data"
)


@dataclass(slots=True, frozen=True)
class DomainListEntry:
    """Parsed domain-list-community entry."""

    domain: str
    entry_type: str
    source: str


class DomainListCommunityError(RuntimeError):
    """Domain list community error."""


class DomainListCommunityClient:
    """Download files from domain-list-community."""

    def __init__(self, cache_dir: Path, base_url: str = DEFAULT_BASE_URL) -> None:
        self._cache_dir = cache_dir
        self._base_url = base_url.rstrip("/")

    def fetch(self, list_name: str) -> Path:
        """Download list file into cache and return cached path."""

        self._cache_dir.mkdir(parents=True, exist_ok=True)

        url = f"{self._base_url}/{list_name}"
        target = self._cache_dir / list_name

        try:
            with urlopen(url, timeout=20) as response:
                content = response.read()
        except URLError as exc:
            raise DomainListCommunityError(f"Failed to download {url}: {exc}") from exc

        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(content)
        tmp.replace(target)

        return target


class DomainListCommunityParser:
    """Parse domain-list-community files."""

    def parse_file(self, filename: Path, source_name: str) -> list[DomainListEntry]:
        """Parse list file."""

        entries: list[DomainListEntry] = []

        for raw_line in filename.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()

            if not line or line.startswith("#"):
                continue

            line = line.split("#", 1)[0].strip()
            line = line.split("@", 1)[0].strip()

            if not line:
                continue

            if line.startswith("include:"):
                continue

            if ":" in line:
                entry_type, domain = line.split(":", 1)
            else:
                entry_type = "domain"
                domain = line

            entry_type = entry_type.strip()
            domain = domain.strip()

            if entry_type not in {"domain", "full"}:
                continue

            if domain:
                entries.append(
                    DomainListEntry(
                        domain=domain,
                        entry_type=entry_type,
                        source=source_name,
                    )
                )

        return entries
