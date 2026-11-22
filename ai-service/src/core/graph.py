"""LangGraph workflow for portfolio reports."""

from langgraph.graph import END, START, StateGraph

from .nodes.enricher import enrich_portfolio
from .nodes.output import format_output
from .nodes.parser import parse_holdings
from .nodes.portfolio_context import build_portfolio_context
from .nodes.recommender import generate_recommendations
from .nodes.risk_analyzer import analyze_portfolio_risk
from .state import ReportState


def _after_risk(state: ReportState) -> str:
    return "recommender" if state.get("normalized_holdings") else "output"


def create_report_graph():
    graph = StateGraph(ReportState)
    graph.add_node("parser", parse_holdings)
    graph.add_node("enricher", enrich_portfolio)
    graph.add_node("portfolio_context", build_portfolio_context)
    graph.add_node("risk_analyzer", analyze_portfolio_risk)
    graph.add_node("recommender", generate_recommendations)
    graph.add_node("output", format_output)
    graph.add_edge(START, "parser")
    graph.add_edge("parser", "enricher")
    graph.add_edge("enricher", "portfolio_context")
    graph.add_edge("portfolio_context", "risk_analyzer")
    graph.add_conditional_edges("risk_analyzer", _after_risk, ["recommender", "output"])
    graph.add_edge("recommender", "output")
    graph.add_edge("output", END)
    return graph.compile()
