"""관심 종목 등락을 yfinance로 수집한다. (출력·저장은 하지 않음)"""

from __future__ import annotations

import yfinance as yf

from config import WATCH_TICKERS


def _fetch_stock(symbol: str, name: str) -> dict:
    """종목 하나의 종가·등락률·등락폭을 조회한다.

    최근 종가 2개를 받아 전일 대비 변화를 계산한다. (지수 수집과 동일한 방식)
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
        "ticker": symbol,
        "name": name,
        "price": round(current, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
    }


def collect_stocks() -> list[dict]:
    """관심 종목 전체를 수집한다. 개별 실패는 건너뛰고 계속한다.

    반환은 등락률 절대값 큰 순(움직임이 큰 종목 먼저)으로 정렬한다.
    """
    results: list[dict] = []
    for symbol, name in WATCH_TICKERS.items():
        try:
            results.append(_fetch_stock(symbol, name))
        except Exception as exc:  # 하나 실패해도 전체는 계속
            print(f"[경고] {name}({symbol}) 수집 실패: {exc}")

    results.sort(key=lambda r: abs(r["change_pct"]), reverse=True)
    return results
