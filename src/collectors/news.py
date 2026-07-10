"""Finnhub 시장 뉴스·종목별 뉴스 수집과 정책 뉴스 필터. (출력·저장은 하지 않음)"""

from __future__ import annotations

import re
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
    POLICY_KEYWORDS,
    STOCK_NEWS_DAYS,
    STOCK_NEWS_MAX_PER_TICKER,
    STOCK_NEWS_SUMMARY_MAX,
    WATCH_TICKERS,
)

# 정책 키워드를 단어 경계 정규식으로 컴파일 ("fed"가 confederate 등에 걸리지 않게)
_POLICY_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in POLICY_KEYWORDS) + r")\b",
    re.IGNORECASE,
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


def collect_stock_news(symbols: list[str] | None = None) -> dict[str, list[dict]]:
    """종목별 최근 뉴스(헤드라인 + 요약)를 수집한다.

    symbols=None 이면 관심 종목(WATCH_TICKERS) 전체. 무버 등 임의 종목 리스트에도 재활용.
    반환: {티커: [{"headline": ..., "summary": ...}, ...]} — 종목당 최신순 상위 N개.
    요약(summary)은 헤드라인만으로 안 드러나는 등락 원인을 해설이 짚도록 함께 준다.
    뉴스 없으면 빈 리스트.
    """
    if not FINNHUB_API_KEY:
        raise RuntimeError(
            "FINNHUB_API_KEY 가 없습니다. .env 에 키를 추가하세요. (.env.example 참고)"
        )

    result: dict[str, list[dict]] = {}
    for symbol in (symbols if symbols is not None else list(WATCH_TICKERS)):
        items = _fetch_company_news(symbol)
        # 최신순 정렬 후 상위 N개 (토큰 절약)
        items.sort(key=lambda a: a.get("datetime", 0), reverse=True)
        picked: list[dict] = []
        seen: set = set()
        for item in items:
            headline = (item.get("headline") or "").strip()
            if not headline or headline in seen:  # 동일 헤드라인 중복 제거
                continue
            seen.add(headline)
            summary = (item.get("summary") or "").strip()
            if len(summary) > STOCK_NEWS_SUMMARY_MAX:  # 너무 길면 잘라 토큰 절약
                summary = summary[:STOCK_NEWS_SUMMARY_MAX].rstrip() + "…"
            picked.append({"headline": headline, "summary": summary})
            if len(picked) >= STOCK_NEWS_MAX_PER_TICKER:
                break
        result[symbol] = picked
    return result


def filter_policy_news(news: list[dict]) -> list[dict]:
    """수집된 시장 뉴스에서 연준·정책 관련 기사만 골라낸다.

    추가 API 호출 없이 이미 수집한 뉴스(headline·summary)를 키워드로 거른다.
    기존 뉴스 목록은 그대로 두고 별도 리스트를 반환하며, 해당 기사가 없으면 빈 리스트.
    """
    matched: list[dict] = []
    for article in news:
        text = f"{article.get('headline', '')} {article.get('summary', '')}"
        if _POLICY_PATTERN.search(text):
            matched.append(article)
    return matched
