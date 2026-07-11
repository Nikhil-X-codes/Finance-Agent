"""Portfolio RAG - vectorize holdings and trades for Q&A retrieval."""

from __future__ import annotations

import asyncio
import numpy as np
from typing import Any

from src.services.embedding_service import get_embedding_service
from src.config.settings import settings


class PortfolioRAG:
    """RAG engine that retrieves from portfolio/trade history context dynamically."""
    
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
    
    async def index_portfolio(self, holdings: list[dict], trades: list[dict]):
        """Build vector index from active holdings + trade history."""
        documents = []
        
        # 1. Index active holdings
        for h in holdings:
            qty = float(h.get("quantity") or 0.0)
            if qty <= 0:
                continue
                
            text = (
                f"User currently holds active position of {qty} shares of {h.get('ticker')} "
                f"({h.get('name')}) bought at average buy price of ₹{float(h.get('avg_buy_price') or 0.0):.2f}. "
                f"Current sector is {h.get('sector', 'Other')}. "
                f"Asset type is {h.get('asset_type', 'STOCK')}."
            )
            
            documents.append({
                "id": f"holding_{h.get('ticker')}",
                "text": text,
                "type": "holding",
                "data": h
            })
        
        # 2. Index realized trades (completed sells)
        for t in trades:
            text = (
                f"User completed trade history for {t.get('ticker')} ({t.get('name')}). "
                f"Bought {float(t.get('quantity') or 0.0)} shares at ₹{float(t.get('avg_buy_price') or t.get('buy_price') or 0.0):.2f} "
                f"and sold them at ₹{float(t.get('sell_price') or 0.0):.2f}. "
                f"Realized profit/loss (P&L) was ₹{float(t.get('realized_pnl') or 0.0):,.2f}."
            )
            
            documents.append({
                "id": f"trade_{t.get('ticker')}",
                "text": text,
                "type": "trade",
                "data": t
            })
            
        # 3. Index portfolio summary metrics
        if holdings:
            total_invested = sum(float(h.get("quantity") or 0.0) * float(h.get("avg_buy_price") or 0.0) for h in holdings)
            tickers = [h.get("ticker") for h in holdings if float(h.get("quantity") or 0.0) > 0]
            sectors = set(h.get("sector") for h in holdings if h.get("sector"))
            
            summary_text = (
                f"User portfolio overview summary: has {len(tickers)} active holdings "
                f"with total invested capital value of ₹{total_invested:,.2f}. "
                f"Active tickers owned: {', '.join(tickers)}. "
                f"Sectors represented: {', '.join(sectors) if sectors else 'None'}."
            )
            documents.append({
                "id": "portfolio_summary",
                "text": summary_text,
                "type": "summary",
                "data": {"holdings_count": len(tickers), "total_invested": total_invested}
            })
            
        # 4. Index trade summary metrics
        if trades:
            total_pnl = sum(float(t.get("realized_pnl") or 0.0) for t in trades)
            
            # Find best and worst trade by realized P&L
            best_trade = max(trades, key=lambda x: float(x.get("realized_pnl") or 0.0))
            worst_trade = min(trades, key=lambda x: float(x.get("realized_pnl") or 0.0))
            
            summary_text = (
                f"User completed trade history summary: completed {len(trades)} trades "
                f"with total realized profit/loss P&L of ₹{total_pnl:,.2f}. "
                f"Best trade was {best_trade.get('ticker')} with profit of ₹{float(best_trade.get('realized_pnl') or 0.0):,.2f}. "
                f"Worst trade was {worst_trade.get('ticker')} with loss/PNL of ₹{float(worst_trade.get('realized_pnl') or 0.0):,.2f}."
            )
            documents.append({
                "id": "trade_summary",
                "text": summary_text,
                "type": "summary",
                "data": {"trades_count": len(trades), "total_pnl": total_pnl}
            })
            
        self._documents = documents
        
        # Concurrently generate embeddings
        if documents:
            embedder = self._get_embedder()
            tasks = [embedder.embed(d["text"]) for d in documents]
            vectors = await asyncio.gather(*tasks)
            self._vectors = np.array(vectors)
            print(f"✅ Indexed {len(documents)} portfolio RAG documents")
        else:
            self._vectors = None
            print("⚠️ No documents to index for portfolio RAG")
            
    async def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Search portfolio records matching semantic query."""
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
        
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score > 0.25:  # Relevance threshold
                doc = self._documents[idx]
                results.append({
                    "source": f"portfolio_{doc['type']}",
                    "doc_id": doc["id"],
                    "content": doc["text"],
                    "score": score,
                    "data": doc["data"],
                    "type": doc["type"]
                })
        return results

    def clear(self):
        self._documents = []
        self._vectors = None


# Singleton instance
portfolio_rag = PortfolioRAG.get_instance()
