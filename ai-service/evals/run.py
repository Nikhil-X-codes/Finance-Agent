"""Run the production Q&A graph with a versioned synthetic dataset."""

import argparse
import asyncio
from collections import defaultdict
from datetime import date
import json
import math
import os
from pathlib import Path
from statistics import mean
import sys

from src.core.qa_graph import create_qa_graph, default_qa_providers
from src.core.qa_types import GroundedAnswer, ParsedQuestion, QAProviders

FIXTURE = Path(__file__).with_name("v2.json")


def load_fixture(path: Path = FIXTURE):
    return json.loads(path.read_text(encoding="utf-8"))


async def run_case(graph, fixture, case, *, live_answer=False):
    async def market(symbol: str, when: date | None):
        return fixture["quotes"].get(f"{symbol}:{when.isoformat() if when else 'latest'}", {})

    async def classify(_question, _history):
        return ParsedQuestion(intent="clarify")

    async def answer(_query, evidence):
        return GroundedAnswer(text=case["reference"], evidence_ids=[e["id"] for e in evidence])

    providers = default_qa_providers()
    context = QAProviders(providers.classify if live_answer else classify,
                          providers.answer if live_answer else answer, market)
    return await graph.ainvoke({
        "question": case["question"],
        "conversation_history": case.get("history", []),
        "raw_holdings": fixture["portfolios"][case["portfolio"]],
    }, context=context)


def check_case(case, result, *, live_answer=False):
    errors = []
    evidence = result.get("evidence", [])
    citations = result.get("qa_citations", [])
    evidence_by_id = {doc["id"]: doc for doc in evidence}
    if result.get("question_type") != case["expected_intent"]:
        errors.append("intent mismatch")
    if result.get("answer_status") != case["expected_status"]:
        errors.append("answer status mismatch")
    if sorted({doc["kind"] for doc in evidence}) != sorted(case["expected_kinds"]):
        errors.append("evidence source mismatch")
    if any(
        citation["id"] not in evidence_by_id or
        citation["relevantText"] != evidence_by_id[citation["id"]]["text"]
        for citation in citations
    ):
        errors.append("citation did not resolve to the supplied evidence")
    if evidence and case["expected_status"] == "answered" and not citations:
        errors.append("missing citation")
    text = result.get("qa_response", "").casefold()
    contexts = "\n".join(doc["text"] for doc in evidence)
    for fragment in case.get("evidence_contains", []):
        if fragment not in contexts:
            errors.append(f"missing evidence: {fragment}")
    # Model paraphrases are scored by Ragas. Mock responses retain exact strings.
    for value in case.get("contains", []):
        if (not live_answer or any(c.isdigit() for c in value)) and value.casefold() not in text:
            errors.append(f"missing response value: {value}")
    for value in case.get("excluded", []):
        if value.casefold() in text or value in contexts:
            errors.append(f"unexpected value: {value}")
    return errors


async def score_case(case, result, metrics):
    if result["answer_status"] != "answered":
        return {}
    text = result["qa_response"]
    contexts = [doc["text"] for doc in result.get("evidence", [])]
    question = result["parsed_question"].question
    reference = case["reference"]
    factual = await metrics["factual_correctness"].ascore(response=text, reference=reference)
    scores = {"factual_correctness": factual.value}
    if contexts and case["expected_kinds"]:
        scores["faithfulness"] = (await metrics["faithfulness"].ascore(
            user_input=question, response=text, retrieved_contexts=contexts)).value
        for name in ("context_precision", "context_recall"):
            scores[name] = (await metrics[name].ascore(
                user_input=question, reference=reference, retrieved_contexts=contexts)).value
    if any(not math.isfinite(score) for score in scores.values()):
        raise ValueError("Ragas returned a non-finite score")
    return scores


def threshold_failures(aggregates, policy, fixture_version):
    if policy["fixture_version"] != fixture_version:
        raise ValueError("Thresholds do not match the fixture version.")
    failures = []
    for intent, scores in policy["minimums"].items():
        for name, required in scores.items():
            if isinstance(required, bool) or not isinstance(required, (int, float)) or not 0 <= required <= 1:
                raise ValueError(f"Invalid threshold for {intent}.{name}")
            actual = aggregates.get(intent, {}).get(name)
            if actual is None or actual < required:
                failures.append({"intent": intent, "metric": name, "actual": actual, "required": required})
    return failures


async def evaluate(args):
    fixture = load_fixture(args.fixture)
    cases = [case for case in fixture["cases"] if not args.case or case["id"] in args.case]
    if not cases or set(args.case or ()) - {case["id"] for case in cases}:
        raise SystemExit("Unknown evaluation case.")
    graph = create_qa_graph()
    metrics = {}
    client = None
    if args.judge:
        from openai import AsyncOpenAI
        from ragas.llms import llm_factory
        from ragas.metrics.collections import ContextPrecision, ContextRecall, FactualCorrectness, Faithfulness

        key = os.environ.get("EVAL_API_KEY") or os.environ.get("OPENAI_API_KEY")
        model = os.environ.get("EVAL_MODEL")
        if not key or not model:
            raise SystemExit("Set EVAL_API_KEY (or OPENAI_API_KEY) and EVAL_MODEL to run Ragas.")
        client = AsyncOpenAI(api_key=key, base_url=os.environ.get("EVAL_BASE_URL") or None, timeout=45, max_retries=1)
        llm = llm_factory(model, client=client, max_tokens=4096)
        metrics = {name: cls(llm=llm) for name, cls in (
            ("faithfulness", Faithfulness), ("context_precision", ContextPrecision),
            ("context_recall", ContextRecall), ("factual_correctness", FactualCorrectness),
        )}

    by_intent = defaultdict(lambda: defaultdict(list))
    failures = []
    rows = []
    try:
        for case in cases:
            if metrics:
                print(f"Scoring {case['id']}", file=sys.stderr, flush=True)
            state = await run_case(graph, fixture, case, live_answer=args.live_answer)
            errors = check_case(case, state, live_answer=args.live_answer)
            scores = {}
            if metrics:
                try:
                    scores = await asyncio.wait_for(score_case(case, state, metrics), timeout=args.judge_timeout)
                except Exception as exc:
                    errors.append(f"Ragas failed: {type(exc).__name__}")
            if errors:
                failures.append(case["id"])
            for metric, score in scores.items():
                by_intent[case["expected_intent"]][metric].append(score)
                by_intent["all"][metric].append(score)
            rows.append({"id": case["id"], "intent": state["question_type"], "status": state["answer_status"],
                         "errors": errors, "scores": scores})
    finally:
        if client:
            await client.close()

    aggregates = {intent: {name: mean(scores) for name, scores in measures.items()}
                  for intent, measures in by_intent.items()}
    gate_failures = []
    if args.thresholds:
        policy = json.loads(args.thresholds.read_text(encoding="utf-8"))
        try:
            gate_failures = threshold_failures(aggregates, policy, fixture["version"])
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    report = {"fixture_version": fixture["version"], "selected_cases": len(cases), "failed_cases": failures,
              "cases": rows, "averages": aggregates, "gate_failures": gate_failures}
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return int(bool(failures or gate_failures))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE, help="Path to a versioned fixture")
    parser.add_argument("--live-answer", action="store_true", help="Use the configured app model on synthetic records")
    parser.add_argument("--judge", action="store_true", help="Score responses using Ragas")
    parser.add_argument("--judge-timeout", type=int, default=120, help="Per-case judge timeout in seconds")
    parser.add_argument("--case", action="append", help="Run one or more named cases")
    parser.add_argument("--thresholds", type=Path, help="Use a versioned minimum-score policy. Run the full fixture.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.judge_timeout <= 0:
        parser.error("--judge-timeout must be positive")
    if args.thresholds and (not args.judge or args.case):
        parser.error("--thresholds requires --judge and the full fixture")
    return asyncio.run(evaluate(args))


if __name__ == "__main__":
    raise SystemExit(main())
