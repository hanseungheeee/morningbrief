"""프로젝트 전역 설정 - 모든 설정은 이 파일 한 곳에서만 관리한다."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# .env 로드 (실제 키는 .env 에, 예시는 .env.example 에)
load_dotenv()

# ---------------------------------------------------------------------------
# 경로 상수
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent
DATA_DIR: Path = BASE_DIR / "data"

# ---------------------------------------------------------------------------
# 지수 티커 (yfinance 심볼 → 한글 표시명)
# ---------------------------------------------------------------------------
INDEX_TICKERS: dict[str, str] = {
    "^GSPC": "S&P 500",
    "^IXIC": "나스닥",
    "^DJI": "다우",
    "^RUT": "러셀 2000",
}

# ---------------------------------------------------------------------------
# 매크로 티커 (yfinance 심볼 → 한글 표시명)
# ---------------------------------------------------------------------------
MACRO_TICKERS: dict[str, str] = {
    "GC=F": "금",
    "CL=F": "WTI 유가",
    "^TNX": "미 10년물 국채금리",
    "DX-Y.NYB": "달러 인덱스",
    "^VIX": "VIX",
}

# ---------------------------------------------------------------------------
# 암호화폐 (CoinGecko id → 한글 표시명)
# ---------------------------------------------------------------------------
CRYPTO_COINS: dict[str, str] = {
    "bitcoin": "비트코인",
    "ethereum": "이더리움",
    "ripple": "리플",
    "solana": "솔라나",
}

# ---------------------------------------------------------------------------
# CoinGecko API
# ---------------------------------------------------------------------------
COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_VS_CURRENCY: str = "usd"

# ---------------------------------------------------------------------------
# API 키 (.env 에서 로드, 없으면 None)
# ---------------------------------------------------------------------------
FINNHUB_API_KEY: str | None = os.getenv("FINNHUB_API_KEY")
GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID: str | None = os.getenv("TELEGRAM_CHAT_ID")

# GitHub Pages 배포 URL (텔레그램 알림 링크에 사용)
GITHUB_PAGES_URL: str | None = os.getenv("GITHUB_PAGES_URL")

# ---------------------------------------------------------------------------
# Finnhub 뉴스
# ---------------------------------------------------------------------------
FINNHUB_NEWS_URL: str = "https://finnhub.io/api/v1/news"
# 수집할 뉴스 카테고리 (general=시장 전반, forex=환/금리, crypto=암호화폐)
NEWS_CATEGORIES: list[str] = ["general", "forex", "crypto"]
NEWS_RECENT_HOURS: int = 24  # 이 시간 이내 기사만 사용
NEWS_MAX_ITEMS: int = 30     # Claude 입력 토큰 절약을 위해 상위 N개만

# ---------------------------------------------------------------------------
# Gemini 해설
# ---------------------------------------------------------------------------
GEMINI_MODEL: str = "gemini-2.5-flash"  # 무료 티어에서 충분히 빠르고 좋음 (2.0-flash는 무료 한도 0)
GEMINI_MAX_TOKENS: int = 2000

# ---------------------------------------------------------------------------
# Telegram 알림
# ---------------------------------------------------------------------------
TELEGRAM_API_URL: str = "https://api.telegram.org"
