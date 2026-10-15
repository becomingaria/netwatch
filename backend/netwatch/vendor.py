"""MAC address -> manufacturer, using the OUI database bundled with scapy."""

from functools import lru_cache

from scapy.all import conf


def is_randomized(mac: str) -> bool:
    # Phones and laptops use "locally administered" random MACs for privacy.
    return bool(int(mac.split(":")[0], 16) & 0x02)


@lru_cache(maxsize=4096)
def lookup(mac: str) -> str | None:
    if is_randomized(mac):
        return None
    try:
        _, long_name = conf.manufdb.lookup(mac)
    except Exception:
        return None
    return None if not long_name or long_name.lower() == mac.lower() else long_name
