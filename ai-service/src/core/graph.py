import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.tracers import LangChainTracer
from langgraph.graph import END, START, StateGraph

from src.config.settings import settings
from src.core.edges.conditions import route_recommender, route_portfolio_context
from src.core.edges.router import route_request
from src.core.nodes.enricher import enrich_portfolio
from src.core.nodes.output import format_output
from src.core.nodes.parser import parse_holdings
from src.core.nodes.qa_generator import generate_qa_response
from src.core.nodes.portfolio_context import build_portfolio_context
from src.core.nodes.recommender import generate_recommendations
from src.core.nodes.risk_analyzer import analyze_portfolio_risk
from src.core.nodes.trade_validator import validate_trade
from src.core.state import PortfolioState

# Global tracer instance for LangSmith integration
tracer = LangChainTracer(project_name=settings.langsmith_project or "Agent")


def create_agent_graph() -> StateGraph:
    """Build and compile the LangGraph StateGraph."""
    workflow = StateGraph(PortfolioState)

    # 1. Register all nodes
    workflow.add_node("parser", parse_holdings)
    workflow.add_node("enricher", enrich_portfolio)
    workflow.add_node("portfolio_context", build_portfolio_context)
    workflow.add_node("risk_analyzer", analyze_portfolio_risk)
    workflow.add_node("recommender", generate_recommendations)
    workflow.add_node("output", format_output)
    workflow.add_node("qa_generator", generate_qa_response)
    workflow.add_node("trade_validator", validate_trade)

    # 2. Add entry router
    workflow.add_conditional_edges(
        START,
        route_request,
        {
            "parser": "parser",
            "qa_retriever": "portfolio_context",
            "trade_validator": "trade_validator"
        }
    )

    # 3. Add report subgraph edges
    workflow.add_edge("parser", "enricher")
    workflow.add_edge("enricher", "portfolio_context")
    
    # Conditional route after portfolio context to branch for QA vs Report
    workflow.add_conditional_edges(
        "portfolio_context",
        route_portfolio_context,
        {
            "qa_generator": "qa_generator",
            "risk_analyzer": "risk_analyzer"
        }
    )
    
    # Conditional route after risk analysis (skip recommender on empty portfolio / critical errors)
    workflow.add_conditional_edges(
        "risk_analyzer",
        route_recommender,
        {
            "recommender": "recommender",
            "output": "output"
        }
    )
    
    workflow.add_edge("recommender", "output")
    workflow.add_edge("output", END)

    # 4. Add Q&A subgraph edges
    workflow.add_edge("qa_generator", END)

    # 5. Add Trade Validation edges
    workflow.add_edge("trade_validator", END)

    # 6. Compile graph with checkpointer
    # Step 8 HITL post-parse checkpoint integration:
    # Compile with interrupt_after parser
    import asyncio
    import aiosqlite
    import threading
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    async def make_saver():
        conn = aiosqlite.connect(settings.sqlite_path, check_same_thread=False)
        await conn.__aenter__()
        return AsyncSqliteSaver(conn)

    class LoopThread(threading.Thread):
        def run(self):
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.saver = self.loop.run_until_complete(make_saver())

    t = LoopThread()
    t.start()
    t.join()
    checkpointer = t.saver
    
    return workflow.compile(checkpointer=checkpointer, interrupt_after=["parser"])


# Singleton instance of compiled agent
agent_graph = create_agent_graph()
