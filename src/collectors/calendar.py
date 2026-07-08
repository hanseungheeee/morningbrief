"""경제 캘린더 수집 - Nasdaq 무료 경제 이벤트 API. (출력·저장은 하지 않음)

무키로 실제(actual)/예상(consensus)/이전(previous)을 모두 주는 유일한 무료 소스라
Nasdaq 내부 API 를 쓴다(2026-07 실측 확인). Finnhub·FMP 무료 티어는 캘린더가 유료 전용.
비공식 엔드포인트라 구조 변경·차단 리스크가 있어, 모든 호출을 방어적으로 감싼다.

## 날짜/시간대 기준 (중요 — 함정 방지)
이 브리핑은 매일 07:00 KST(로컬 launchd)에 돈다. 그 시각을 UTC 로 보면 전날 22:00,
US-Eastern(EDT/EST) 으로 보면 전날 18:00 이다. 즉 실행 시점에 미국의 "어제 거래일"은
이미 장이 끝나 지표 결과가 다 나와 있다. 그래서 07:00 KST 시점 기준으로:

- "오늘 발표된 지표" = 방금 지난 미국 거래일 = (KST 오늘 날짜 − 1일).
  그 날이 토/일이면 금요일까지 뒤로 물린다(월요일 아침엔 금요일 발표분이 "오늘").
  ※ 7am KST = 전날 18:00 ET 이므로 "KST 날짜 − 1일"이 곧 미국 기준 어제 거래일이며,
    이 관계는 서머타임(EDT/EST)과 무관하게 성립한다.
- "예정 일정" = 그 기준일의 다음 영업일부터 앞으로 CALENDAR_UPCOMING_BUSINESS_DAYS 영업일.

Nasdaq 의 date 파라미터는 미국(ET) 달력 날짜 기준이라 위에서 구한 날짜를 그대로 넘긴다.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import requests

from config import (
    CALENDAR_COUNTRY,
    CALENDAR_EXCLUDE_KEYWORDS,
    CALENDAR_KEYWORDS,
    CALENDAR_UPCOMING_BUSINESS_DAYS,
    CALENDAR_UPCOMING_MAX,
    NASDAQ_CALENDAR_URL,
    NASDAQ_HEADERS,
)

# 화이트리스트/제외 키워드를 소문자로 미리 준비 (대소문자 무시 부분 일치)
_KEYWORDS_LOWER = [k.lower() for k in CALENDAR_KEYWORDS]
_EXCLUDE_LOWER = [k.lower() for k in CALENDAR_EXCLUDE_KEYWORDS]

# 한글 요일 (월=0 ... 일=6)
_WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]

# 숫자 파싱용: 값에서 부호·소수·K/M/B/T 배수만 뽑는다
_NUM_PATTERN = re.compile(r"^\s*([+-]?\d[\d,]*\.?\d*)\s*([KMBT%]?)", re.IGNORECASE)
_SCALE = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}


# ---------------------------------------------------------------------------
# 날짜 계산
# ---------------------------------------------------------------------------
def _reference_us_date(now: datetime) -> date:
    """실행 시각(KST)으로 '방금 지난 미국 거래일'을 구한다.

    7am KST = 전날 18:00 ET 이므로 KST 날짜에서 하루를 뺀 날이 미국 어제 거래일이다.
    그 날이 주말이면 금요일까지 뒤로 물린다.
    (미국 공휴일은 별도 달력이 없어 보정하지 않는다 — 그 경우 해당일 지표가 비어
     '오늘 발표' 섹션이 그냥 숨겨진다. 없는 데이터를 지어내는 것보다 정직하다.)
    """
    ref = now.date() - timedelta(days=1)
    while ref.weekday() >= 5:  # 5=토, 6=일 → 금요일까지 back
        ref -= timedelta(days=1)
    return ref


def _upcoming_business_days(ref: date, count: int) -> list[date]:
    """기준일 '다음' 영업일부터 앞으로 count 영업일(주말 제외)을 반환한다."""
    days: list[date] = []
    cursor = ref
    while len(days) < count:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:  # 평일만
            days.append(cursor)
    return days


# ---------------------------------------------------------------------------
# 값 정리 / 중요도 필터
# ---------------------------------------------------------------------------
def _clean(value: object) -> str | None:
    """Nasdaq 셀 값을 정리한다. 빈칸·&nbsp; 등은 None."""
    if not isinstance(value, str):
        return None
    text = value.replace("\xa0", " ").replace("&nbsp;", " ").strip()
    return text or None


def _parse_num(text: str | None) -> float | None:
    """'57K', '4.2%', '1,814K', '-77.60B' 같은 값을 float 로 파싱한다. 실패 시 None.

    실제치·예상치 비교(예상 상회/하회 판정)에만 쓴다. 두 값은 같은 단위라 배수만
    일관되게 적용하면 대소 비교가 정확하다.
    """
    if not text:
        return None
    m = _NUM_PATTERN.match(text)
    if not m:
        return None
    num = m.group(1).replace(",", "")
    try:
        value = float(num)
    except ValueError:
        return None
    suffix = m.group(2).lower()
    if suffix in _SCALE:
        value *= _SCALE[suffix]
    return value


def _is_important(name: str) -> bool:
    """이벤트명이 중요 지표 화이트리스트에 걸리고 제외 키워드엔 안 걸리는지."""
    lower = name.lower()
    if any(ex in lower for ex in _EXCLUDE_LOWER):
        return False
    return any(kw in lower for kw in _KEYWORDS_LOWER)


def _surprise(actual: str | None, consensus: str | None) -> str | None:
    """실제치가 예상치 대비 상회/하회/부합인지. 비교 불가면 None.

    'above' = 실제 > 예상, 'below' = 실제 < 예상, 'inline' = 같음.
    ※ 상회가 곧 호재라는 의미는 아니다(예: 높은 CPI). 방향만 표시한다.
    """
    a = _parse_num(actual)
    c = _parse_num(consensus)
    if a is None or c is None:
        return None
    if a > c:
        return "above"
    if a < c:
        return "below"
    return "inline"


# ---------------------------------------------------------------------------
# Nasdaq 호출
# ---------------------------------------------------------------------------
def _fetch_day(day: date) -> list[dict]:
    """특정 날짜의 대상국 경제 이벤트 원본 행을 가져온다. 실패 시 빈 리스트."""
    try:
        resp = requests.get(
            NASDAQ_CALENDAR_URL,
            params={"date": day.isoformat()},
            headers=NASDAQ_HEADERS,
            timeout=12,
        )
        resp.raise_for_status()
        rows = ((resp.json() or {}).get("data") or {}).get("rows") or []
    except Exception as exc:  # 하루 실패해도 전체는 계속
        print(f"[경고] 경제 캘린더({day}) 수집 실패: {exc}")
        return []
    return [r for r in rows if r.get("country") == CALENDAR_COUNTRY]


# ---------------------------------------------------------------------------
# 수집 진입점
# ---------------------------------------------------------------------------
def collect_calendar(now: datetime | None = None) -> dict:
    """오늘 발표된 지표 결과 + 향후 예정 일정을 수집한다.

    반환:
      {
        "today_date": "YYYY-MM-DD",           # '오늘 발표'의 기준 미국 거래일
        "today": [ {name, actual, consensus, previous, surprise}, ... ],
        "upcoming": [ {date, weekday, name, consensus}, ... ],
      }
    now=None 이면 datetime.now()(=KST, 로컬 스케줄러) 사용. 개별 호출 실패는 건너뛰고
    가능한 만큼만 채운다.
    """
    now = now or datetime.now()
    ref = _reference_us_date(now)
    upcoming_days = _upcoming_business_days(ref, CALENDAR_UPCOMING_BUSINESS_DAYS)

    # 기준일 + 예정 영업일들을 한 번에 병렬 조회 (순차면 6회 × 수초라 아침 실행에 부담).
    # 각 _fetch_day 는 자체 try/except 로 실패해도 빈 리스트를 돌려주므로 안전하다.
    all_days = [ref, *upcoming_days]
    with ThreadPoolExecutor(max_workers=len(all_days)) as pool:
        fetched = dict(zip(all_days, pool.map(_fetch_day, all_days)))

    # 1) 오늘(기준일) 발표된 지표 결과 — actual 이 실제로 있는 중요 지표만
    today: list[dict] = []
    for row in fetched.get(ref, []):
        name = _clean(row.get("eventName"))
        if not name or not _is_important(name):
            continue
        actual = _clean(row.get("actual"))
        if actual is None:  # 결과가 아직 없는 건(연설 등)은 '발표 결과'에서 제외
            continue
        consensus = _clean(row.get("consensus"))
        previous = _clean(row.get("previous"))
        today.append({
            "name": name,
            "actual": actual,
            "consensus": consensus,
            "previous": previous,
            "surprise": _surprise(actual, consensus),
        })

    # 2) 예정 일정 — 다음 영업일들의 중요 지표 (미래라 actual 은 비어 있음)
    # 같은 날 같은 지표명이 여러 행(레벨·전월비 등)으로 오면 예상치 있는 쪽을 남긴다.
    upcoming: list[dict] = []
    seen: dict[tuple[str, str], int] = {}  # (날짜, 지표명) → upcoming 인덱스
    for day in upcoming_days:
        for row in fetched.get(day, []):
            name = _clean(row.get("eventName"))
            if not name or not _is_important(name):
                continue
            consensus = _clean(row.get("consensus"))
            key = (day.isoformat(), name)
            if key in seen:  # 중복: 기존이 예상치 없고 이번에 있으면 교체
                idx = seen[key]
                if upcoming[idx]["consensus"] is None and consensus is not None:
                    upcoming[idx]["consensus"] = consensus
                continue
            seen[key] = len(upcoming)
            upcoming.append({
                "date": day.isoformat(),
                "weekday": _WEEKDAYS_KO[day.weekday()],
                "name": name,
                "consensus": consensus,
            })
    upcoming = upcoming[:CALENDAR_UPCOMING_MAX]

    return {
        "today_date": ref.isoformat(),
        "today": today,
        "upcoming": upcoming,
    }
