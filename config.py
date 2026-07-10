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
# 섹터 로테이션 (SPDR S&P 11개 섹터 ETF 심볼 → 한글 표시명)
# 개별 종목보다 상위 관점에서 "오늘 돈이 어느 섹터로 움직였나"를 보여준다.
# ---------------------------------------------------------------------------
SECTOR_TICKERS: dict[str, str] = {
    "XLK": "기술",
    "XLC": "커뮤니케이션",
    "XLY": "자유소비재",
    "XLF": "금융",
    "XLV": "헬스케어",
    "XLI": "산업재",
    "XLP": "필수소비재",
    "XLE": "에너지",
    "XLB": "소재",
    "XLU": "유틸리티",
    "XLRE": "부동산",
}

# ---------------------------------------------------------------------------
# 관심 종목 (yfinance/Finnhub 심볼 → 한글 표시명)
# ---------------------------------------------------------------------------
WATCH_TICKERS: dict[str, str] = {
    # 빅테크
    "NVDA": "엔비디아",
    "AAPL": "애플",
    "MSFT": "마이크로소프트",
    "GOOGL": "알파벳",
    "AMZN": "아마존",
    "META": "메타",
    "TSLA": "테슬라",
    # 반도체
    "TSM": "TSMC",
    "AVGO": "브로드컴",
    "MU": "마이크론",
}

# ---------------------------------------------------------------------------
# 시장 무버 감시 리스트 (yfinance 심볼 → 한글 표시명)
# Finnhub 무료 티어에 gainers/losers 엔드포인트가 없어, 대형주 감시 리스트를
# yfinance 일괄 조회해 상위/하위를 뽑는다. 관심 종목(WATCH_TICKERS)도 포함하되
# 무버 선정 시 런타임에 제외한다 (CP5 섹션과 중복 방지).
# ---------------------------------------------------------------------------
MOVER_UNIVERSE: dict[str, str] = {
    **WATCH_TICKERS,
    # 금융
    "JPM": "JP모건", "V": "비자", "MA": "마스터카드", "BAC": "뱅크오브아메리카",
    "WFC": "웰스파고", "GS": "골드만삭스", "MS": "모건스탠리", "BLK": "블랙록",
    "SCHW": "찰스슈왑", "C": "씨티그룹", "AXP": "아메리칸익스프레스", "SPGI": "S&P글로벌",
    "PYPL": "페이팔", "COIN": "코인베이스", "HOOD": "로빈후드", "SOFI": "소파이",
    # 헬스케어
    "LLY": "일라이릴리", "UNH": "유나이티드헬스", "JNJ": "존슨앤드존슨", "PFE": "화이자",
    "MRK": "머크", "ABBV": "애브비", "ABT": "애보트", "TMO": "서모피셔",
    "BMY": "브리스톨마이어스", "GILD": "길리어드", "AMGN": "암젠", "REGN": "리제네론",
    "VRTX": "버텍스", "ISRG": "인튜이티브서지컬", "MDT": "메드트로닉",
    # 소비재·유통
    "WMT": "월마트", "PG": "P&G", "KO": "코카콜라", "PEP": "펩시코",
    "COST": "코스트코", "HD": "홈디포", "LOW": "로우스", "TGT": "타깃",
    "NKE": "나이키", "MCD": "맥도날드", "SBUX": "스타벅스", "CMG": "치폴레",
    "DPZ": "도미노피자", "YUM": "얌브랜즈", "TJX": "TJX", "DIS": "디즈니",
    # 소프트웨어·IT서비스
    "ORCL": "오라클", "CRM": "세일즈포스", "ADBE": "어도비", "NFLX": "넷플릭스",
    "INTU": "인튜이트", "NOW": "서비스나우", "IBM": "IBM", "CSCO": "시스코",
    "PLTR": "팔란티어", "SNOW": "스노우플레이크", "CRWD": "크라우드스트라이크",
    "PANW": "팔로알토네트웍스", "FTNT": "포티넷", "ZS": "지스케일러",
    "DDOG": "데이터독", "NET": "클라우드플레어", "SHOP": "쇼피파이",
    # 반도체·하드웨어
    "AMD": "AMD", "INTC": "인텔", "QCOM": "퀄컴", "TXN": "텍사스인스트루먼트",
    "AMAT": "어플라이드머티어리얼즈", "LRCX": "램리서치", "KLAC": "KLA",
    "MRVL": "마벨테크놀로지", "ANET": "아리스타네트웍스", "SNPS": "시놉시스",
    "CDNS": "케이던스", "ARM": "Arm홀딩스",
    # 플랫폼·모빌리티
    "UBER": "우버", "ABNB": "에어비앤비", "DASH": "도어대시", "BKNG": "부킹홀딩스",
    "EXPE": "익스피디아", "RBLX": "로블록스", "MAR": "메리어트", "HLT": "힐튼",
    # 자동차·산업재
    "F": "포드", "GM": "GM", "RIVN": "리비안", "LCID": "루시드",
    "BA": "보잉", "LMT": "록히드마틴", "RTX": "RTX", "NOC": "노스롭그루먼",
    "GD": "제너럴다이내믹스", "DE": "디어", "CAT": "캐터필러", "HON": "허니웰",
    "GE": "GE에어로스페이스", "MMM": "3M", "UPS": "UPS", "FDX": "페덱스",
    "DAL": "델타항공", "UAL": "유나이티드항공", "AAL": "아메리칸항공",
    # 에너지·소재·유틸리티
    "XOM": "엑슨모빌", "CVX": "셰브론", "COP": "코노코필립스", "SLB": "SLB",
    "OXY": "옥시덴털", "FCX": "프리포트맥모란", "NEM": "뉴몬트", "LIN": "린데",
    "NEE": "넥스트에라", "SO": "서던컴퍼니", "DUK": "듀크에너지",
    # 통신
    "T": "AT&T", "VZ": "버라이즌", "TMUS": "T모바일", "CMCSA": "컴캐스트",
}

# 무버 선정 개수 (상승 N + 하락 N)
MOVERS_TOP_N: int = 3

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
# GitHub Actions 는 GITHUB_ 접두 secret/env 를 금지하므로 CI 에선 PAGES_URL 을 쓴다.
# 로컬 .env 는 기존 GITHUB_PAGES_URL 을 그대로 쓰도록 둘 다 허용.
GITHUB_PAGES_URL: str | None = os.getenv("PAGES_URL") or os.getenv("GITHUB_PAGES_URL")

# ---------------------------------------------------------------------------
# Finnhub 뉴스
# ---------------------------------------------------------------------------
FINNHUB_NEWS_URL: str = "https://finnhub.io/api/v1/news"
# 수집할 뉴스 카테고리 (general=시장 전반, forex=환/금리, crypto=암호화폐)
NEWS_CATEGORIES: list[str] = ["general", "forex", "crypto"]
NEWS_RECENT_HOURS: int = 24  # 이 시간 이내 기사만 사용
NEWS_MAX_ITEMS: int = 30     # Claude 입력 토큰 절약을 위해 상위 N개만
NEWS_DISPLAY_MAX: int = 6    # 브리핑 HTML 에 실제로 노출할 헤드라인 개수

# 종목별 뉴스 (Finnhub company-news)
FINNHUB_COMPANY_NEWS_URL: str = "https://finnhub.io/api/v1/company-news"
STOCK_NEWS_DAYS: int = 2          # 최근 N일 기사만 조회
STOCK_NEWS_MAX_PER_TICKER: int = 3  # 종목당 상위 N개 헤드라인 (토큰 절약)

# 연준·정책 뉴스 필터 키워드 (대소문자 무시, 헤드라인·요약에서 부분 일치)
# 수집된 시장 뉴스에서 정책 관련 기사를 따로 골라 해설의 정책 코멘트 근거로 쓴다.
POLICY_KEYWORDS: list[str] = [
    # 연준·통화정책
    "fed", "federal reserve", "powell", "fomc", "rate cut", "rate hike",
    "interest rate", "monetary policy", "quantitative",
    # 재무부·재정정책
    "treasury", "yellen", "bessent", "fiscal", "debt ceiling", "shutdown",
    # 무역·관세
    "tariff", "trade war", "sanction", "export control",
    # 경제지표
    "inflation", "cpi", "pce", "ppi", "jobs report", "nonfarm", "payroll",
    "unemployment", "gdp", "recession",
]

# ---------------------------------------------------------------------------
# 경제 캘린더 (Nasdaq 무료 경제 이벤트 API)
# ---------------------------------------------------------------------------
# Finnhub /calendar/economic 은 유료 전용(2026-07 실측 403), FMP 무료 티어도
# economic calendar 는 유료 전용(402/403)이라, 무키로 실제/예상/이전을 모두 주는
# Nasdaq 내부 API 를 사용한다. 비공식 엔드포인트라 브라우저 User-Agent 헤더가 필요하고,
# 구조 변경·차단 리스크가 있어 수집기에서 모든 호출을 방어적으로 감싼다.
NASDAQ_CALENDAR_URL: str = "https://api.nasdaq.com/api/calendar/economicevents"
NASDAQ_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}
# 조회 대상 국가 (Nasdaq country 필드 값). 미국 지표 위주.
CALENDAR_COUNTRY: str = "United States"
# 예정 일정: 기준일 다음 영업일부터 앞으로 N영업일(주말 제외)
CALENDAR_UPCOMING_BUSINESS_DAYS: int = 5
# 예정 일정 최대 표시 개수 (너무 길어지지 않도록 상한)
CALENDAR_UPCOMING_MAX: int = 15

# 중요도 필터 — Nasdaq 은 중요도 등급을 주지 않으므로 이벤트명 키워드 화이트리스트로
# 시장 영향 큰 지표만 고른다(대소문자 무시 부분 일치). 자잘한 지표(단기채 입찰,
# CFTC 포지션, Redbook 등)는 여기 없으니 자동 제외된다.
CALENDAR_KEYWORDS: list[str] = [
    # 고용
    "Nonfarm Payrolls", "Unemployment Rate", "Average Hourly Earnings",
    "ADP Nonfarm Employment Change", "Initial Jobless Claims",
    "Continuing Jobless Claims", "JOLTS Job Openings", "Challenger Job Cuts",
    # 물가
    "CPI", "PCE", "PPI", "Import Price", "Export Price",
    # 성장·소비·생산
    "GDP", "Retail Sales", "Durable Goods Orders", "Industrial Production",
    "Factory Orders", "Personal Income", "Personal Spending",
    # 심리·PMI
    "ISM Manufacturing PMI", "ISM Non-Manufacturing PMI", "ISM Services PMI",
    "S&P Global Manufacturing PMI", "S&P Global Services PMI",
    "S&P Global Composite PMI", "Michigan Consumer Sentiment",
    "Michigan Inflation Expectations", "CB Consumer Confidence",
    "Chicago PMI", "Philadelphia Fed", "Philly Fed", "Empire State",
    # 주택
    "Building Permits", "Housing Starts", "New Home Sales",
    "Existing Home Sales", "Pending Home Sales",
    # 무역
    "Trade Balance",
    # 연준
    "FOMC", "Fed Interest Rate Decision", "Powell",
]
# 위 키워드에 걸려도 노이즈라 버릴 이벤트명 (부분 일치). 예: GDPNow 는 상시 갱신 나우캐스트라 제외.
CALENDAR_EXCLUDE_KEYWORDS: list[str] = ["GDPNow"]

# ---------------------------------------------------------------------------
# Gemini 해설
# ---------------------------------------------------------------------------
GEMINI_MODEL: str = "gemini-2.5-flash"  # 무료 티어에서 충분히 빠르고 좋음 (2.0-flash는 무료 한도 0)
GEMINI_MAX_TOKENS: int = 2000

# ---------------------------------------------------------------------------
# Telegram 알림
# ---------------------------------------------------------------------------
TELEGRAM_API_URL: str = "https://api.telegram.org"
