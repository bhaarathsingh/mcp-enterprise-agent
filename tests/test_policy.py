import json

import pytest

from enterprise_agent.audit import AuditLog
from enterprise_agent.policy import AccessDenied, principal_named
from enterprise_agent.service import ToolService


@pytest.fixture
def service(tmp_path):
    def create(name="analyst-east"):
        return ToolService(principal_named(name), AuditLog(tmp_path / "audit.jsonl"), "test-run")

    return create


def test_revenue_is_region_scoped_before_aggregation(service):
    result = service().call("revenue_summary", {})
    assert result["revenue_cents"] == 400000
    assert result["order_count"] == 4
    assert result["by_region_cents"] == {"East": 400000}


def test_finance_can_aggregate_all_regions(service):
    result = service("finance").call("margin_summary", {})
    assert result["revenue_cents"] == 1000000
    assert result["gross_margin_cents"] == 420000
    assert result["gross_margin_percent"] == 42


def test_month_filter_and_empty_period(service):
    assert service().call("revenue_summary", {"month": "2026-02"})["revenue_cents"] == 150000
    assert (
        service("finance").call("margin_summary", {"month": "2027-01"})["gross_margin_percent"]
        is None
    )


@pytest.mark.parametrize(
    "principal,tool,args",
    [
        ("analyst-east", "margin_summary", {}),
        ("support-east", "revenue_summary", {}),
        ("finance", "customer_lookup", {"customer_id": "C-001"}),
        ("analyst-east", "revenue_summary", {"region": "West"}),
        ("support-east", "customer_lookup", {"customer_id": "C-002"}),
        ("support-east", "customer_lookup", {"customer_id": "C-999"}),
        ("finance", "execute_sql", {"query": "DROP TABLE orders"}),
    ],
)
def test_denied_calls_are_enforced_and_audited(service, tmp_path, principal, tool, args):
    with pytest.raises(AccessDenied):
        service(principal).call(tool, args)
    events = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert events[-1]["status"] == "denied"
    assert events[-1]["run_id"] == "test-run"


def test_customer_contact_is_masked(service):
    result = service("support-east").call("customer_lookup", {"customer_id": "C-001"})
    assert result["email"] == "[REDACTED]"
    assert "@" not in json.dumps(result)


def test_restricted_documents_cannot_affect_retrieval(service):
    analyst = service()
    before = analyst.call("search_documents", {"query": "margin refund", "limit": 5})
    analyst.documents += [
        {"id": "secret", "title": "refund", "text": "refund " * 1000, "roles": ["finance"]}
    ]
    assert analyst.call("search_documents", {"query": "margin refund", "limit": 5}) == before
    assert "finance-margin" not in json.dumps(before)
    assert "policy-returns" in json.dumps(before)


def test_query_never_enters_audit_log(service, tmp_path):
    service().call("search_documents", {"query": "private value secret_12345"})
    assert "secret_12345" not in (tmp_path / "audit.jsonl").read_text()


@pytest.mark.parametrize(
    "tool,args",
    [
        ("search_documents", {"query": ""}),
        ("search_documents", {"query": "refund", "limit": 6}),
        ("search_documents", {"query": "refund", "limit": True}),
        ("revenue_summary", {"month": "2026-13"}),
        ("revenue_summary", {"month": "2026-01'; DELETE"}),
    ],
)
def test_invalid_arguments(service, tool, args):
    with pytest.raises(ValueError):
        service().call(tool, args)


def test_unknown_principal_fails_closed():
    with pytest.raises(ValueError):
        principal_named("admin")


def test_audit_failure_prevents_tool_execution(service, monkeypatch):
    tool_service = service()

    def fail(**kwargs):
        raise OSError("Disk full")

    monkeypatch.setattr(tool_service.audit, "record", fail)
    with pytest.raises(OSError):
        tool_service.call("revenue_summary", {})
