"""Read-only demo tools with server-side policy and scoped data access."""

import json
import re
import time
from collections import defaultdict
from importlib.resources import files

from enterprise_agent.audit import AuditLog
from enterprise_agent.policy import AccessDenied, Principal, authorize, permitted_regions
from enterprise_agent.retrieval import search


def load_data(name: str) -> list[dict]:
    return json.loads(files("enterprise_agent").joinpath("data", name + ".json").read_text())


class ToolService:
    def __init__(self, principal: Principal, audit: AuditLog, run_id: str):
        self.principal = principal
        self.audit = audit
        self.run_id = run_id
        self.documents = load_data("documents")
        self.orders = load_data("orders")
        self.customers = load_data("customers")

    def call(self, name: str, arguments: dict) -> dict:
        start = time.monotonic()
        status = "error"
        self.audit.record(
            principal=self.principal.name, tool=name, status="started", run_id=self.run_id
        )
        try:
            authorize(self.principal, name)
            handler = {
                "search_documents": self.search_documents,
                "revenue_summary": self.revenue_summary,
                "margin_summary": self.margin_summary,
                "customer_lookup": self.customer_lookup,
            }[name]
            result = handler(**arguments)
            status = "success"
            return result
        except AccessDenied:
            status = "denied"
            raise
        except (ValueError, TypeError):
            status = "invalid"
            raise
        finally:
            self.audit.record(
                principal=self.principal.name,
                tool=name,
                status=status,
                run_id=self.run_id,
                duration_ms=(time.monotonic() - start) * 1000,
            )

    def search_documents(self, query: str, limit: int = 3) -> dict:
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 2000:
            raise ValueError("query must contain 1 to 2000 characters")
        if type(limit) is not int or not 1 <= limit <= 5:
            raise ValueError("limit must be an integer from 1 to 5")
        visible = [d for d in self.documents if self.principal.role in d["roles"]]
        return {
            "method": "tf-idf cosine",
            "synthetic": True,
            "documents": search(visible, query, limit),
        }

    def _orders(self, region: str | None, month: str | None):
        regions = permitted_regions(self.principal, region)
        if month is not None and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            raise ValueError("month must be YYYY-MM")
        rows = [
            o
            for o in self.orders
            if o["region"] in regions and (month is None or o["month"] == month)
        ]
        return rows, sorted(regions)

    def revenue_summary(self, region: str | None = None, month: str | None = None) -> dict:
        rows, regions = self._orders(region, month)
        by_region = defaultdict(int)
        for row in rows:
            by_region[row["region"]] += row["revenue_cents"]
        return {
            "currency": "USD",
            "revenue_cents": sum(by_region.values()),
            "order_count": len(rows),
            "by_region_cents": dict(sorted(by_region.items())),
            "scope": {"regions": regions, "month": month, "available_period": "2026-Q1"},
            "source": "demo://orders",
            "synthetic": True,
        }

    def margin_summary(self, region: str | None = None, month: str | None = None) -> dict:
        rows, regions = self._orders(region, month)
        revenue = sum(o["revenue_cents"] for o in rows)
        cost = sum(o["cost_cents"] for o in rows)
        return {
            "currency": "USD",
            "revenue_cents": revenue,
            "cost_cents": cost,
            "gross_margin_cents": revenue - cost,
            "gross_margin_percent": round((revenue - cost) / revenue * 100, 2) if revenue else None,
            "scope": {"regions": regions, "month": month},
            "source": "demo://orders",
            "synthetic": True,
        }

    def customer_lookup(self, customer_id: str) -> dict:
        # Nonexistent and out-of-scope customers have indistinguishable responses.
        for customer in self.customers:
            if customer["id"] == customer_id and customer["region"] in self.principal.regions:
                return {
                    **customer,
                    "email": "[REDACTED]",
                    "synthetic": True,
                    "source": "demo://customers/" + customer_id,
                }
        raise AccessDenied("Customer unavailable for this principal")
