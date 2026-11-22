"""Produce grounded responses with citations that resolve to supplied evidence."""

import json

from langgraph.runtime import Runtime

from ..qa_types import GroundedAnswer, QAProviders, QAState


def check_evidence(state: QAState) -> dict:
    intent = state["parsed_question"].intent
    if intent == "clarify":
        return {"answer_status": "clarify"}
    if intent == "current_rules":
        return {
            "answer_status": "unavailable",
            "limitations": ["I could not verify current tax or regulatory rules from an official source."],
        }
    if intent in {"portfolio", "market", "mixed"} and not state.get("evidence"):
        return {"answer_status": "unavailable"}
    return {"answer_status": "answered"}


async def generate_qa_response(state: QAState, runtime: Runtime[QAProviders]) -> dict:
    evidence = state.get("evidence") or []
    limitations = state.get("limitations") or []
    parsed = state["parsed_question"]
    if state["answer_status"] != "answered":
        fallback = "Can you clarify whether you mean your portfolio or general market information?"
        return {"qa_response": "\n\n".join(limitations) or fallback, "qa_citations": []}

    try:
        if parsed.intent == "market":
            lines = []
            for item in evidence:
                quote = json.loads(item["text"])
                lines.append(f"{quote['symbol']}: {quote['currency']} {quote['price']:,} as of {quote['published_at']}.")
            answer = GroundedAnswer(text="\n".join(lines), evidence_ids=[item["id"] for item in evidence])
        elif parsed.answer_kind == "holding_quantity":
            active = [(item, json.loads(item["text"])) for item in evidence]
            active = [(item, row) for item, row in active if row["status"] != "REALIZED" and row["quantity"] > 0]
            if len(active) != 1:
                return {
                    "qa_response": "I could not verify a single active holding for that symbol.",
                    "qa_citations": [],
                    "answer_status": "unavailable",
                }
            item, row = active[0]
            answer = GroundedAnswer(
                text=f"You hold {row['quantity']} units of {row['ticker']}.",
                evidence_ids=[item["id"]],
            )
        elif parsed.answer_kind == "portfolio_value":
            totals = json.loads(evidence[0]["text"])
            market = totals["total_current"]
            cost = f"{totals['total_invested']:,.2f}".rstrip("0").rstrip(".")
            quoted = "unavailable" if market is None else f"INR {market:,.2f}"
            answer = GroundedAnswer(
                text=f"Quoted market value is {quoted}. The invested cost is INR {cost}.",
                evidence_ids=[evidence[0]["id"]],
            )
        else:
            answer = await runtime.context.answer(parsed, evidence)
        by_id = {item["id"]: item for item in evidence}
        ids = list(dict.fromkeys(answer.evidence_ids))
        if any(item_id not in by_id for item_id in ids) or (evidence and not ids):
            raise ValueError("Answer citations did not resolve to supplied records")
        citations = [
            {
                "id": item_id, "source": by_id[item_id]["source"], "docTitle": by_id[item_id]["title"],
                "section": item_id, "date": by_id[item_id]["date"], "relevantText": by_id[item_id]["text"],
            }
            for item_id in ids
        ]
        return {"qa_response": "\n\n".join([answer.text.strip(), *limitations]), "qa_citations": citations}
    except Exception:
        return {
            "qa_response": "\n\n".join(["I couldn't produce a verified answer for this question.", *limitations]),
            "qa_citations": [],
            "answer_status": "unavailable",
        }
