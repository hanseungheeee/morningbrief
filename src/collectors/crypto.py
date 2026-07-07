"""암호화폐 시세를 CoinGecko 무료 API로 수집한다. (출력·저장은 하지 않음)"""

from __future__ import annotations

import requests

from config import COINGECKO_URL, COINGECKO_VS_CURRENCY, CRYPTO_COINS


def collect_crypto() -> list[dict]:
    """CoinGecko /simple/price 로 현재가(USD)와 24시간 등락률을 수집한다."""
    params = {
        "ids": ",".join(CRYPTO_COINS.keys()),
        "vs_currencies": COINGECKO_VS_CURRENCY,
        "include_24hr_change": "true",
    }

    results: list[dict] = []
    try:
        resp = requests.get(COINGECKO_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"[경고] 암호화폐 수집 실패: {exc}")
        return results

    for coin_id, name in CRYPTO_COINS.items():
        info = data.get(coin_id)
        if not info:
            print(f"[경고] {name}({coin_id}) 응답 누락")
            continue

        price = info.get(COINGECKO_VS_CURRENCY)
        change_pct = info.get(f"{COINGECKO_VS_CURRENCY}_24h_change")
        results.append({
            "id": coin_id,
            "name": name,
            "price": round(float(price), 2) if price is not None else None,
            "change_pct": round(float(change_pct), 2) if change_pct is not None else None,
        })

    return results
