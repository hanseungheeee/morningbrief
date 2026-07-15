"""Gemini TTS 로 해설 산문을 블록별 오디오(WAV)로 합성한다.

- 커멘터리와 같은 GEMINI_API_KEY 를 재사용한다. (Cloud Text-to-Speech 는 API 키를
  받지 않아 서비스계정이 필요하므로, 이미 키가 통하는 Gemini TTS 를 쓴다.)
- google-genai SDK 사용. 반환 오디오는 24kHz·16bit·mono PCM → WAV 헤더를 씌워 저장.
- 키가 없거나 합성이 실패하면 조용히 None/부분 결과를 반환한다.
  (파이프라인은 죽지 않고, 페이지는 브라우저 Web Speech 로 폴백한다.)
- 낭독 대상 블록·접두어·게이트 조건은 templates/brief.html.j2 의 data-tts 블록과 1:1로 맞춘다.
"""

from __future__ import annotations

import io
import re
import time
import wave
from pathlib import Path

from google import genai
from google.genai import types

from config import (
    GEMINI_API_KEY,
    GEMINI_TTS_MODEL,
    GEMINI_TTS_SAMPLE_RATE,
    GEMINI_TTS_VOICE,
)

_MAX_ATTEMPTS = 4          # 최초 1회 + 재시도 3회
_BACKOFF_BASE = 2          # 2, 4, 8초


# ---------------------------------------------------------------------------
# 텍스트 정규화 (브라우저 JS normalize() 와 동일 규칙)
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    t = re.sub(r"\s+", " ", str(text)).strip()
    t = t.replace("%", " 퍼센트")
    t = t.replace("$", " 달러")
    t = re.sub(r"[▲▼]", "", t)                 # 상승/하락 삼각형 제거
    t = re.sub(r"\+(?=\s*\d)", " 플러스 ", t)     # 숫자 앞 +
    t = re.sub(r"-(?=\s*\d)", " 마이너스 ", t)     # 숫자 앞 -
    t = re.sub(r"\s+", " ", t).strip()
    return t


# ---------------------------------------------------------------------------
# 낭독 블록 구성 (data-tts 블록과 순서·게이트를 일치시킨다)
#   각 항목: (key, prefix, body)  — key 는 템플릿 data-tts-key 와 매칭용
# ---------------------------------------------------------------------------
def _build_blocks(payload: dict) -> list[tuple[str, str, str]]:
    c = payload.get("commentary") or {}
    movers = payload.get("movers") or {}
    blocks: list[tuple[str, str, str]] = []

    ms = c.get("market_summary")
    kt = c.get("key_topics") or []
    if ms or kt:
        parts = ([ms] if ms else []) + list(kt)
        blocks.append(("summary", "", " ".join(parts)))

    wp = c.get("watch_points") or []
    if wp:
        blocks.append(("watch", "", " ".join(wp)))

    if c.get("index_comment"):
        blocks.append(("index", "주요 지수.", c["index_comment"]))
    if c.get("macro_comment"):
        blocks.append(("macro", "매크로 지표.", c["macro_comment"]))
    if payload.get("sectors") and c.get("sector_comment"):
        blocks.append(("sector", "섹터 흐름.", c["sector_comment"]))
    if c.get("policy_comment"):
        blocks.append(("policy", "연준 및 정책.", c["policy_comment"]))
    if payload.get("calendar_today") and c.get("calendar_comment"):
        blocks.append(("calendar", "오늘의 경제 지표.", c["calendar_comment"]))
    if c.get("crypto_comment"):
        blocks.append(("crypto", "암호화폐.", c["crypto_comment"]))

    scs = c.get("stock_comments") or []
    if payload.get("stocks") and scs:
        body = " ".join(f"{s.get('name', '')} — {s.get('comment', '')}" for s in scs)
        blocks.append(("stock", "주요 종목.", body))

    mcs = c.get("mover_comments") or []
    if (movers.get("gainers") or movers.get("losers")) and mcs:
        body = " ".join(f"{m.get('name', '')} — {m.get('comment', '')}" for m in mcs)
        blocks.append(("mover", "오늘의 무버.", body))

    return blocks


# ---------------------------------------------------------------------------
# PCM → WAV
# ---------------------------------------------------------------------------
def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Gemini 가 준 raw PCM(16bit·mono)을 WAV 파일 바이트로 감싼다."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)          # 16-bit
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _rate_from_mime(mime: str | None, default: int) -> int:
    """inline_data mime(예: 'audio/L16;codec=pcm;rate=24000')에서 샘플레이트 추출."""
    if not mime:
        return default
    m = re.search(r"rate=(\d+)", mime)
    return int(m.group(1)) if m else default


def _is_retryable(exc: Exception) -> bool:
    s = str(exc).lower()
    return any(k in s for k in ("429", "503", "500", "resource_exhausted", "unavailable", "deadline"))


# ---------------------------------------------------------------------------
# Gemini TTS 합성
# ---------------------------------------------------------------------------
def _synthesize(client: "genai.Client", text: str) -> bytes | None:
    """텍스트 한 덩어리를 WAV 바이트로 합성한다. 실패 시 예외."""
    cfg = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=GEMINI_TTS_VOICE)
            )
        ),
    )
    resp = client.models.generate_content(
        model=GEMINI_TTS_MODEL,
        contents=text,
        config=cfg,
    )
    part = resp.candidates[0].content.parts[0]
    inline = getattr(part, "inline_data", None)
    if not inline or not inline.data:
        return None
    rate = _rate_from_mime(getattr(inline, "mime_type", None), GEMINI_TTS_SAMPLE_RATE)
    return _pcm_to_wav(inline.data, rate)


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------
def generate_tts(payload: dict, output_dir: Path) -> dict | None:
    """해설 블록을 오디오로 합성해 output/tts/{date}/ 에 저장한다.

    반환: {key: 상대경로} 매니페스트 (예: {"summary": "tts/2026-07-15/summary.wav"}).
          키가 없거나 아무것도 못 만들면 None.
    """
    if not GEMINI_API_KEY:
        print("[TTS] GEMINI_API_KEY 없음 → 오디오 생성 건너뜀 (브라우저 Web Speech 폴백).")
        return None

    blocks = _build_blocks(payload)
    if not blocks:
        print("[TTS] 낭독할 해설 블록이 없어 오디오 생성을 건너뜁니다.")
        return None

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as exc:  # noqa: BLE001
        print(f"[TTS] Gemini 클라이언트 초기화 실패 → Web Speech 폴백: {exc}")
        return None

    date = payload.get("date") or ""
    tts_dir = Path(output_dir) / "tts" / date
    tts_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, str] = {}
    for key, prefix, raw in blocks:
        text = _normalize(f"{prefix} {raw}" if prefix else raw)
        if not text:
            continue

        audio = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                audio = _synthesize(client, text)
                break
            except Exception as exc:  # noqa: BLE001 — 한 블록 실패가 전체를 막지 않게
                if _is_retryable(exc) and attempt < _MAX_ATTEMPTS:
                    wait = _BACKOFF_BASE ** attempt
                    print(f"[TTS] '{key}' 일시 실패({attempt}), {wait:.0f}초 후 재시도")
                    time.sleep(wait)
                    continue
                print(f"[TTS] '{key}' 합성 실패 (이 블록은 Web Speech 폴백): {type(exc).__name__}")
                break

        if not audio:
            continue
        (tts_dir / f"{key}.wav").write_bytes(audio)
        manifest[key] = f"tts/{date}/{key}.wav"

    if not manifest:
        print("[TTS] 생성된 오디오가 없습니다 (전체 Web Speech 폴백).")
        return None

    print(f"[TTS] {len(manifest)}개 블록 오디오 생성 → {tts_dir}  "
          f"(모델: {GEMINI_TTS_MODEL}, 음성: {GEMINI_TTS_VOICE})")
    return manifest
