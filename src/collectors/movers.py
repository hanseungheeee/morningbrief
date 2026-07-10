"""감시 리스트에서 그날의 시장 무버(상승/하락 상위)를 뽑는다. (출력·저장은 하지 않음)

Finnhub 무료 티어에 gainers/losers 엔드포인트가 없어(2026-07 실측 확인),
MOVER_UNIVERSE 대형주 리스트를 yfinance 로 일괄 조회해 등락률 상위/하위를 뽑는다.
"""

from __future__ import annotations

import yfinance as yf

from config import MOVER_UNIVERSE, MOVERS_TOP_N, WATCH_TICKERS


def _compute_change(closes) -> tuple[float, float, float] | None:
    """종가 시리즈에서 (현재가, 등락폭, 등락률)을 계산한다. 데이터 부족 시 None."""
    closes = closes.dropna()
    if len(closes) < 2:
        return None
    current = float(closes.iloc[-1])
    previous = float(closes.iloc[-2])
    if not previous:
        return None
    change = current - previous
    return current, change, change / previous * 100


def _compute_breadth(rows: list[dict]) -> dict | None:
    """감시 유니버스 전체 등락으로 시장 폭(breadth)을 집계한다.

    상승/하락 종목 수·비율과 평균 등락률로 "오늘 시장 전반의 힘"을 한눈에 보여준다.
    데이터가 없으면 None.
    """
    if not rows:
        return None
    total = len(rows)
    up = sum(1 for r in rows if r["change_pct"] > 0)
    down = sum(1 for r in rows if r["change_pct"] < 0)
    flat = total - up - down
    avg = sum(r["change_pct"] for r in rows) / total
    return {
        "total": total,
        "up": up,
        "down": down,
        "flat": flat,
        "up_pct": round(up / total * 100, 1),
        "avg_change_pct": round(avg, 2),
    }


def collect_movers() -> dict:
    """감시 리스트를 일괄 조회해 상승/하락 상위 N 종목과 시장 폭을 함께 뽑는다.

    관심 종목(WATCH_TICKERS)은 CP5 섹션에서 이미 다루므로 무버 선정에서만 제외하되,
    시장 폭(breadth)은 유니버스 전체(관심주 포함)를 대상으로 집계한다.
    반환: {"gainers": [...], "losers": [...], "breadth": {...}|None}.
    개별 티커 데이터 이상은 건너뛰고, 전체 조회 실패 시에만 예외를 던진다.
    """
    symbols = list(MOVER_UNIVERSE)
    # 개별 history() 반복 대신 일괄 다운로드 (120개 기준 10초 이내)
    data = yf.download(symbols, period="5d", group_by="ticker",
                       threads=True, progress=False)
    if data.empty:
        raise RuntimeError("무버 감시 리스트 일괄 조회 결과가 비어 있음")

    all_rows: list[dict] = []  # 유니버스 전체 (breadth 용)
    available = {col[0] for col in data.columns}  # 실제로 응답에 포함된 티커
    for symbol in symbols:
        if symbol not in available:
            print(f"[경고] 무버 후보 {symbol} 응답 없음, 건너뜀")
            continue
        try:
            computed = _compute_change(data[symbol]["Close"])
        except Exception as exc:  # 하나 실패해도 전체는 계속
            print(f"[경고] 무버 후보 {symbol} 계산 실패: {exc}")
            continue
        if computed is None:
            continue
        current, change, change_pct = computed
        all_rows.append({
            "ticker": symbol,
            "name": MOVER_UNIVERSE[symbol],
            "price": round(current, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
        })

    breadth = _compute_breadth(all_rows)

    # 무버 선정: 관심주(WATCH_TICKERS)는 CP5 섹션과 중복되므로 제외
    rows = [r for r in all_rows if r["ticker"] not in WATCH_TICKERS]
    rows.sort(key=lambda r: r["change_pct"], reverse=True)
    gainers = [r for r in rows if r["change_pct"] > 0][:MOVERS_TOP_N]
    losers = [r for r in rows if r["change_pct"] < 0][-MOVERS_TOP_N:][::-1]  # 많이 내린 순
    return {"gainers": gainers, "losers": losers, "breadth": breadth}
