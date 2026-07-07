"""Gemini API로 시장 해설 생성. (숫자·뉴스 근거만 사용, 억지 해석·투자추천 금지)"""

from __future__ import annotations

import json

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MAX_TOKENS, GEMINI_MODEL

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

출력 JSON 형식:
{
  "market_summary": "3~4문장. 오늘 장 전체 분위기 요약 (지수 흐름 + 가장 큰 테마 1~2개)",
  "index_comment": "1~2문장. 지수가 이렇게 움직인 배경 (뉴스 근거)",
  "macro_comment": "1~2문장. 금리·유가·달러·VIX 중 의미있는 움직임 해석. 특히 금리/VIX 하락이 시장에 갖는 의미를 자연스럽게 설명",
  "crypto_comment": "1문장. 암호화폐 흐름",
  "key_topics": ["오늘 시장을 움직인 핵심 이슈 3~5개, 각 한 줄"]
}"""

# 파싱 실패·API 실패 시 반환할 키 구조 (템플릿이 참조하는 키)
_KEYS = ["market_summary", "index_comment", "macro_comment", "crypto_comment", "key_topics"]


def _build_user_message(market: dict, crypto: list[dict], news: list[dict]) -> str:
    """숫자 데이터와 뉴스 헤드라인을 정리해 유저 메시지로 만든다."""
    # 숫자 데이터는 JSON 그대로 전달 (Claude가 값을 지어내지 않도록 근거 고정)
    numbers = json.dumps(
        {"market": market, "crypto": crypto},
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
        "위 숫자와 뉴스만 근거로, 지정된 JSON 형식의 해설을 작성하세요."
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


def generate_commentary(market: dict, crypto: list[dict], news: list[dict]) -> dict | None:
    """시장 숫자 + 뉴스로 해설을 생성한다.

    성공 시 해설 dict, 실패 시 None (파이프라인이 죽지 않도록 fallback).
    """
    if not GEMINI_API_KEY:
        print("[경고] GEMINI_API_KEY 가 없어 해설 생성을 건너뜁니다. (.env 참고)")
        return None

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=_build_user_message(market, crypto, news),
            config=types.GenerateContentConfig(
                # 시스템 프롬프트는 Gemini에선 system_instruction 으로 전달
                system_instruction=SYSTEM_PROMPT,
                # 순수 JSON 강제 (Gemini 옵션)
                response_mime_type="application/json",
                max_output_tokens=GEMINI_MAX_TOKENS,
                # thinking 비활성화: 정해진 JSON 출력엔 불필요하고, 켜두면 thinking이
                # 출력 토큰 예산을 소진해 JSON이 잘린다 (2.5-flash는 thinking 모델).
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
    except Exception as exc:
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

    # 기대 키만 추려서 반환 (key_topics 는 리스트로 정규화)
    result: dict = {}
    for key in _KEYS:
        value = parsed.get(key)
        if key == "key_topics":
            result[key] = value if isinstance(value, list) else []
        else:
            result[key] = value if isinstance(value, str) else ""
    return result
