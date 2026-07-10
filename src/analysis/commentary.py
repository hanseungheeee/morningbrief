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
차분하지만 판단이 담긴 해설체로 씁니다. 과장하거나 낙관/비관으로 치우치지 않고,
사실 위에서 담담하게 맥락을 짚습니다.

## 서사 원칙 (market_summary 작성법)
market_summary 는 "A 올랐다, B 내렸다" 식 병렬 나열이 아니라, 오늘 시장을 관통하는
하나의 흐름으로 쓴다. 제공된 뉴스에서 가장 큰 동인(driver) 1~2개를 찾아 중심에 놓고,
지수·매크로·종목의 움직임이 그 동인과 어떻게 연결되는지 흐름 있게 서술한다.

단, 인과 연결에는 철칙이 있다:
- "A 때문에 B"라고 쓰려면 그 인과가 제공된 뉴스에서 확인되어야 한다. 뉴스가 두 사실을
  함께 언급하거나 원인으로 지목할 때만 연결한다.
- 인과 사슬 금지: 뉴스에 각각 존재하는 사실들을 임의로 이어 "A → B → C" 식 사슬을
  만들지 않는다 (예: "유가 상승이 인플레이션 우려를 키워 기술주에 부담"처럼 그럴듯한
  경제 논리로 잇는 것). 사슬의 연결고리 하나하나가 뉴스에서 직접 확인될 때만 잇는다.
- 뉴스가 통념과 반대로 말하면 뉴스를 따른다. 일반적인 경제 상식으로 뉴스에 없는
  연결을 보충하지 않는다.
- 근거가 없으면 두 사실을 병렬로 두거나 "직접적 연관은 확인되지 않는다"고 명시한다.
- [방향 일치 예외] 개별 종목의 촉매가 뉴스에 없을 때, 그 종목의 업종(일반 상식으로 분류
  가능)이나 관련 원자재가 '제공된 섹터·매크로 데이터'에서 같은 방향으로 뚜렷이 움직였다면,
  그 사실을 맥락으로 덧붙일 수 있다. 단 인과("~때문에")가 아니라 방향 일치("~와 같은 흐름/방향
  속에")로만 쓰고, 개별 촉매는 확인되지 않았음을 함께 밝힌다. 이는 '제공된 숫자'에 근거한
  관찰이지, 뉴스에 없는 인과 사슬을 지어내는 것이 아니다. 섹터·원자재도 같은 방향이 아니면
  이 예외를 쓰지 않는다.
- ★ 억지 인과는 틀린 정보다. 정직한 병렬이 그럴듯한 거짓 서사보다 낫다. ★

## 반드시 지킬 원칙
1. 제공된 숫자 데이터와 뉴스 헤드라인에 있는 정보만 사용한다. 숫자를 새로 지어내거나
   추측하지 않는다. 제공되지 않은 수치를 문장에 넣지 않는다.
2. 어떤 움직임의 근거가 뉴스에서 확인되지 않으면 "관련 뉴스에서 확인되지 않음"이라고
   명시하고, 억지 해석이나 그럴듯한 소설을 만들지 않는다.
3. 특정 종목의 매수/매도 추천을 절대 하지 않는다. 사실과 맥락만 전달한다.
4. 반드시 아래 형식의 순수 JSON만 출력한다. 마크다운 코드펜스나 설명 문장을 덧붙이지 않는다.
5. 종목 코멘트는 뉴스 근거가 있거나 등락이 큰 종목 위주로만 작성한다. 움직임이 미미하고
   관련 뉴스도 없는 종목은 생략해도 된다. 전 종목을 억지로 다 쓰지 않는다.
6. 무버(movers)는 그날 크게 움직인 종목이므로 "왜 움직였나"의 뉴스 근거가 특히 중요하다.
   다음 순서로 처리한다: (1) 해당 종목 뉴스(헤드라인·요약)에서 개별 촉매가 확인되면 그것을
   연결한다. (2) 개별 촉매가 없더라도, 위 '방향 일치 예외'에 따라 그 종목의 업종이나 관련
   원자재가 제공된 섹터·매크로 데이터에서 같은 방향으로 뚜렷이 움직였다면 그 맥락을 덧붙인다
   (예: "유가·에너지 섹터 약세와 같은 흐름 속에 하락, 개별 촉매는 뉴스에서 확인되지 않음").
   (3) 개별 촉매도 없고 섹터·원자재 동조도 없을 때만 "급등/급락 원인은 관련 뉴스에서 확인되지
   않음"이라고 쓴다. 인과 단정과 억지 해석은 어느 경우에도 금지.
7. policy_comment 는 "연준·정책 뉴스" 섹션에 기사가 있을 때만 작성한다. 연준 발언·금리·
   재정·관세·경제지표·지정학이 오늘 시장에 준 영향을 2~3문장으로 짚되, 시장 영향과의
   연결 역시 위 인과 철칙을 따른다. 정책 뉴스가 없으면 빈 문자열("")로 둔다.
8. calendar_comment 는 "오늘 발표된 경제 지표" 섹션에 지표가 있을 때만 작성한다. 오늘 나온
   지표가 예상 대비 어땠고(상회/하회/부합) 시장에 어떤 의미인지 1~2문장으로 짚는다.
   ★ 예상치·실제치·이전치 수치는 반드시 제공된 데이터의 값만 쓴다. 수치를 새로 지어내거나
   반올림·변형하지 않는다. ★ 상회가 곧 호재라는 식의 단정은 피하고(예: 높은 물가 지표는
   상회가 악재일 수 있다), 지표 성격에 맞게 담담히 해석한다. 발표된 지표가 없으면 null.
9. sector_comment 는 제공된 "섹터 등락"(11개 섹터 ETF) 데이터를 근거로, 오늘 강했던 섹터와
   약했던 섹터를 짚어 "돈이 어디로 움직였나"(섹터 로테이션)를 1~2문장으로 서술한다. 어느 섹터가
   왜 움직였는지는 위 인과 철칙을 따라 뉴스 근거가 있을 때만 연결한다. 섹터 데이터가 없으면 null.
10. watch_points 는 "앞으로"를 보는 항목이다. 제공된 "예정 일정"(다가오는 경제 지표)과 정책
    뉴스를 근거로, 오늘·이번 주 시장이 주목할 이벤트·지표와 그 관전 포인트를 2~4개, 각 한 줄로
    쓴다. ★ 예정 일정에 없는 이벤트를 지어내지 않는다. ★ 과거 해석이 아니라 "무엇을 지켜볼지"에
    초점을 둔다(예: "15일 CPI — 예상 상회 시 금리 인하 기대 후퇴 여부"). 근거가 없으면 빈 배열.

출력 JSON 형식:
{
  "market_summary": "4~6문장. 오늘 시장을 관통하는 서사 — 핵심 동인 1~2개를 중심에 놓고 지수·매크로·종목을 흐름으로 연결 (위 서사 원칙 준수)",
  "index_comment": "1~2문장. 지수가 이렇게 움직인 배경 (뉴스 근거)",
  "macro_comment": "1~2문장. 금리·유가·달러·VIX 중 의미있는 움직임 해석. 특히 금리/VIX 하락이 시장에 갖는 의미를 자연스럽게 설명",
  "policy_comment": "2~3문장. 연준·정책 뉴스가 시장에 준 영향 (정책 뉴스 있을 때만, 없으면 빈 문자열)",
  "calendar_comment": "1~2문장. 오늘 발표된 경제 지표가 예상 대비 어땠고 시장에 갖는 의미 (제공된 수치만 사용, 지표 없으면 null)",
  "sector_comment": "1~2문장. 오늘 강/약했던 섹터로 본 자금 흐름(섹터 로테이션). 섹터 데이터 없으면 null",
  "crypto_comment": "1문장. 암호화폐 흐름",
  "key_topics": ["오늘 서사의 핵심 축 3~5개, 각 한 줄. 단순 헤드라인 나열이 아니라 시장을 움직인 축으로"],
  "watch_points": ["오늘·이번 주 지켜볼 관전 포인트 2~4개, 각 한 줄 (예정 지표·정책 이벤트 근거, forward-looking)"],
  "stock_comments": [
    {"ticker": "NVDA", "name": "엔비디아", "comment": "1~2문장. 이 종목이 왜 이렇게 움직였나. 해당 종목 뉴스에 근거가 있으면 연결하고, 없으면 등락 사실만 담담히 서술"}
  ],
  "mover_comments": [
    {"ticker": "...", "name": "...", "direction": "up 또는 down", "comment": "1~2문장. 왜 이렇게 크게 움직였나. 뉴스 근거 필수, 근거 없으면 '급등/급락 원인은 관련 뉴스에서 확인되지 않음'"}
  ]
}
movers 데이터가 비어 있으면 mover_comments 는 빈 배열로 둔다."""

# 파싱 실패·API 실패 시 반환할 키 구조 (템플릿이 참조하는 키)
_KEYS = ["market_summary", "index_comment", "macro_comment", "policy_comment", "calendar_comment",
         "sector_comment", "crypto_comment", "key_topics", "watch_points",
         "stock_comments", "mover_comments"]


def _format_ticker_news(ticker_news: dict[str, list[dict]] | None) -> str:
    """{티커: [{headline, summary}]} 을 티커 단위 목록 텍스트로 만든다. (근거를 종목별로 고정)

    헤드라인 아래에 요약을 들여써 붙여, 헤드라인만으로 안 드러나는 등락 원인을 준다.
    """
    lines: list[str] = []
    for ticker, items in (ticker_news or {}).items():
        if not items:
            lines.append(f"- {ticker}: (뉴스 없음)")
            continue
        lines.append(f"- {ticker}:")
        for it in items:
            # 하위호환: 혹시 문자열이 오면 헤드라인으로 취급
            if isinstance(it, str):
                lines.append(f"  - {it}")
                continue
            headline = (it.get("headline") or "").strip()
            summary = (it.get("summary") or "").strip()
            lines.append(f"  - {headline}")
            if summary:
                lines.append(f"    ({summary})")
    return "\n".join(lines) if lines else "(수집된 종목 뉴스 없음)"


def _format_calendar_today(events: list[dict] | None) -> str:
    """오늘 발표된 지표 목록을 '지표명: 실제/예상/이전 (상회|하회)' 줄로 만든다.

    Gemini 가 calendar_comment 에서 지어낸 수치를 못 쓰도록 근거를 명시적으로 고정한다.
    """
    if not events:
        return "(오늘 발표된 주요 경제 지표 없음 → calendar_comment 는 null)"
    label = {"above": "예상 상회", "below": "예상 하회", "inline": "예상 부합"}
    lines = []
    for e in events:
        actual = e.get("actual") or "-"
        consensus = e.get("consensus") or "-"
        previous = e.get("previous") or "-"
        tag = label.get(e.get("surprise") or "", "")
        suffix = f" ({tag})" if tag else ""
        lines.append(
            f"- {e.get('name', '')}: 실제 {actual} / 예상 {consensus} / 이전 {previous}{suffix}"
        )
    return "\n".join(lines)


def _format_calendar_upcoming(events: list[dict] | None) -> str:
    """예정 일정(다가오는 지표) 목록을 watch_points 근거로 쓸 텍스트로 만든다."""
    if not events:
        return "(예정된 주요 지표 없음 → watch_points 는 빈 배열)"
    lines = []
    for e in events:
        cons = e.get("consensus")
        cons = f" (예상 {cons})" if cons else ""
        wd = e.get("weekday", "")
        wd = f"({wd})" if wd else ""
        lines.append(f"- {e.get('date', '')}{wd} {e.get('name', '')}{cons}")
    return "\n".join(lines)


def _format_headlines(articles: list[dict] | None, empty_text: str) -> str:
    """뉴스 기사 목록을 '[출처] 헤드라인' 줄 목록으로 만든다."""
    if not articles:
        return empty_text
    lines = []
    for i, article in enumerate(articles, 1):
        headline = article.get("headline", "").strip()
        source = article.get("source", "")
        lines.append(f"{i}. [{source}] {headline}")
    return "\n".join(lines)


def _build_user_message(
    market: dict,
    crypto: list[dict],
    news: list[dict],
    stocks: list[dict] | None = None,
    stock_news: dict[str, list[str]] | None = None,
    movers: dict[str, list[dict]] | None = None,
    mover_news: dict[str, list[str]] | None = None,
    policy_news: list[dict] | None = None,
    calendar_today: list[dict] | None = None,
    sectors: list[dict] | None = None,
    calendar_upcoming: list[dict] | None = None,
) -> str:
    """숫자 데이터와 뉴스 헤드라인을 정리해 유저 메시지로 만든다."""
    # 숫자 데이터는 JSON 그대로 전달 (Claude가 값을 지어내지 않도록 근거 고정)
    numbers = json.dumps(
        {
            "market": market,
            "sectors": sectors or [],
            "crypto": crypto,
            "stocks": stocks or [],
            "movers": movers or {"gainers": [], "losers": []},
        },
        ensure_ascii=False,
        indent=2,
    )

    return (
        "## 오늘의 시장 숫자 데이터 (JSON — sectors 는 sector_comment 의 근거)\n"
        f"{numbers}\n\n"
        "## 오늘의 시장 뉴스 헤드라인\n"
        f"{_format_headlines(news, '(수집된 뉴스 없음)')}\n\n"
        "## 연준·정책 뉴스 (시장 뉴스에서 정책 키워드로 선별, policy_comment 의 근거)\n"
        f"{_format_headlines(policy_news, '(오늘 정책 관련 뉴스 없음 → policy_comment 는 빈 문자열)')}\n\n"
        "## 오늘 발표된 경제 지표 (calendar_comment 의 근거 — 이 수치만 사용, 지어내지 말 것)\n"
        f"{_format_calendar_today(calendar_today)}\n\n"
        "## 예정 일정 (watch_points 의 근거 — 다가오는 지표/이벤트, 없는 항목 지어내지 말 것)\n"
        f"{_format_calendar_upcoming(calendar_upcoming)}\n\n"
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
    policy_news: list[dict] | None = None,
    calendar_today: list[dict] | None = None,
    sectors: list[dict] | None = None,
    calendar_upcoming: list[dict] | None = None,
) -> dict | None:
    """시장 숫자 + 뉴스(+ 관심 종목·시장 무버·정책 뉴스·경제 지표·섹터·예정 일정)로
    서사형 해설을 생성한다.

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
                                   movers, mover_news, policy_news, calendar_today,
                                   sectors, calendar_upcoming)
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
        if key in ("key_topics", "watch_points"):
            # 문자열 리스트로 정규화 (비문자열·빈 항목 제거)
            result[key] = [s.strip() for s in value if isinstance(s, str) and s.strip()] \
                if isinstance(value, list) else []
        elif key == "stock_comments":
            result[key] = _shape_stock_comments(value)
        elif key == "mover_comments":
            result[key] = _shape_mover_comments(value)
        elif key in ("calendar_comment", "sector_comment"):
            # 근거 없으면 null (템플릿이 섹션 해설을 숨김)
            result[key] = value.strip() if isinstance(value, str) and value.strip() else None
        else:
            result[key] = value if isinstance(value, str) else ""
    return result
