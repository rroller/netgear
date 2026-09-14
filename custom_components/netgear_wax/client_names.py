"""Resolve useful client labels without replacing names supplied by the AP."""


def normalize_mac(value: str) -> str:
    """Normalize MAC separators and casing for comparison and registry lookup."""
    compact = value.strip().lower().replace("-", "").replace(":", "").replace(".", "")
    if len(compact) == 12 and all(char in "0123456789abcdef" for char in compact):
        return ":".join(compact[index:index + 2] for index in range(0, 12, 2))
    return value.strip().lower()


def useful_name(value: str, mac_address: str) -> str:
    """Reject placeholders and a MAC masquerading as a hostname."""
    value = (value or "").strip()
    if value.casefold() in {"", "not applicable", "not applicabl", "unknown", "none", "null", "n/a", "-"}:
        return ""
    return "" if normalize_mac(value) == normalize_mac(mac_address) else value
