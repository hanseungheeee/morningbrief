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
    MARKET_CROSS_MAX_PER_TICKER,
    NEWS_CATEGORIES,
    NEWS_MAX_ITEMS,
    NEWS_RECENT_HOURS,
    POLICY_KEYWORDS,
    STOCK_NEWS_DAYS,
    STOCK_NEWS_MAX_PER_TICKER,
    STOCK_NEWS_SUMMARY_MAX_CHARS,
    TICKER_MATCH_NAMES,
    WATCH_TICKERS,
)

# 정책 키워드를 단어 경계 정규식으로 컴파일 ("fed"가 confederate 등에 걸리지 않게)
_POLICY_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in POLICY_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# 일부 뉴스 summary 에는 원본 HTML 태그(<p class=...> 등)가 섞여 온다. Gemini 로
# 넘기기 전에 태그를 벗기고 텍스트만 남긴다(노이즈·토큰 낭비 방지).
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


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


def _fetch_company_news(symbol: str, days: int) -> list[dict]:
    """종목 하나의 최근 days 일 뉴스를 조회한다. 실패 시 빈 리스트."""
    today = date.today()
    since = today - timedelta(days=days)
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


def _trim_summary(text: str) -> str:
    """뉴스 요약을 토큰 관리를 위해 STOCK_NEWS_SUMMARY_MAX_CHARS 로 자른다.

    잘릴 때는 마지막 공백에서 끊고 '…' 를 붙여 단어가 반쪽 나지 않게 한다.
    """
    text = _HTML_TAG_PATTERN.sub(" ", text or "")  # HTML 태그 제거
    text = " ".join(text.split())  # 개행·중복 공백 정리
    if len(text) <= STOCK_NEWS_SUMMARY_MAX_CHARS:
        return text
    cut = text[:STOCK_NEWS_SUMMARY_MAX_CHARS]
    space = cut.rfind(" ")
    if space > STOCK_NEWS_SUMMARY_MAX_CHARS * 0.6:  # 너무 짧게 잘리지 않을 때만 공백 기준
        cut = cut[:space]
    return cut.rstrip() + "…"


def collect_stock_news(
    symbols: list[str] | None = None,
    max_per_ticker: int = STOCK_NEWS_MAX_PER_TICKER,
    days: int = STOCK_NEWS_DAYS,
) -> dict[str, list[dict]]:
    """종목별 최근 뉴스를 헤드라인 + 요약(summary)으로 수집한다.

    symbols=None 이면 관심 종목(WATCH_TICKERS) 전체. 무버 등 임의 종목 리스트에도 재활용
    (무버는 근거 확보가 더 중요해 max_per_ticker 를 크게 넘겨 호출한다).
    반환: {티커: [{headline, summary, from_market:False}, ...]} — 종목당 최신순 상위 N개.
          뉴스 없으면 빈 리스트. summary 는 헤드라인의 "왜"를 담는 경우가 많아 함께 넘긴다.
    """
    if not FINNHUB_API_KEY:
        raise RuntimeError(
            "FINNHUB_API_KEY 가 없습니다. .env 에 키를 추가하세요. (.env.example 참고)"
        )

    result: dict[str, list[dict]] = {}
    for symbol in (symbols if symbols is not None else list(WATCH_TICKERS)):
        items = _fetch_company_news(symbol, days)
        # 최신순 정렬 후 상위 N개 (headline + summary)
        items.sort(key=lambda a: a.get("datetime", 0), reverse=True)
        collected: list[dict] = []
        seen_headlines: set[str] = set()
        for item in items:
            headline = (item.get("headline") or "").strip()
            if not headline or headline in seen_headlines:  # 동일 헤드라인 중복 제거
                continue
            seen_headlines.add(headline)
            collected.append({
                "headline": headline,
                "summary": _trim_summary(item.get("summary") or ""),
                "from_market": False,  # 개별 company-news 근거
            })
            if len(collected) >= max_per_ticker:
                break
        result[symbol] = collected
    return result


def _compile_ticker_matchers() -> dict[str, tuple]:
    """티커별 (티커기호 정규식|None, 회사명 정규식|None) 을 미리 컴파일한다.

    둘 다 대소문자를 구분한다. 뉴스에서 회사·티커는 고유명사라 대문자로 표기되므로,
    대소문자를 구분하면 소문자 일반어 오탐을 막는다. (예: 'Target'(타깃)이 이란 기사
    본문의 소문자 동사 'target'에 붙거나, 'Arm'(Arm홀딩스)이 'arm'(팔)에 붙는 것 방지.)
    - 티커 기호: 길이 3+ 만 매칭(V·F·GM 등 1~2글자는 오탐이 커 제외, 회사명으로만 잡는다).
    - 회사명: TICKER_MATCH_NAMES 의 영문 별칭을 표기 그대로(대문자 시작) 단어 경계 매칭.
    """
    matchers: dict[str, tuple] = {}
    for ticker, names in TICKER_MATCH_NAMES.items():
        sym_re = None
        if len(ticker) >= 3:
            sym_re = re.compile(r"\b" + re.escape(ticker) + r"\b")  # 대소문자 구분
        name_re = None
        if names:
            # 대소문자 구분: 별칭은 이미 'Exxon'·'Target'처럼 고유명사 표기라
            # 소문자 동사·일반어(target/arm/booking 등)에는 걸리지 않는다.
            name_re = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b")
        matchers[ticker] = (sym_re, name_re)
    return matchers


def augment_ticker_news_with_market(
    ticker_news: dict[str, list[dict]],
    market_news: list[dict],
    max_per_ticker: int = MARKET_CROSS_MAX_PER_TICKER,
) -> dict[str, list[dict]]:
    """개별 종목 뉴스에, 그날 시장 전체 뉴스에서 그 종목이 언급된 기사를 보강한다.

    개별 company-news 에 근거가 없어도 "반도체 섹터 하락" 같은 시장 뉴스에 종목이
    언급되면 그것도 근거가 된다. 티커(길이 3+)와 영문 회사명 양쪽으로 매칭하고,
    이미 있는 헤드라인과 중복되면 건너뛴다. 종목당 최대 max_per_ticker 개만 추가.
    입력 dict 를 제자리에서 보강해 반환한다(억지 인과는 프롬프트 원칙으로 별도 방지).
    """
    if not market_news:
        return ticker_news

    matchers = _compile_ticker_matchers()
    for ticker, items in ticker_news.items():
        sym_re, name_re = matchers.get(ticker, (None, None))
        if sym_re is None and name_re is None:  # 매칭할 이름이 없으면 보강 불가
            continue
        existing = {i["headline"].lower() for i in items}
        added = 0
        for article in market_news:
            if added >= max_per_ticker:
                break
            headline = (article.get("headline") or "").strip()
            if not headline or headline.lower() in existing:
                continue
            # HTML 태그를 벗긴 텍스트로 매칭 (태그 속성값 오탐 방지)
            text = _HTML_TAG_PATTERN.sub(" ", f"{headline} {article.get('summary') or ''}")
            if (sym_re and sym_re.search(text)) or (name_re and name_re.search(text)):
                items.append({
                    "headline": headline,
                    "summary": _trim_summary(article.get("summary") or ""),
                    "from_market": True,  # 시장 뉴스 교차검색으로 보강한 근거
                })
                existing.add(headline.lower())
                added += 1
    return ticker_news


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
