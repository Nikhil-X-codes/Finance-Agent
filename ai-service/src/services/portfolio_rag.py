"""Portfolio RAG - vectorize holdings and trades for Q&A retrieval."""

from __future__ import annotations

import asyncio
import numpy as np
from typing import Any

from src.services.embedding_service import get_embedding_service
from src.config.settings import settings


class PortfolioRAG:
    """RAG engine that retrieves from portfolio/trade history context dynamically.
    
    Indexes 8 types of documents for comprehensive portfolio coverage:
    1. Individual holdings (with weights, values, sector)
    2. Individual trades (with P&L, buy/sell prices)
    3. Portfolio summary (overall metrics)
    4. Trade summary (best/worst trades, total P&L)
    5. Sector allocation (sector-level aggregation)
    6. Concentration analysis (top holdings, risk assessment)
    7. Diversification profile (number of sectors, asset types)
    8. Holding comparisons (relative weights, largest vs smallest)
    """
    
    _instance = None
    
    @classmethod
    def get_instance(cls) -> PortfolioRAG:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self) -> None:
        self._embedder = None
        self._documents: list[dict[str, Any]] = []
        self._vectors: np.ndarray | None = None
    
    def _get_embedder(self):
        if self._embedder is None:
            self._embedder = get_embedding_service(
                model_name=settings.embedding_model_name,
                cache_folder=settings.embedding_cache_folder,
            )
        return self._embedder

    def _get_display_name(self, h: dict) -> str:
        """Resolve a human-readable display name for the holding/security.
        Avoids showing raw ISIN codes where possible."""
        name = h.get("name") or ""
        ticker = h.get("ticker") or ""
        if not name:
            return ticker
        if name == ticker:
            return name
        # If ticker looks like an ISIN (12 chars, starting with INE) but name is human-readable, use name
        is_isin = len(ticker) == 12 and ticker.startswith("INE")
        if is_isin and name and not (len(name) == 12 and name.startswith("INE")):
            return name
        return f"{name} ({ticker})"
    
    async def index_portfolio(self, holdings: list[dict], trades: list[dict]):
        """Build vector index from active holdings + trade history."""
        documents = []
        
        # Calculate total invested value first
        total_invested = 0.0
        for h in holdings:
            qty = float(h.get("quantity") or 0.0)
            if qty <= 0:
                continue
            
            buy_price = float(h.get("avg_buy_price") or 0.0)
            value = qty * buy_price
            total_invested += value
        
        # ── 1. Index individual active holdings (enriched text) ──
        for h in holdings:
            qty = float(h.get("quantity") or 0.0)
            if qty <= 0:
                continue
                
            buy_price = float(h.get("avg_buy_price") or 0.0)
            value = qty * buy_price
            weight = (value / total_invested * 100) if total_invested > 0 else 0.0
            ticker = h.get("ticker", "UNKNOWN")
            display_name = self._get_display_name(h)
            sector = h.get("sector", "Other")
            asset_type = h.get("asset_type", "STOCK")
            
            text = (
                f"User currently holds an active position of {qty:.0f} shares of {display_name} "
                f"in the {sector} sector. "
                f"Average buy price is ₹{buy_price:,.2f}, "
                f"total invested value is ₹{value:,.2f}, "
                f"which represents {weight:.1f}% of the portfolio. "
                f"Asset type is {asset_type}. "
                f"This is {'a major' if weight > 25 else 'a moderate' if weight > 10 else 'a minor'} "
                f"position in the portfolio."
            )
            
            documents.append({
                "id": f"holding_{ticker}",
                "text": text,
                "type": "holding",
                "source": f"holding_{ticker.lower()}",
                "data": h
            })
        
        # ── 2. Index individual realized trades (enriched text) ──
        for t in trades:
            ticker = t.get("ticker", "UNKNOWN")
            display_name = self._get_display_name(t)
            qty = float(t.get("quantity") or 0.0)
            buy_price = float(t.get("avg_buy_price") or t.get("buy_price") or 0.0)
            sell_price = float(t.get("sell_price") or 0.0)
            pnl = float(t.get("realized_pnl") or 0.0)
            buy_date = t.get("buy_date") or "unknown date"
            sell_date = t.get("sell_date") or "unknown date"
            
            pnl_pct = ((sell_price - buy_price) / buy_price * 100) if buy_price > 0 else 0.0
            pnl_label = "profit" if pnl >= 0 else "loss"
            
            text = (
                f"User completed a trade for {display_name}. "
                f"Bought {qty:.0f} shares at ₹{buy_price:,.2f} on {buy_date} "
                f"and sold them at ₹{sell_price:,.2f} on {sell_date}. "
                f"Realized {pnl_label} (P&L) was ₹{pnl:,.2f} "
                f"({'+' if pnl >= 0 else ''}{pnl_pct:.1f}% return). "
                f"This trade is now closed and fully realized."
            )
            
            documents.append({
                "id": f"trade_{ticker}",
                "text": text,
                "type": "trade",
                "source": f"trade_{ticker.lower()}",
                "data": t
            })
            
        # ── 3. Portfolio summary (overall metrics) ──
        active_holdings = [h for h in holdings if float(h.get("quantity") or 0) > 0]
        if active_holdings:
            display_names = [self._get_display_name(h) for h in active_holdings]
            sectors = set(h.get("sector") or "Other" for h in active_holdings)
            asset_types = set(h.get("asset_type") or "STOCK" for h in active_holdings)
            
            summary_text = (
                f"User portfolio overview: The portfolio has {len(display_names)} active holdings "
                f"with a total invested capital of ₹{total_invested:,.2f}. "
                f"Active securities owned: {', '.join(display_names)}. "
                f"The portfolio spans {len(sectors)} sector(s): {', '.join(sorted(sectors))}. "
                f"Asset types held: {', '.join(sorted(asset_types))}. "
                f"Total number of distinct stocks/funds: {len(display_names)}."
            )
            documents.append({
                "id": "portfolio_summary",
                "text": summary_text,
                "type": "summary",
                "source": "portfolio_overview",
                "data": {"holdings_count": len(display_names), "total_invested": total_invested, "sectors": list(sectors)}
            })
            
        # ── 4. Trade summary (aggregated trade metrics) ──
        if trades:
            total_pnl = sum(float(t.get("realized_pnl") or 0.0) for t in trades)
            profitable = [t for t in trades if float(t.get("realized_pnl") or 0.0) > 0]
            loss_making = [t for t in trades if float(t.get("realized_pnl") or 0.0) < 0]
            
            best_trade = max(trades, key=lambda x: float(x.get("realized_pnl") or 0.0))
            worst_trade = min(trades, key=lambda x: float(x.get("realized_pnl") or 0.0))
            
            win_rate = (len(profitable) / len(trades) * 100) if trades else 0
            
            summary_text = (
                f"User trade history summary: Completed {len(trades)} total trades. "
                f"Total realized P&L across all trades is ₹{total_pnl:,.2f}. "
                f"{len(profitable)} trade(s) were profitable, {len(loss_making)} resulted in losses. "
                f"Win rate is {win_rate:.0f}%. "
                f"Best performing trade was {self._get_display_name(best_trade)} with profit of ₹{float(best_trade.get('realized_pnl') or 0.0):,.2f}. "
                f"Worst performing trade was {self._get_display_name(worst_trade)} with loss/PNL of ₹{float(worst_trade.get('realized_pnl') or 0.0):,.2f}."
            )
            documents.append({
                "id": "trade_summary",
                "text": summary_text,
                "type": "summary",
                "source": "trade_history",
                "data": {"trades_count": len(trades), "total_pnl": total_pnl, "win_rate": win_rate}
            })
        
        # ── 5. Sector allocation document ──
        if active_holdings and total_invested > 0:
            sector_values: dict[str, float] = {}
            sector_tickers: dict[str, list[str]] = {}
            for h in active_holdings:
                sec = h.get("sector") or "Other"
                val = float(h.get("quantity") or 0) * float(h.get("avg_buy_price") or 0)
                sector_values[sec] = sector_values.get(sec, 0.0) + val
                if sec not in sector_tickers:
                    sector_tickers[sec] = []
                sector_tickers[sec].append(self._get_display_name(h))
            
            sector_lines = []
            for sec, val in sorted(sector_values.items(), key=lambda x: -x[1]):
                weight = val / total_invested * 100
                ticks = ", ".join(sector_tickers.get(sec, []))
                sector_lines.append(f"{sec}: ₹{val:,.2f} ({weight:.1f}%) — includes {ticks}")
            
            top_sector = max(sector_values, key=sector_values.get)
            top_sector_weight = sector_values[top_sector] / total_invested * 100
            
            sector_text = (
                f"Portfolio sector allocation breakdown: "
                f"The portfolio is invested across {len(sector_values)} sector(s). "
                + ". ".join(sector_lines) + ". "
                f"The largest sector exposure is {top_sector} at {top_sector_weight:.1f}% of the portfolio. "
                f"{'The portfolio is heavily concentrated in one sector.' if top_sector_weight > 50 else 'Sector diversification is moderate.' if len(sector_values) < 4 else 'Sector diversification is reasonable.'}"
            )
            documents.append({
                "id": "sector_allocation",
                "text": sector_text,
                "type": "analysis",
                "source": "sector_analysis",
                "data": {"sectors": {k: round(v / total_invested, 4) for k, v in sector_values.items()}}
            })
        
        # ── 6. Concentration analysis document ──
        if active_holdings and total_invested > 0:
            weighted = []
            for h in active_holdings:
                val = float(h.get("quantity") or 0) * float(h.get("avg_buy_price") or 0)
                weight = val / total_invested * 100
                weighted.append((self._get_display_name(h), weight, val))
            
            weighted.sort(key=lambda x: -x[1])
            top_3 = weighted[:3]
            top_3_weight = sum(w[1] for w in top_3)
            
            top_lines = [f"{t}: {w:.1f}% (₹{v:,.2f})" for t, w, v in top_3]
            
            if weighted[0][1] > 50:
                risk_level = "CRITICAL — single stock dominates more than 50% of the portfolio"
            elif weighted[0][1] > 30:
                risk_level = "HIGH — top holding exceeds 30% of portfolio"
            elif top_3_weight > 80:
                risk_level = "MODERATE — top 3 holdings represent over 80%"
            else:
                risk_level = "LOW — portfolio is reasonably diversified"
            
            conc_text = (
                f"Portfolio concentration analysis: "
                f"Top holdings by weight: {'; '.join(top_lines)}. "
                f"Top 3 holdings together represent {top_3_weight:.1f}% of the portfolio. "
                f"Concentration risk level: {risk_level}. "
                f"The portfolio has {len(weighted)} total active positions."
            )
            documents.append({
                "id": "concentration_analysis",
                "text": conc_text,
                "type": "analysis",
                "source": "concentration_analysis",
                "data": {"top_holdings": [(t, round(w, 2)) for t, w, _ in top_3], "risk_level": risk_level}
            })
        
        # ── 7. Diversification profile document ──
        if active_holdings:
            sectors = set(h.get("sector") or "Other" for h in active_holdings)
            asset_types = set(h.get("asset_type") or "STOCK" for h in active_holdings)
            num_holdings = len(active_holdings)
            
            if num_holdings >= 8 and len(sectors) >= 4:
                div_score = "Well diversified"
            elif num_holdings >= 4 and len(sectors) >= 3:
                div_score = "Moderately diversified"
            elif num_holdings >= 2 and len(sectors) >= 2:
                div_score = "Lightly diversified"
            else:
                div_score = "Poorly diversified — high concentration risk"
            
            has_mf = "MUTUAL_FUND" in asset_types
            has_etf = "ETF" in asset_types
            equity_only = asset_types == {"STOCK"}
            
            div_text = (
                f"Portfolio diversification profile: "
                f"{num_holdings} active holdings across {len(sectors)} sector(s) and {len(asset_types)} asset type(s). "
                f"Sectors: {', '.join(sorted(sectors))}. "
                f"Asset types: {', '.join(sorted(asset_types))}. "
                f"Overall diversification rating: {div_score}. "
                f"{'Includes mutual funds for broader exposure. ' if has_mf else ''}"
                f"{'Includes ETFs for passive diversification. ' if has_etf else ''}"
                f"{'Portfolio is 100% direct equity with no MF/ETF allocation.' if equity_only and num_holdings > 1 else ''}"
            )
            documents.append({
                "id": "diversification_profile",
                "text": div_text,
                "type": "analysis",
                "source": "diversification_analysis",
                "data": {"sectors": list(sectors), "asset_types": list(asset_types), "rating": div_score}
            })
        
        # ── 8. Holding comparison document (if 2+ holdings) ──
        if len(active_holdings) >= 2 and total_invested > 0:
            weighted = []
            for h in active_holdings:
                val = float(h.get("quantity") or 0) * float(h.get("avg_buy_price") or 0)
                weight = val / total_invested * 100
                weighted.append((self._get_display_name(h), weight, val, h.get("sector", "Other")))
            
            weighted.sort(key=lambda x: -x[1])
            largest = weighted[0]
            smallest = weighted[-1]
            
            comparison_text = (
                f"Holding comparison: Largest position is {largest[0]} at {largest[1]:.1f}% "
                f"(₹{largest[2]:,.2f}, sector: {largest[3]}). "
                f"Smallest position is {smallest[0]} at {smallest[1]:.1f}% "
                f"(₹{smallest[2]:,.2f}, sector: {smallest[3]}). "
                f"The weight ratio between largest and smallest is {largest[1]/smallest[1]:.1f}x. "
                f"{'This indicates a highly skewed portfolio.' if largest[1]/smallest[1] > 5 else 'Position sizing is relatively balanced.' if largest[1]/smallest[1] < 2 else 'There is moderate variation in position sizes.'}"
            )
            documents.append({
                "id": "holding_comparison",
                "text": comparison_text,
                "type": "analysis",
                "source": "holding_comparison",
                "data": {"largest": largest[0], "smallest": smallest[0]}
            })
            
        self._documents = documents
        
        # Concurrently generate embeddings
        if documents:
            embedder = self._get_embedder()
            tasks = [embedder.embed(d["text"]) for d in documents]
            vectors = await asyncio.gather(*tasks)
            self._vectors = np.array(vectors)
            print(f"[OK] Indexed {len(documents)} portfolio RAG documents ({sum(1 for d in documents if d['type'] == 'holding')} holdings, {sum(1 for d in documents if d['type'] == 'trade')} trades, {sum(1 for d in documents if d['type'] == 'summary')} summaries, {sum(1 for d in documents if d['type'] == 'analysis')} analysis docs)")
        else:
            self._vectors = None
            print("[Warning] No documents to index for portfolio RAG")
            
    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search portfolio records matching semantic query.
        
        Uses adaptive relevance thresholds:
        - Holdings/trades: score > 0.20 (more permissive for specific data)
        - Summaries/analysis: score > 0.30 (stricter for aggregated insights)
        """
        if not self._documents or self._vectors is None:
            return []
            
        embedder = self._get_embedder()
        query_vector = await embedder.embed(query)
        query_vector = np.array(query_vector)
        
        # Calculate cosine similarities
        dot_product = np.dot(self._vectors, query_vector)
        norms_vectors = np.linalg.norm(self._vectors, axis=1)
        norm_query = np.linalg.norm(query_vector)
        
        similarities = dot_product / (norms_vectors * norm_query + 1e-9)
        
        # Get top candidates (fetch more than top_k, then filter by threshold)
        num_candidates = min(len(self._documents), top_k + 3)
        top_indices = np.argsort(similarities)[::-1][:num_candidates]
        
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            doc = self._documents[idx]
            
            # Adaptive threshold by document type
            threshold = 0.20 if doc["type"] in ("holding", "trade") else 0.30
            
            if score > threshold:
                results.append({
                    "source": doc.get("source", f"portfolio_{doc['type']}"),
                    "doc_id": doc["id"],
                    "content": doc["text"],
                    "score": score,
                    "data": doc["data"],
                    "type": doc["type"]
                })
            
            if len(results) >= top_k:
                break
                
        return results

    def clear(self):
        self._documents = []
        self._vectors = None


# Singleton instance
portfolio_rag = PortfolioRAG.get_instance()
