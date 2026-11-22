"""Market-data contract shared by Stocks, Q&A, and reports."""

from dataclasses import dataclass
from datetime import date
from typing import Protocol, TypedDict

from src.config.settings import settings
from src.core.tools.nse_market import NseMcpProvider


class Quote(TypedDict, total=False):
    company_name: str
    current_price: float | None
    previous_close: float | None
    day_change: float | None
    day_change_percent: float | None
    fifty_two_week_range: str | None
    currency: str
    source: str
    timestamp: str
    fresh: bool
    status: str
    error: str


class SymbolMatch(TypedDict):
    symbol: str
    name: str


class DailyBar(TypedDict):
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float
    volume: float | None


class PriceHistory(TypedDict, total=False):
    status: str
    source: str
    asOf: str
    points: list[DailyBar]
    adjustedPriceReturnPercent: float | None
    adjustment: str


class MarketDataProvider(Protocol):
    async def quote(self, symbol: str) -> Quote: ...

    async def search(self, query: str) -> list[SymbolMatch]: ...

    async def history(self, symbol: str) -> PriceHistory: ...

    async def historical_close(self, symbol: str, trading_date: date) -> Quote: ...

    async def movers(self, limit: int) -> dict[str, list[str]]: ...


@dataclass
class MarketDataService:
    provider: MarketDataProvider | None

    @property
    def enabled(self) -> bool:
        return self.provider is not None

    async def quote(self, symbol: str) -> Quote:
        if self.provider is None:
            return {"status": "disabled", "error": "MARKET_DATA_DISABLED"}
        return await self.provider.quote(symbol)

    async def search(self, query: str) -> list[SymbolMatch]:
        if self.provider is None:
            return []
        return await self.provider.search(query)

    async def history(self, symbol: str) -> PriceHistory:
        if self.provider is None:
            return {"status": "disabled"}
        return await self.provider.history(symbol)

    async def historical_close(self, symbol: str, trading_date: date) -> Quote:
        if self.provider is None:
            return {}
        return await self.provider.historical_close(symbol, trading_date)

    async def movers(self, limit: int) -> dict[str, list[str]]:
        if self.provider is None:
            return {"gainers": [], "losers": []}
        return await self.provider.movers(limit)


market_data = MarketDataService(NseMcpProvider() if settings.nse_market_data else None)
