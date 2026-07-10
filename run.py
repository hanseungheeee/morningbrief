"""진입점 - 데이터를 수집해 JSON으로 저장·출력하고 HTML 브리핑을 렌더링한다."""

from __future__ import annotations

import argparse
import json
from datetime import datetime

from config import DATA_DIR
from src.analysis.commentary import generate_commentary
from src.collectors.calendar import collect_calendar
from src.collectors.crypto import collect_crypto
from src.collectors.market import collect_indices, collect_macros, collect_sectors
from src.collectors.movers import collect_movers
from src.collectors.news import collect_news, collect_stock_news, filter_policy_news
from src.collectors.stocks import collect_stocks
from src.notify.telegram import send_notification
from src.render.builder import render

# ANSI 색상 코드
GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"


def collect_all(with_commentary: bool = True) -> dict:
    """수집(시장+암호화폐+종목) → 뉴스 수집 → Claude 해설 → 하나의 dict로 묶는다."""
    now = datetime.now()
    market = {
        "indices": collect_indices(),
        "macros": collect_macros(),
    }
    crypto = collect_crypto()

    # 섹터 로테이션 (S&P 11개 섹터 ETF, 실패해도 파이프라인은 계속)
    try:
        sectors = collect_sectors()
    except Exception as exc:
        print(f"[경고] 섹터 수집 단계 실패: {exc}")
        sectors = []

    # 관심 종목 등락 수집 (실패해도 파이프라인은 계속)
    try:
        stocks = collect_stocks()
    except Exception as exc:
        print(f"[경고] 종목 수집 단계 실패: {exc}")
        stocks = []

    # 뉴스 수집 (실패해도 파이프라인은 계속)
    try:
        news = collect_news()
    except Exception as exc:
        print(f"[경고] 뉴스 수집 단계 실패: {exc}")
        news = []

    # 연준·정책 뉴스 선별 (추가 API 호출 없음, 실패해도 계속)
    try:
        policy_news = filter_policy_news(news)
    except Exception as exc:
        print(f"[경고] 정책 뉴스 필터 실패: {exc}")
        policy_news = []

    # 시장 무버 추출 (실패해도 파이프라인은 계속)
    try:
        movers = collect_movers()
    except Exception as exc:
        print(f"[경고] 무버 수집 단계 실패: {exc}")
        movers = {"gainers": [], "losers": [], "breadth": None}

    # 종목별 뉴스 수집 (실패해도 파이프라인은 계속)
    try:
        stock_news = collect_stock_news()
    except Exception as exc:
        print(f"[경고] 종목 뉴스 수집 단계 실패: {exc}")
        stock_news = {}

    # 무버 종목 뉴스 수집 (실패해도 파이프라인은 계속)
    try:
        mover_tickers = [m["ticker"] for m in movers["gainers"] + movers["losers"]]
        mover_news = collect_stock_news(mover_tickers) if mover_tickers else {}
    except Exception as exc:
        print(f"[경고] 무버 뉴스 수집 단계 실패: {exc}")
        mover_news = {}

    # 경제 캘린더 수집 (오늘 발표 지표 + 예정 일정, 실패해도 파이프라인은 계속)
    try:
        calendar = collect_calendar(now)
    except Exception as exc:
        print(f"[경고] 경제 캘린더 수집 단계 실패: {exc}")
        calendar = {"today_date": "", "today": [], "upcoming": []}

    # Claude 해설 (--no-commentary 면 건너뜀, 실패 시 None)
    commentary = None
    if with_commentary:
        commentary = generate_commentary(market, crypto, news, stocks, stock_news,
                                         movers, mover_news, policy_news,
                                         calendar["today"], sectors,
                                         calendar["upcoming"])

    return {
        "date": now.strftime("%Y-%m-%d"),
        "collected_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "market": market,
        "sectors": sectors,
        "crypto": crypto,
        "stocks": stocks,
        "movers": movers,
        "news": news,
        "policy_news": policy_news,
        "stock_news": stock_news,
        "mover_news": mover_news,
        # 경제 캘린더: 오늘 발표 결과 + 예정 일정 (calendar_comment 는 commentary 안)
        "calendar_today": calendar["today"],
        "calendar_upcoming": calendar["upcoming"],
        "calendar_today_date": calendar["today_date"],
        # 오늘 발표 지표 해설을 top-level 로도 미러링 (commentary 없으면 None)
        "calendar_comment": (commentary or {}).get("calendar_comment"),
        # 종목·무버·정책 코멘트는 commentary 안에 포함 (stock/mover_comments, policy_comment)
        "commentary": commentary,
    }


def save_json(payload: dict) -> str:
    """수집 결과를 data/YYYY-MM-DD.json 으로 저장한다."""
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{payload['date']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return str(path)


def _format_change(change_pct: float | None, change: float | None = None) -> str:
    """등락률(과 등락 포인트)을 화살표·색상 텍스트로 만든다."""
    if change_pct is None:
        return "  -  "

    change_pct = change_pct + 0.0  # 음의 0(-0.0)을 0.0으로 정규화
    if change is not None:
        change = change + 0.0

    arrow = "▲" if change_pct >= 0 else "▼"
    color = GREEN if change_pct >= 0 else RED
    sign = "+" if change_pct >= 0 else ""

    body = f"{arrow} {sign}{change_pct:.2f}%"
    if change is not None:
        body += f" ({sign}{change:.2f})"
    return f"{color}{body}{RESET}"


def _print_section(title: str, rows: list[dict], with_points: bool) -> None:
    """카테고리 하나를 표처럼 정렬 출력한다."""
    print(f"\n[{title}]")
    if not rows:
        print("  (수집된 데이터 없음)")
        return

    for row in rows:
        name = row["name"]
        price = row["price"]
        price_str = f"{price:,.2f}" if price is not None else "-"
        change = row.get("change") if with_points else None
        change_str = _format_change(row.get("change_pct"), change)
        print(f"  {name:<16} {price_str:>14}   {change_str}")


def print_report(payload: dict) -> None:
    """수집 결과를 콘솔에 사람이 읽기 좋게 출력한다."""
    print("=" * 48)
    print(f" 미국 증시 아침 브리핑 - {payload['date']}")
    print(f" 수집 시각: {payload['collected_at']}")
    print("=" * 48)

    _print_section("지수", payload["market"]["indices"], with_points=True)
    _print_section("매크로", payload["market"]["macros"], with_points=True)
    _print_section("섹터 (강→약)", payload.get("sectors", []), with_points=False)
    _print_section("암호화폐 (USD)", payload["crypto"], with_points=False)
    _print_section("주요 종목", payload.get("stocks", []), with_points=True)
    movers = payload.get("movers") or {}
    _print_breadth(movers.get("breadth"))
    _print_section("오늘의 무버 · 상승", movers.get("gainers", []), with_points=True)
    _print_section("오늘의 무버 · 하락", movers.get("losers", []), with_points=True)
    _print_calendar(payload)
    print()


def _print_breadth(breadth: dict | None) -> None:
    """시장 폭(감시 유니버스 상승/하락 비율)을 한 줄로 출력한다."""
    if not breadth:
        return
    avg = breadth["avg_change_pct"] + 0.0
    color = GREEN if avg >= 0 else RED
    print(f"\n[시장 폭] {breadth['total']}종목 중 상승 {breadth['up']} / 하락 "
          f"{breadth['down']} (상승 {breadth['up_pct']:.0f}%) · 평균 "
          f"{color}{avg:+.2f}%{RESET}")


# 예상 대비 상회/하회 라벨 (콘솔용)
_SURPRISE_LABEL = {"above": "상회", "below": "하회", "inline": "부합"}


def _print_calendar(payload: dict) -> None:
    """경제 캘린더(오늘 발표 결과 + 예정 일정)를 콘솔에 출력한다."""
    today = payload.get("calendar_today") or []
    upcoming = payload.get("calendar_upcoming") or []

    print(f"\n[오늘의 경제 지표 · 기준일 {payload.get('calendar_today_date', '')}]")
    if not today:
        print("  (발표된 주요 지표 없음)")
    else:
        for e in today:
            tag = _SURPRISE_LABEL.get(e.get("surprise") or "", "")
            tag = f"  ({tag})" if tag else ""
            print(f"  {e['name']:<34} 실제 {e.get('actual') or '-':>9} | "
                  f"예상 {e.get('consensus') or '-':>9} | 이전 {e.get('previous') or '-':>9}{tag}")

    print("\n[예정 일정]")
    if not upcoming:
        print("  (예정된 주요 지표 없음)")
    else:
        for e in upcoming:
            cons = e.get("consensus")
            cons = f"  예상 {cons}" if cons else ""
            print(f"  {e['date']}({e['weekday']})  {e['name']}{cons}")


def render_step() -> None:
    """가장 최근 JSON을 읽어 HTML 브리핑을 생성한다."""
    index_path, archive_path = render()
    print(f"HTML 생성: {index_path}")
    print(f"아카이브 : {archive_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="미국 증시 아침 브리핑")
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="수집을 건너뛰고 저장된 최신 JSON으로 HTML만 생성",
    )
    parser.add_argument(
        "--no-commentary",
        action="store_true",
        help="Gemini 해설 없이 숫자·뉴스만 수집 (API 비용 절약)",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="텔레그램 알림 없이 실행 (테스트용)",
    )
    args = parser.parse_args()

    payload = None
    # --render-only 가 아니면 수집 → JSON 저장 → 콘솔 출력
    if not args.render_only:
        payload = collect_all(with_commentary=not args.no_commentary)
        path = save_json(payload)
        print_report(payload)
        print(f"저장 완료: {path}")

    # 렌더링 단계
    render_step()

    # 알림 단계 (전체 파이프라인 실행 시에만, --no-notify 면 건너뜀)
    if payload is not None and not args.no_notify:
        send_notification(payload)


if __name__ == "__main__":
    main()
