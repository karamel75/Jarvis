"""Marchés (Yahoo Finance via yfinance, gratuit) : indices, actions, crypto, devises."""
from __future__ import annotations

import logging

from jarvis.tools import ToolContext, ToolError, tool

log = logging.getLogger("jarvis.markets")


def quotes(symbols: dict[str, str]) -> list[dict]:
    import yfinance as yf

    tickers = list(symbols.values())
    data = yf.download(tickers, period="5d", interval="1d", progress=False, group_by="ticker", auto_adjust=False)
    rows = []
    for name, tk in symbols.items():
        try:
            closes = (data[tk]["Close"] if len(tickers) > 1 else data["Close"]).dropna()
            if hasattr(closes, "columns"):  # certaines versions renvoient un DataFrame d'une colonne
                closes = closes.iloc[:, 0]
            last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
            rows.append({"nom": name, "symbole": tk, "cours": round(last, 2),
                         "variation_pct": round((last - prev) / prev * 100, 2)})
        except Exception:
            log.debug("cours indisponible pour %s", tk, exc_info=True)
    return rows


@tool(
    "get_markets",
    "Cours et variation du jour. Sans paramètre : la liste de surveillance de Monsieur (CAC 40, S&P 500, "
    "Nasdaq, Bitcoin, euro/dollar…). Sinon donnez des symboles Yahoo (AAPL, MC.PA, NVDA, ETH-USD). "
    "Affiche une carte holographique.",
    {"symbols": {"type": "array", "items": {"type": "string"}}},
)
def get_markets(ctx: ToolContext, symbols: list[str] | None = None):
    watch = {s: s for s in symbols} if symbols else dict(ctx.cfg.get_path("markets.watchlist", {}))
    if not watch:
        raise ToolError("Aucun symbole.")
    rows = quotes(watch)
    if not rows:
        raise ToolError("Les marchés ne répondent pas pour le moment.")
    ctx.card("markets", "Marchés", rows=rows)
    return rows
