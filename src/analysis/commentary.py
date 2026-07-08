"""Gemini API로 시장 해설 생성. (숫자·뉴스 근거만 사용, 억지 해석·투자추천 금지)"""

from __future__ import annotations

import json
import time

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MAX_TOKENS, GEMINI_MODEL

# 일시적(재시도하면 풀리는) 서버 오류. 나머지(400/401/403 등)는 재시도해도 소용없어 즉시 포기.
_RETRYABLE_CODES = {429, 500, 502, 503, 504}
_RETRYABLE_HINTS = ("unavailable", "overloaded", "high demand", "resource_exhausted",
                    "deadline", "timeout", "internal")
# 재시도 정책: 최초 1회 + 재시도 3회, 대기 2·4·8초 (지수 백오프)
_MAX_ATTEMPTS = 4
_BACKOFF_BASE = 2.0


def _is_retryable(exc: Exception) -> bool:
    """일시적 서버 오류인지 판단한다. (code 또는 메시지 키워드로 판별)"""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in _RETRYABLE_CODES:
        return True
    text = str(exc).lower()
    return any(hint in text for hint in _RETRYABLE_HINTS)

# 해설 원칙과 톤을 못박는 시스템 프롬프트
SYSTEM_PROMPT = """당신은 한국경제TV의 미국 증시 아침 브리핑을 쓰는 시장 해설가입니다.
차분한 해설체로, 과장 없이 사실 전달과 맥락 해석만 합니다.

반드시 지킬 원칙:
1. 제공된 숫자 데이터와 뉴스 헤드라인에 있는 정보만 사용한다. 숫자를 새로 지어내거나
   추측하지 않는다. 제공되지 않은 수치를 문장에 넣지 않는다.
2. 어떤 움직임의 근거가 뉴스에서 확인되지 않으면 "관련 뉴스에서 확인되지 않음"이라고
   명시하고, 억지 해석이나 그럴듯한 소설을 만들지 않는다.
3. 특정 종목의 매수/매도 추천을 절대 하지 않는다. 사실과 맥락만 전달한다.
4. 반드시 아래 형식의 순수 JSON만 출력한다. 마크다운 코드펜스나 설명 문장을 덧붙이지 않는다.

5. 종목 코멘트는 뉴스 근거가 있거나 등락이 큰 종목 위주로만 작성한다. 움직임이 미미하고
   관련 뉴스도 없는 종목은 생략해도 된다. 전 종목을 억지로 다 쓰지 않는다.
6. 무버(movers)는 그날 크게 움직인 종목이므로 "왜 움직였나"의 뉴스 근거가 특히 중요하다.
   해당 종목 뉴스에서 원인이 확인되면 연결하고, 확인되지 않으면 반드시
   "급등/급락 원인은 관련 뉴스에서 확인되지 않음"이라고 쓴다. 억지 해석 금지.

출력 JSON 형식:
{
  "market_summary": "3~4문장. 오늘 장 전체 분위기 요약 (지수 흐름 + 가장 큰 테마 1~2개)",
  "index_comment": "1~2문장. 지수가 이렇게 움직인 배경 (뉴스 근거)",
  "macro_comment": "1~2문장. 금리·유가·달러·VIX 중 의미있는 움직임 해석. 특히 금리/VIX 하락이 시장에 갖는 의미를 자연스럽게 설명",
  "crypto_comment": "1문장. 암호화폐 흐름",
  "key_topics": ["오늘 시장을 움직인 핵심 이슈 3~5개, 각 한 줄"],
  "stock_comments": [
    {"ticker": "NVDA", "name": "엔비디아", "comment": "1~2문장. 이 종목이 왜 이렇게 움직였나. 해당 종목 뉴스에 근거가 있으면 연결하고, 없으면 등락 사실만 담담히 서술"}
  ],
  "mover_comments": [
    {"ticker": "...", "name": "...", "direction": "up 또는 down", "comment": "1~2문장. 왜 이렇게 크게 움직였나. 뉴스 근거 필수, 근거 없으면 '급등/급락 원인은 관련 뉴스에서 확인되지 않음'"}
  ]
}
movers 데이터가 비어 있으면 mover_comments 는 빈 배열로 둔다."""

# 파싱 실패·API 실패 시 반환할 키 구조 (템플릿이 참조하는 키)
_KEYS = ["market_summary", "index_comment", "macro_comment", "crypto_comment", "key_topics",
         "stock_comments", "mover_comments"]


def _format_ticker_news(ticker_news: dict[str, list[str]] | None) -> str:
    """{티커: [헤드라인들]} 을 티커 단위 목록 텍스트로 만든다. (근거를 종목별로 고정)"""
    lines: list[str] = []
    for ticker, headlines in (ticker_news or {}).items():
        if headlines:
            lines.append(f"- {ticker}:")
            lines.extend(f"  - {h}" for h in headlines)
        else:
            lines.append(f"- {ticker}: (뉴스 없음)")
    return "\n".join(lines) if lines else "(수집된 종목 뉴스 없음)"


def _build_user_message(
    market: dict,
    crypto: list[dict],
    news: list[dict],
    stocks: list[dict] | None = None,
    stock_news: dict[str, list[str]] | None = None,
    movers: dict[str, list[dict]] | None = None,
    mover_news: dict[str, list[str]] | None = None,
) -> str:
    """숫자 데이터와 뉴스 헤드라인을 정리해 유저 메시지로 만든다."""
    # 숫자 데이터는 JSON 그대로 전달 (Claude가 값을 지어내지 않도록 근거 고정)
    numbers = json.dumps(
        {
            "market": market,
            "crypto": crypto,
            "stocks": stocks or [],
            "movers": movers or {"gainers": [], "losers": []},
        },
        ensure_ascii=False,
        indent=2,
    )

    # 뉴스는 헤드라인 목록으로 간결하게
    if news:
        lines = []
        for i, article in enumerate(news, 1):
            headline = article.get("headline", "").strip()
            source = article.get("source", "")
            lines.append(f"{i}. [{source}] {headline}")
        news_block = "\n".join(lines)
    else:
        news_block = "(수집된 뉴스 없음)"

    return (
        "## 오늘의 시장 숫자 데이터 (JSON)\n"
        f"{numbers}\n\n"
        "## 오늘의 시장 뉴스 헤드라인\n"
        f"{news_block}\n\n"
        "## 관심 종목별 뉴스 헤드라인\n"
        f"{_format_ticker_news(stock_news)}\n\n"
        "## 시장 무버 종목별 뉴스 헤드라인\n"
        f"{_format_ticker_news(mover_news)}\n\n"
        "위 숫자와 뉴스만 근거로, 지정된 JSON 형식의 해설을 작성하세요. "
        "stock_comments 는 위 stocks 데이터, mover_comments 는 위 movers 데이터에 있는 "
        "종목만 대상으로 하세요."
    )


def _parse_json(text: str) -> dict:
    """Claude 응답에서 JSON을 안전하게 파싱한다. ```json 펜스가 있으면 제거."""
    cleaned = text.strip()
    # 코드펜스 제거
    if cleaned.startswith("```"):
        # ```json ... ``` 또는 ``` ... ``` 형태
        cleaned = cleaned.split("```", 2)[1] if cleaned.count("```") >= 2 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip("`").strip()

    return json.loads(cleaned)


def _shape_stock_comments(value: object) -> list[dict]:
    """stock_comments 응답을 검증해 정규화한다. (형식이 어긋난 항목은 버림)"""
    if not isinstance(value, list):
        return []
    shaped: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        ticker = item.get("ticker")
        comment = item.get("comment")
        if not (isinstance(ticker, str) and isinstance(comment, str) and comment.strip()):
            continue
        name = item.get("name")
        shaped.append({
            "ticker": ticker,
            "name": name if isinstance(name, str) else ticker,
            "comment": comment.strip(),
        })
    return shaped


def _shape_mover_comments(value: object) -> list[dict]:
    """mover_comments 응답을 검증해 정규화한다. direction 은 up/down 만 허용."""
    shaped: list[dict] = []
    for item in _shape_stock_comments(value):  # ticker/name/comment 검증은 동일
        direction = None
        if isinstance(value, list):
            # _shape_stock_comments 가 버린 항목이 있을 수 있어 티커로 원본을 찾는다
            for raw in value:
                if isinstance(raw, dict) and raw.get("ticker") == item["ticker"]:
                    direction = raw.get("direction")
                    break
        item["direction"] = direction if direction in ("up", "down") else "flat"
        shaped.append(item)
    return shaped


def generate_commentary(
    market: dict,
    crypto: list[dict],
    news: list[dict],
    stocks: list[dict] | None = None,
    stock_news: dict[str, list[str]] | None = None,
    movers: dict[str, list[dict]] | None = None,
    mover_news: dict[str, list[str]] | None = None,
) -> dict | None:
    """시장 숫자 + 뉴스(+ 관심 종목·시장 무버와 각 종목 뉴스)로 해설을 생성한다.

    성공 시 해설 dict, 실패 시 None (파이프라인이 죽지 않도록 fallback).
    """
    if not GEMINI_API_KEY:
        print("[경고] GEMINI_API_KEY 가 없어 해설 생성을 건너뜁니다. (.env 참고)")
        return None

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as exc:
        print(f"[경고] Gemini 클라이언트 초기화 실패: {exc}")
        return None

    contents = _build_user_message(market, crypto, news, stocks, stock_news,
                                   movers, mover_news)
    gen_config = types.GenerateContentConfig(
        # 시스템 프롬프트는 Gemini에선 system_instruction 으로 전달
        system_instruction=SYSTEM_PROMPT,
        # 순수 JSON 강제 (Gemini 옵션)
        response_mime_type="application/json",
        max_output_tokens=GEMINI_MAX_TOKENS,
        # thinking 비활성화: 정해진 JSON 출력엔 불필요하고, 켜두면 thinking이
        # 출력 토큰 예산을 소진해 JSON이 잘린다 (2.5-flash는 thinking 모델).
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    # 일시적 503/429 등은 지수 백오프로 재시도. 그 외 오류는 즉시 포기(None 폴백).
    response = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=gen_config,
            )
            break
        except Exception as exc:
            if _is_retryable(exc) and attempt < _MAX_ATTEMPTS:
                wait = _BACKOFF_BASE ** attempt
                print(f"[경고] Gemini 해설 API 일시 실패({attempt}/{_MAX_ATTEMPTS - 1}), "
                      f"{wait:.0f}초 후 재시도: {exc}")
                time.sleep(wait)
                continue
            print(f"[경고] Gemini 해설 API 호출 실패: {exc}")
            return None

    # 응답 텍스트 추출
    text = response.text or ""

    try:
        # response_mime_type 로 이미 순수 JSON이지만, 펜스 제거는 안전장치로 유지
        parsed = _parse_json(text)
    except Exception as exc:
        print(f"[경고] Gemini 응답 JSON 파싱 실패: {exc}")
        return None

    # 기대 키만 추려서 반환 (key_topics·stock_comments·mover_comments 는 리스트로 정규화)
    result: dict = {}
    for key in _KEYS:
        value = parsed.get(key)
        if key == "key_topics":
            result[key] = value if isinstance(value, list) else []
        elif key == "stock_comments":
            result[key] = _shape_stock_comments(value)
        elif key == "mover_comments":
            result[key] = _shape_mover_comments(value)
        else:
            result[key] = value if isinstance(value, str) else ""
    return result
