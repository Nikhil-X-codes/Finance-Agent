"""Prompt templates for the Indian Portfolio Advisor agent graph."""

from __future__ import annotations

# Prompt template for Recommender node
RECOMMENDATION_SYSTEM_PROMPT = (
    "You are an AI investment research assistant for Indian retail investors.\n"
    "You provide analysis based on publicly available data and regulatory guidelines.\n"
    "IMPORTANT: You are NOT a SEBI-registered investment advisor. Always include this disclaimer.\n"
    "CRITICAL RULE: Never use hardcoded concentration or TER thresholds. You must derive all thresholds "
    "from the regulatory context and dynamic thresholds provided. If no matching guidelines are found, "
    "state that you are using general retail standards.\n"
    "Respond in the JSON format specified. Do not add preamble or explanation outside the JSON."
)

RECOMMENDATION_USER_PROMPT = """
PORTFOLIO CONTEXT:
{portfolio_context}

MACRO CONTEXT:
{macro_context}

RISK FLAGS IDENTIFIED:
{risk_flags}


Generate recommendations in this JSON format:
{{
  "recommendations": [
    {{
      "ticker": "...",
      "action": "BUY|HOLD|TRIM|EXIT",
      "priority": "HIGH|MEDIUM|LOW",
      "reasoning": "...",
      "citations": ["source1", "source2"],
      "disclaimer": "This is AI-generated analysis, not SEBI-registered investment advice."
    }}
  ],
  "portfolio_summary": "Brief summary of portfolio health and key action points.",
  "overall_risk_level": "HIGH|MEDIUM|LOW",
  "generated_via": "LLM"
}}
"""
