"""Finnhub 시장 뉴스·종목별 뉴스 수집. (출력·저장은 하지 않음)"""

from __future__ import annotations

import time
from datetime import date, timedelta

import requests

from config import (
    FINNHUB_API_KEY,
    FINNHUB_COMPANY_NEWS_URL,
    FINNHUB_NEWS_URL,
    NEWS_CATEGORIES,
    NEWS_MAX_ITEMS,
    NEWS_RECENT_HOURS,
    STOCK_NEWS_DAYS,
    STOCK_NEWS_MAX_PER_TICKER,
    WATCH_TICKERS,
)


def _fetch_category(category: str) -> list[dict]:
    """카테고리 하나의 뉴스를 조회한다. 실패 시 빈 리스트."""
    try:
        resp = requests.get(
            FINNHUB_NEWS_URL,
            params={"category": category, "token": FINNHUB_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception as exc:
        print(f"[경고] 뉴스({category}) 수집 실패: {exc}")
        return []


def collect_news() -> list[dict]:
    """당일 시장 뉴스를 카테고리별로 모아 최근·상위 N개만 반환한다.

    반환 항목: headline, summary, source, datetime(unix), url, related
    """
    if not FINNHUB_API_KEY:
        raise RuntimeError(
            "FINNHUB_API_KEY 가 없습니다. .env 에 키를 추가하세요. (.env.example 참고)"
        )

    cutoff = int(time.time()) - NEWS_RECENT_HOURS * 3600  # 최근 기사 기준 시각

    articles: list[dict] = []
    seen_ids: set = set()  # 카테고리 간 중복 제거용
    for category in NEWS_CATEGORIES:
        for item in _fetch_category(category):
            # 너무 오래된 기사 제외
            if item.get("datetime", 0) < cutoff:
                continue
            # 중복 기사 제외
            key = item.get("id") or item.get("url")
            if key in seen_ids:
                continue
            seen_ids.add(key)

            articles.append({
                "headline": item.get("headline", ""),
                "summary": item.get("summary", ""),
                "source": item.get("source", ""),
                "datetime": item.get("datetime", 0),
                "url": item.get("url", ""),
                "related": item.get("related", ""),
            })

    # 최신순 정렬 후 상위 N개
    articles.sort(key=lambda a: a["datetime"], reverse=True)
    return articles[:NEWS_MAX_ITEMS]


def _fetch_company_news(symbol: str) -> list[dict]:
    """종목 하나의 최근 뉴스를 조회한다. 실패 시 빈 리스트."""
    today = date.today()
    since = today - timedelta(days=STOCK_NEWS_DAYS)
    try:
        resp = requests.get(
            FINNHUB_COMPANY_NEWS_URL,
            params={
                "symbol": symbol,
                "from": since.isoformat(),
                "to": today.isoformat(),
                "token": FINNHUB_API_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception as exc:
        print(f"[경고] 종목 뉴스({symbol}) 수집 실패: {exc}")
        return []


def collect_stock_news() -> dict[str, list[str]]:
    """관심 종목별 최근 뉴스 헤드라인을 수집한다.

    반환: {티커: [헤드라인, ...]} — 종목당 최신순 상위 N개, 뉴스 없으면 빈 리스트.
    """
    if not FINNHUB_API_KEY:
        raise RuntimeError(
            "FINNHUB_API_KEY 가 없습니다. .env 에 키를 추가하세요. (.env.example 참고)"
        )

    result: dict[str, list[str]] = {}
    for symbol in WATCH_TICKERS:
        items = _fetch_company_news(symbol)
        # 최신순 정렬 후 상위 N개 헤드라인만 (토큰 절약)
        items.sort(key=lambda a: a.get("datetime", 0), reverse=True)
        headlines: list[str] = []
        for item in items:
            headline = (item.get("headline") or "").strip()
            if headline and headline not in headlines:  # 동일 헤드라인 중복 제거
                headlines.append(headline)
            if len(headlines) >= STOCK_NEWS_MAX_PER_TICKER:
                break
        result[symbol] = headlines
    return result
