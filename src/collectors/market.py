"""지수·매크로 티커를 yfinance로 수집한다. (출력·저장은 하지 않음)"""

from __future__ import annotations

import yfinance as yf

from config import INDEX_TICKERS, MACRO_TICKERS


def _fetch_ticker(symbol: str, name: str) -> dict:
    """티커 하나의 종가·등락률·등락 포인트를 조회한다.

    최근 2 거래일 종가를 받아 전일 대비 변화를 계산한다.
    """
    hist = yf.Ticker(symbol).history(period="5d")

    if hist.empty or len(hist) < 2:
        raise ValueError("가격 데이터 부족")

    closes = hist["Close"].dropna()
    if len(closes) < 2:
        raise ValueError("종가 데이터 부족")

    current = float(closes.iloc[-1])   # 당일 종가
    previous = float(closes.iloc[-2])  # 전일 종가
    change = current - previous
    change_pct = (change / previous * 100) if previous else 0.0

    return {
        "symbol": symbol,
        "name": name,
        "price": round(current, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
    }


def _collect(tickers: dict[str, str]) -> list[dict]:
    """티커 dict를 순회하며 수집한다. 개별 실패는 건너뛴다."""
    results: list[dict] = []
    for symbol, name in tickers.items():
        try:
            results.append(_fetch_ticker(symbol, name))
        except Exception as exc:  # 하나 실패해도 전체는 계속
            print(f"[경고] {name}({symbol}) 수집 실패: {exc}")
    return results


def collect_indices() -> list[dict]:
    """지수 티커를 수집한다."""
    return _collect(INDEX_TICKERS)


def collect_macros() -> list[dict]:
    """매크로 티커를 수집한다."""
    return _collect(MACRO_TICKERS)
