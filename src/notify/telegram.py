"""Telegram Bot API로 브리핑 알림 전송. (별도 SDK 없이 requests 사용)"""

from __future__ import annotations

import requests

from config import (
    GITHUB_PAGES_URL,
    TELEGRAM_API_URL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)


def _build_message(payload: dict) -> str:
    """알림 메시지 본문을 만든다. (날짜 + 제목 + 핵심 요약 + 링크)"""
    date = payload.get("date", "")
    lines = [f"📈 미국 증시 아침 브리핑 — {date}", ""]

    # 요약: commentary.market_summary 가 있으면 짧게, 없으면 지수 등락만
    commentary = payload.get("commentary") or {}
    summary = commentary.get("market_summary")
    if summary:
        # 너무 길면 잘라서 (텔레그램 가독성)
        lines.append(summary[:300])
    else:
        indices = payload.get("market", {}).get("indices", [])
        for row in indices:
            pct = row.get("change_pct")
            if pct is None:
                continue
            arrow = "▲" if pct >= 0 else "▼"
            sign = "+" if pct >= 0 else ""
            lines.append(f"{row['name']}  {arrow} {sign}{pct:.2f}%")

    # GitHub Pages 링크
    if GITHUB_PAGES_URL:
        lines.append("")
        lines.append(f"전체 브리핑 → {GITHUB_PAGES_URL}")

    return "\n".join(lines)


def send_notification(payload: dict) -> bool:
    """수집·해설 결과를 텔레그램으로 전송한다.

    성공 시 True, 실패/건너뜀 시 False (파이프라인은 죽지 않음).
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[경고] TELEGRAM_BOT_TOKEN/CHAT_ID 가 없어 알림을 건너뜁니다. (.env 참고)")
        return False

    url = f"{TELEGRAM_API_URL}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": _build_message(payload),
                "disable_web_page_preview": False,  # Pages 링크 미리보기 표시
            },
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        print(f"[경고] 텔레그램 알림 전송 실패: {exc}")
        return False

    print("텔레그램 알림 전송 완료")
    return True
