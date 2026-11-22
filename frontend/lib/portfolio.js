const roundMoney = (value) => Math.sign(value) * Math.round((Math.abs(value) * (1 + Number.EPSILON)) * 100) / 100;
const roundQuantity = (value) => Number(value.toFixed(8));
const symbol = (value) => String(value || "").trim().toUpperCase();
const finite = (value) => typeof value === "number" && Number.isFinite(value);

export function calculatePortfolio(snapshot, trades) {
  const positions = new Map();
  const aliases = new Map();
  const tradeHistory = [];
  const invalidTrades = [];

  for (const holding of snapshot?.holdings_json || []) {
    const ticker = symbol(holding.ticker || holding.isin);
    if (!ticker) continue;
    const quantity = Number(holding.quantity || 0);
    const avgBuyPrice = Number(holding.avgBuyPrice ?? holding.avg_buy_price ?? 0);
    let currentPrice = holding.currentPrice ?? holding.current_price ?? null;
    // Legacy imports sometimes substituted acquisition cost for a missing quote.
    if (!snapshot.coverage_end && !holding.priceSource && currentPrice === avgBuyPrice) currentPrice = null;
    const row = {
      ...holding, ticker, quantity, avgBuyPrice,
      currentPrice: finite(currentPrice) ? currentPrice : null,
      priceSource: finite(currentPrice) ? holding.priceSource || "STATEMENT" : null,
      priceAsOf: finite(currentPrice) ? holding.priceAsOf || snapshot.coverage_end || null : null,
    };
    if (row.status === "REALIZED") {
      tradeHistory.push({
        ...row,
        realizedPnl: row.realizedPnl ?? (finite(row.sellPrice) ? roundMoney((row.sellPrice - avgBuyPrice) * quantity) : null),
      });
      continue;
    }
    if (quantity <= 0) continue;
    const isin = symbol(row.isin);
    const key = aliases.get(ticker) || (isin && aliases.get(isin)) || ticker;
    aliases.set(ticker, key);
    if (isin) aliases.set(isin, key);
    const existing = positions.get(key);
    if (existing) {
      const combined = roundQuantity(existing.quantity + quantity);
      existing.avgBuyPrice = (existing.quantity * existing.avgBuyPrice + quantity * avgBuyPrice) / combined;
      existing.quantity = combined;
      if (existing.currentPrice === null && row.currentPrice !== null) {
        existing.currentPrice = row.currentPrice;
        existing.priceSource = row.priceSource;
        existing.priceAsOf = row.priceAsOf;
      }
      if (existing.ticker === isin && ticker !== isin) existing.ticker = ticker;
      if (!existing.isin && isin) existing.isin = isin;
    } else {
      positions.set(key, { ...row, status: "UNREALIZED" });
    }
  }

  for (const trade of trades) {
    const ticker = symbol(trade.ticker);
    const key = aliases.get(ticker) || ticker;
    const position = positions.get(key);
    const quantity = Number(trade.quantity);
    const price = Number(trade.price);
    if (!ticker || !finite(quantity) || !finite(price) || quantity <= 0 || price <= 0 ||
        !["BUY", "SELL"].includes(trade.transaction_type)) {
      invalidTrades.push(trade.id);
      continue;
    }

    if (trade.transaction_type === "BUY") {
      if (position) {
        const combined = roundQuantity(position.quantity + quantity);
        position.avgBuyPrice = (position.quantity * position.avgBuyPrice + quantity * price) / combined;
        position.quantity = combined;
      } else {
        positions.set(key, {
          ticker, name: ticker, quantity, avgBuyPrice: price, assetType: "STOCK",
          status: "UNREALIZED", currentPrice: null, priceSource: null, priceAsOf: null,
        });
      }
      continue;
    }
    if (!position || roundQuantity(position.quantity - quantity) < 0) {
      invalidTrades.push(trade.id);
      continue;
    }
    tradeHistory.push({
      ticker: position.ticker, name: position.name, isin: position.isin,
      assetType: position.assetType, sector: position.sector,
      quantity, avgBuyPrice: position.avgBuyPrice, sellPrice: price,
      realizedPnl: roundMoney((price - position.avgBuyPrice) * quantity),
      sellDate: trade.trade_date, status: "REALIZED",
    });
    position.quantity = roundQuantity(position.quantity - quantity);
    if (!position.quantity) positions.delete(key);
  }

  const holdings = [...positions.values()].map((h) => {
    const investedCost = roundMoney(h.quantity * h.avgBuyPrice);
    const marketValue = h.currentPrice === null ? null : roundMoney(h.quantity * h.currentPrice);
    return { ...h, investedCost, marketValue, unrealizedPnl: marketValue === null ? null : roundMoney(marketValue - investedCost) };
  });
  const investedCost = roundMoney(holdings.reduce((total, h) => total + h.investedCost, 0));
  const pricedHoldings = holdings.filter((h) => h.marketValue !== null);
  const marketValue = pricedHoldings.length === holdings.length
    ? roundMoney(pricedHoldings.reduce((total, h) => total + h.marketValue, 0)) : null;
  const sectorCosts = new Map();
  for (const h of holdings) {
    const sector = h.sector || "Other";
    sectorCosts.set(sector, (sectorCosts.get(sector) || 0) + h.investedCost);
  }
  return {
    holdings, tradeHistory, invalidTrades, investedCost, marketValue,
    unrealizedPnl: marketValue === null ? null : roundMoney(marketValue - investedCost),
    pricedHoldingsCount: pricedHoldings.length,
    realizedPnlTotal: tradeHistory.some((trade) => trade.realizedPnl == null)
      ? null : roundMoney(tradeHistory.reduce((total, trade) => total + trade.realizedPnl, 0)),
    sectorAllocation: Object.fromEntries([...sectorCosts].map(([sector, cost]) => [
      sector, investedCost ? roundMoney(100 * cost / investedCost) : 0,
    ])),
  };
}

export function toAiHoldings(holdings) {
  return holdings.map((h) => ({
    isin: h.isin || null,
    ticker: h.ticker,
    name: h.name || h.ticker,
    quantity: h.quantity,
    avg_buy_price: h.avgBuyPrice,
    asset_type: h.assetType === "MF" ? "MUTUAL_FUND" : h.assetType || "STOCK",
    sector: h.sector || null,
    status: h.status,
    current_price: h.currentPrice ?? null,
    invested_cost: h.investedCost ?? null,
    market_value: h.marketValue ?? null,
    price_source: h.priceSource ?? null,
    price_as_of: h.priceAsOf ?? null,
    sell_price: h.sellPrice ?? null,
    realized_pnl: h.realizedPnl ?? null,
    buy_date: h.buyDate || null,
    sell_date: h.sellDate || null,
  }));
}
