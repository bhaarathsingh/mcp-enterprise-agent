"""Deterministic demo planner. This is explicitly NOT a language model."""

import json
import re

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


class DemoPlanner:
    def bind_tools(self, _schemas):
        return self

    async def ainvoke(self, messages):
        results = [m for m in messages if isinstance(m, ToolMessage)]
        if not results:
            question = next(m.content for m in messages if isinstance(m, HumanMessage))
            text = question.lower()
            calls = [{"name": "search_documents", "args": {"query": question[:2000]}}]
            region = "West" if "west" in text else "East" if "east" in text else None
            month_match = re.search(r"\b2026-\d{2}\b", question)
            args = {"region": region, "month": month_match.group() if month_match else None}
            if any(word in text for word in ("revenue", "sales")):
                calls.append({"name": "revenue_summary", "args": args})
            if "margin" in text:
                calls.append({"name": "margin_summary", "args": args})
            customer = re.search(r"\bC-\d{3}\b", question, re.IGNORECASE)
            if customer:
                calls.append(
                    {"name": "customer_lookup", "args": {"customer_id": customer.group().upper()}}
                )
            return AIMessage(
                content="",
                tool_calls=[
                    {**c, "id": f"demo-{i}", "type": "tool_call"} for i, c in enumerate(calls)
                ],
            )
        lines = ["Local demo · synthetic data · deterministic planner"]
        for message in results:
            result = json.loads(message.content)
            if not result["ok"]:
                lines.append(f"{message.name}: {result['error']}.")
                continue
            data = result["data"]
            if message.name == "search_documents":
                for doc in data["documents"]:
                    lines.append(f"[{doc['id']}] {doc['title']}: {doc['text']}")
                if not data["documents"]:
                    lines.append("No accessible documents matched the query.")
            elif message.name == "revenue_summary":
                scope = ", ".join(data["scope"]["regions"])
                period = data["scope"]["month"] or data["scope"]["available_period"]
                lines.append(
                    f"Revenue: ${data['revenue_cents'] / 100:,.2f} USD; "
                    f"{data['order_count']} orders; {scope}; {period}. [demo://orders]"
                )
            elif message.name == "margin_summary":
                scope = ", ".join(data["scope"]["regions"])
                period = data["scope"]["month"] or "2026-Q1"
                lines.append(
                    f"Gross margin: ${data['gross_margin_cents'] / 100:,.2f} USD "
                    f"({data['gross_margin_percent']}%); {scope}; {period}. [demo://orders]"
                )
            elif message.name == "customer_lookup":
                lines.append(
                    f"Customer {data['id']}: {data['company']}; {data['tier']}; "
                    f"{data['region']}; email {data['email']}. [{data['source']}]"
                )
        return AIMessage(content="\n\n".join(lines))
