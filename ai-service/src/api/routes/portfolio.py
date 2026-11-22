"""Portfolio concentration assessment for the dashboard."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.config.models import Holding
from src.services.portfolio_risk import assess_portfolio_risk

router = APIRouter()


class PortfolioRiskRequest(BaseModel):
    portfolio: list[Holding] = Field(default_factory=list)


@router.post("/portfolio/risk-status")
async def get_portfolio_risk_status(payload: PortfolioRiskRequest) -> dict:
    return assess_portfolio_risk(payload.portfolio)
