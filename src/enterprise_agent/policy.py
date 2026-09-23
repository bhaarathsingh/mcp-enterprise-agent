"""Demo identities are trusted process configuration, never tool arguments."""

from dataclasses import dataclass


class AccessDenied(Exception):
    """The current principal cannot access this tool or resource."""


@dataclass(frozen=True)
class Principal:
    name: str
    role: str
    regions: frozenset[str]


PRINCIPALS = {
    "analyst-east": Principal("analyst-east", "analyst", frozenset({"East"})),
    "support-east": Principal("support-east", "support", frozenset({"East"})),
    "finance": Principal("finance", "finance", frozenset({"East", "West"})),
}
TOOL_ROLES = {
    "search_documents": {"analyst", "support", "finance"},
    "revenue_summary": {"analyst", "finance"},
    "margin_summary": {"finance"},
    "customer_lookup": {"support"},
}


def principal_named(name: str) -> Principal:
    try:
        return PRINCIPALS[name]
    except KeyError:
        raise ValueError(f"Unknown demo principal: {name}") from None


def authorize(principal: Principal, tool: str) -> None:
    if principal.role not in TOOL_ROLES.get(tool, set()):
        raise AccessDenied("Tool access denied for this principal")


def permitted_regions(principal: Principal, requested: str | None) -> frozenset[str]:
    if requested is None:
        return principal.regions
    if requested not in principal.regions:
        raise AccessDenied("Region access denied for this principal")
    return frozenset({requested})
