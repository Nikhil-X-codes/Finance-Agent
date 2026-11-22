"""Plot a completed Q&A evaluation as a standalone SVG for the README."""

import argparse
from collections import Counter
from html import escape
import json
from pathlib import Path


INTENT_LABELS = {
    "portfolio": "Portfolio", "market": "Public market", "mixed": "Mixed",
    "general": "Finance education", "clarify": "Clarification", "current_rules": "Current rules",
}
METRIC_LABELS = {
    "faithfulness": "Faithfulness", "context_precision": "Context precision",
    "context_recall": "Context recall", "factual_correctness": "Factual correctness",
}


def render(deterministic: dict, judged: dict | None, gates: dict) -> str:
    counts = Counter(row["intent"] for row in deterministic["cases"])
    passed = Counter(row["intent"] for row in deterministic["cases"] if not row["errors"])
    total = sum(counts.values())
    scores = (judged or {}).get("averages", {}).get("all", {})
    expected = {row["id"] for row in deterministic["cases"] if row["status"] == "answered"}
    scored_cases = sum(bool(row["scores"]) for row in (judged or {}).get("cases", []))
    height = 640 if judged else 374
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="820" height="{height}" viewBox="0 0 820 {height}" role="img" aria-labelledby="title description">',
        '<title id="title">Finance Agent Q&amp;A evaluation results</title>',
        '<desc id="description">Deterministic results by intent and model-judged Ragas scores when available.</desc>',
        f'<rect width="820" height="{height}" rx="16" fill="#f8fafc"/>',
        '<g font-family="system-ui, sans-serif" fill="#0f172a">',
    ]

    def label(x, y, value, size=14, *, bold=False):
        weight = ' font-weight="700"' if bold else ""
        svg.append(f'<text x="{x}" y="{y}" font-size="{size}"{weight}>{escape(str(value))}</text>')

    def bar(y, width, ratio, color):
        svg.append(f'<rect x="205" y="{y}" width="{width}" height="15" rx="4" fill="#e2e8f0"/>')
        if ratio > 0:
            svg.append(f'<rect x="205" y="{y}" width="{width * ratio:.2f}" height="15" rx="4" fill="{color}"/>')

    label(30, 47, f"Q&A evaluation · Fixture v{deterministic['fixture_version']}", 26, bold=True)
    label(30, 77, f"Deterministic graph checks · {sum(passed.values())}/{total} passed", 16, bold=True)
    label(30, 102, "Synthetic portfolios and quotes · model responses mocked")
    largest = max(counts.values(), default=1)
    for i, (intent, name) in enumerate(INTENT_LABELS.items()):
        y = 126 + 34 * i
        label(30, y + 13, name)
        bar(y, 420 * counts[intent] / largest, passed[intent] / counts[intent] if counts[intent] else 0, "#0f766e")
        label(655, y + 13, f"{passed[intent]}/{counts[intent]}")

    if judged:
        label(30, 367, "Ragas · Live answers and judge", 16, bold=True)
        label(30, 392, f"{scored_cases}/{len(expected)} answerable cases scored · {len(judged['failed_cases'])} cases with errors")
        label(650, 417, "Score / scored cases", 12)
        for i, (metric, name) in enumerate(METRIC_LABELS.items()):
            y = 433 + 34 * i
            score = scores.get(metric)
            count = sum(metric in row["scores"] for row in judged["cases"])
            label(30, y + 13, name)
            bar(y, 420, score or 0, "#2457a6")
            gate = gates.get(metric)
            if gate is not None:
                x = 205 + 420 * gate
                svg.append(f'<path d="M{x:.2f} {y - 3}v21" stroke="#0f172a" stroke-width="2"/>')
            label(655, y + 13, "Unavailable" if score is None else f"{score:.2f} / {count}")
        label(30, 595, "Vertical marks show the configured minimums. Averages use completed scores only.", 13)
        if judged["failed_cases"] or judged["gate_failures"]:
            label(30, 617, "The live run did not pass every evaluation check.", 13, bold=True)

    svg.extend(["</g>", "</svg>", ""])
    return "\n".join(svg)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deterministic", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--judged", type=Path)
    parser.add_argument("--thresholds", type=Path)
    args = parser.parse_args()
    deterministic = json.loads(args.deterministic.read_text(encoding="utf-8"))
    judged = json.loads(args.judged.read_text(encoding="utf-8")) if args.judged else None
    thresholds = json.loads(args.thresholds.read_text(encoding="utf-8")) if args.thresholds else {}
    if judged and judged["fixture_version"] != deterministic["fixture_version"]:
        parser.error("The reports must use the same fixture version.")
    if thresholds and thresholds["fixture_version"] != deterministic["fixture_version"]:
        parser.error("The threshold policy must match the fixture version.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(deterministic, judged, thresholds.get("minimums", {}).get("all", {})), encoding="utf-8")


if __name__ == "__main__":
    main()
