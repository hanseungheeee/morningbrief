"""JSON → HTML 렌더링. 포맷팅·색상 판단은 여기서 처리하고 템플릿엔 값만 넘긴다."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import DATA_DIR

# 경로 상수
BASE_DIR: Path = Path(__file__).resolve().parents[2]
OUTPUT_DIR: Path = BASE_DIR / "output"
ARCHIVE_DIR: Path = OUTPUT_DIR / "archive"
TEMPLATE_DIR: Path = Path(__file__).resolve().parent / "templates"


# ---------------------------------------------------------------------------
# JSON 로드
# ---------------------------------------------------------------------------
def load_json(date: str | None = None) -> dict:
    """특정 날짜 또는 가장 최근 JSON을 로드한다.

    date=None 이면 data/ 안의 가장 최근 YYYY-MM-DD.json 을 고른다.
    """
    if date:
        path = DATA_DIR / f"{date}.json"
    else:
        files = sorted(DATA_DIR.glob("*.json"))
        if not files:
            raise FileNotFoundError(f"{DATA_DIR} 안에 JSON 파일이 없습니다.")
        path = files[-1]

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 포맷팅 / 색상 판단
# ---------------------------------------------------------------------------
def _direction(change_pct: float | None) -> str:
    """상승/하락/보합 플래그. 등락률 기준."""
    if change_pct is None:
        return "flat"
    change_pct = change_pct + 0.0  # 음의 0 정규화
    if change_pct > 0:
        return "up"
    if change_pct < 0:
        return "down"
    return "flat"


def _fmt_price(price: float | None) -> str:
    """천단위 콤마, 소수점 2자리."""
    if price is None:
        return "-"
    return f"{price:,.2f}"


def _fmt_signed(value: float | None, suffix: str = "") -> str:
    """부호 포함 소수점 2자리. (음의 0 정규화)"""
    if value is None:
        return "-"
    value = value + 0.0
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}{suffix}"


def _shape_market_row(row: dict, *, with_points: bool) -> dict:
    """지수·매크로 한 행을 템플릿용 뷰모델로 변환한다."""
    change_pct = row.get("change_pct")
    view = {
        "name": row["name"],
        "price": _fmt_price(row.get("price")),
        "change_pct": _fmt_signed(change_pct, "%"),
        "direction": _direction(change_pct),
    }
    if with_points:
        view["change"] = _fmt_signed(row.get("change"))
    return view


def _shape_crypto_row(row: dict) -> dict:
    """암호화폐 한 행을 템플릿용 뷰모델로 변환한다."""
    change_pct = row.get("change_pct")
    return {
        "name": row["name"],
        "price": _fmt_price(row.get("price")),
        "change_pct": _fmt_signed(change_pct, "%"),
        "direction": _direction(change_pct),
    }


def build_context(payload: dict) -> dict:
    """수집 JSON을 템플릿 렌더링 컨텍스트로 가공한다."""
    market = payload.get("market", {})
    movers = payload.get("movers") or {}
    # 해설은 있으면 그대로, 없으면(None) 빈 dict → 템플릿이 블록을 숨김
    commentary = payload.get("commentary") or {}
    return {
        "date": payload.get("date", ""),
        "collected_at": payload.get("collected_at", ""),
        "indices": [_shape_market_row(r, with_points=True) for r in market.get("indices", [])],
        "macros": [_shape_market_row(r, with_points=True) for r in market.get("macros", [])],
        "crypto": [_shape_crypto_row(r) for r in payload.get("crypto", [])],
        # 관심 종목: 표시 항목이 암호화폐와 같아(이름·현재가·등락률) 같은 뷰모델을 쓴다
        "stocks": [_shape_crypto_row(r) for r in payload.get("stocks", [])],
        # 시장 무버: 상승/하락 리스트를 각각 같은 뷰모델로
        "mover_gainers": [_shape_crypto_row(r) for r in movers.get("gainers", [])],
        "mover_losers": [_shape_crypto_row(r) for r in movers.get("losers", [])],
        "commentary": commentary,
    }


# ---------------------------------------------------------------------------
# 렌더 / 저장
# ---------------------------------------------------------------------------
def render_html(payload: dict) -> str:
    """Jinja2 템플릿으로 HTML 문자열을 만든다."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("brief.html.j2")
    return template.render(**build_context(payload))


def save_html(html: str, date: str) -> tuple[str, str]:
    """output/index.html(최신)과 output/archive/{date}.html(복사본)에 저장한다."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)

    index_path = OUTPUT_DIR / "index.html"
    archive_path = ARCHIVE_DIR / f"{date}.html"
    for path in (index_path, archive_path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
    return str(index_path), str(archive_path)


def render(date: str | None = None) -> tuple[str, str]:
    """JSON 로드 → HTML 렌더 → 저장까지 한 번에. 저장 경로 두 개를 반환한다."""
    payload = load_json(date)
    html = render_html(payload)
    return save_html(html, payload.get("date") or datetime.now().strftime("%Y-%m-%d"))
