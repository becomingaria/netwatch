"""Domain blocklists loaded from <data>/blocklists/*.txt.

Accepts plain "domain" lines and hosts-file lines ("0.0.0.0 domain"), so
lists such as URLhaus or StevenBlack's hosts can be dropped in unchanged.
"""

import logging
from pathlib import Path

log = logging.getLogger(__name__)

IGNORED_HOSTS = {"localhost", "localhost.localdomain", "local", "broadcasthost", "0.0.0.0"}


class Blocklist:
    def __init__(self, directory: Path):
        self.directory = directory
        self.domains: set[str] = set()
        self.reload()

    def reload(self) -> None:
        domains: set[str] = set()
        self.directory.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.directory.glob("*.txt")):
            for line in path.read_text(errors="ignore").splitlines():
                line = line.split("#", 1)[0].strip().lower()
                if not line:
                    continue
                domain = line.split()[-1].rstrip(".")
                if domain not in IGNORED_HOSTS:
                    domains.add(domain)
        self.domains = domains
        log.info("blocklist: %d domains from %s", len(domains), self.directory)

    def match(self, domain: str) -> str | None:
        """Return the listed entry matching domain or one of its parents."""
        parts = domain.lower().rstrip(".").split(".")
        for i in range(len(parts) - 1):
            candidate = ".".join(parts[i:])
            if candidate in self.domains:
                return candidate
        return None
