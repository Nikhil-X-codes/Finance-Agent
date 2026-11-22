"""Resolve what source the question needs before retrieving facts."""

import re
from datetime import date

from langgraph.runtime import Runtime

from ..qa_types import ParsedQuestion, QAProviders, QAState

PERSONAL = re.compile(
    r"\b(?:(?:my|our)\b.{0,55}\b(?:portfolio|shares?|holdings?|positions?|trades?|allocation|exposure|cost|returns?|p\s*&\s*l|profit|loss|investments?)|"
    r"(?:do i (?:own|hold|have)|did i (?:buy|sell)|i (?:bought|sold|hold|own)))\b", re.I
)
PUBLIC_MARKET = re.compile(
    r"\b(?:quote|ltp|latest (?:available )?price|current price|stock price|market price|closing price|previous close|"
    r"last traded price|last price|trading at|close on|price on|price today)\b", re.I
)
MARKET_ANALYSIS = re.compile(r"\b(?:closing prices|price history|moving averages?|corporate actions)\b", re.I)
MARKET_ANALYSIS_REQUEST = re.compile(r"^(?:show|list|compare|get|give|find|plot)\b", re.I)
EDUCATION = re.compile(
    r"^(?:what (?:is|are)|explain|define|how (?:does|do))\b.*\b"
    r"(?:ETF|SIP|NAV|mutual funds?|dividends?|market capitalization|cost basis|unrealized|realized|diversification|inflation)\b", re.I
)
CURRENT_RULES = re.compile(r"\b(?:tax|taxation|stcg|ltcg|regulations?|sebi|compliance|rules?)\b", re.I)
FOLLOW_UP = re.compile(r"^(?:and\b|what about\b|how about\b|how much\s*[?]$|how many\s*[?]$|what was it\b)", re.I)
DATE_HINT = re.compile(r"\b(?:on|as of|from|between)\b.{0,16}\d|\b(?:yesterday|last (?:week|month|year)|ago)\b", re.I)
TICKER = re.compile(r"[A-Z0-9][A-Z0-9&.\-]{1,19}")
HOLDING_QUANTITY = re.compile(
    r"\b(?:how many|number of|quantity)\b.*\b(?:shares?|units?)\b.*\b(?:do i (?:hold|own|have)|currently hold)\b",
    re.I,
)
PORTFOLIO_VALUE = re.compile(r"\b(?:value of (?:my|our) portfolio|(?:my|our) portfolio (?:worth|value))\b", re.I)
NOT_SYMBOLS = {"INR", "ETF", "SIP", "NAV", "NSE", "BSE", "SEBI", "STCG", "LTCG", "LTP", "P&L", "IT"}


def _symbols(text: str, holdings: list[dict]) -> list[str]:
    known = {h.get("ticker", "").upper() for h in holdings if h.get("ticker")}
    explicit = re.findall(r"(?<![\w&.\-])[A-Z][A-Z0-9&.\-]{1,19}(?![\w&.\-])", text)
    known_mentions = [s for s in sorted(known) if re.search(
        rf"(?<![\w&.\-]){re.escape(s)}(?![\w&.\-])", text, re.I
    )]
    return list(dict.fromkeys(s.rstrip(".-") for s in [*known_mentions, *explicit] if s.rstrip(".-") not in NOT_SYMBOLS))[:4]


def _rule_intent(text: str):
    if CURRENT_RULES.search(text) and not PERSONAL.search(text):
        return "current_rules"
    private = bool(PERSONAL.search(text))
    market = bool(PUBLIC_MARKET.search(text))
    if private or market:
        return "mixed" if private and market else "portfolio" if private else "market"
    if EDUCATION.search(text):
        return "general"
    return None


def _date(text: str) -> date | None:
    matches = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text))
    if len(matches) != 1:
        return None
    try:
        return date.fromisoformat(matches.pop())
    except ValueError:
        return None


async def parse_question(state: QAState, runtime: Runtime[QAProviders]) -> dict:
    question = state["question"].strip()
    history = [
        turn["content"][:500] for turn in state.get("conversation_history", [])[-8:]
        if turn.get("role") == "user" and isinstance(turn.get("content"), str) and turn["content"].strip() != question
    ]
    known = state.get("raw_holdings") or []
    prior = history[-1] if history else ""
    found = _symbols(question, known)
    intent = _rule_intent(question)
    is_followup = prior and FOLLOW_UP.search(question)
    if is_followup and intent is None:
        intent = _rule_intent(prior)
    resolved = f"{question}\nPrevious question: {prior}" if is_followup else question
    if not found and is_followup:
        found = _symbols(prior, known)
    requested_market_analysis = bool(
        MARKET_ANALYSIS.search(question)
        and (found or PUBLIC_MARKET.search(question) or MARKET_ANALYSIS_REQUEST.search(question))
    )
    if requested_market_analysis and intent != "current_rules":
        intent = "mixed" if PERSONAL.search(question) else "market"

    if intent is None:
        try:
            parsed = await runtime.context.classify(question, history)
            found = [s.upper() for s in parsed.symbols if TICKER.fullmatch(s.upper())]
            intent = parsed.intent
            resolved = parsed.question.strip() or resolved
        except Exception:
            intent = "clarify"

    # Require an explicit ISO date for historical prices. Never silently substitute today's quote.
    trading_date = _date(question) or (_date(prior) if is_followup and not DATE_HINT.search(question) else None)
    limitations = []
    if intent in {"market", "mixed"} and not requested_market_analysis and DATE_HINT.search(question) and trading_date is None:
        limitations = ["Which trading date should I look up? Enter it as YYYY-MM-DD."]
        intent = "clarify"
    if intent == "market" and not found and not requested_market_analysis:
        limitations = ["Which NSE stock symbol should I look up?"]
        intent = "clarify"
    answer_kind = "explanation"
    if intent in {"market", "mixed"} and requested_market_analysis:
        answer_kind = "unsupported_market_analysis"
    elif intent == "portfolio":
        if len(found) == 1 and HOLDING_QUANTITY.search(resolved):
            answer_kind = "holding_quantity"
        elif not found and PORTFOLIO_VALUE.search(question):
            answer_kind = "portfolio_value"
    return {
        "question_type": intent,
        "parsed_question": ParsedQuestion(
            intent=intent, symbols=found, trading_date=trading_date, question=resolved,
            answer_kind=answer_kind,
        ),
        "limitations": limitations,
    }
