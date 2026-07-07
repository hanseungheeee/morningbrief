# morning-brief

미국 증시 아침 브리핑 자동화 시스템 — 지수·매크로·암호화폐 데이터를 수집해 브리핑을 만든다.

## CP1: 데이터 수집 레이어

지수·매크로·암호화폐의 당일 종가와 등락 데이터를 수집해 `data/YYYY-MM-DD.json`으로 저장하고 콘솔에 출력한다.

### 실행법

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

## CP2: HTML 렌더링

`data/`의 최신 JSON을 읽어 Jinja2 템플릿으로 정적 HTML 브리핑을 생성한다.
`output/index.html`(최신)과 `output/archive/YYYY-MM-DD.html`(복사본)에 저장된다.

```bash
python run.py                # 수집 → JSON 저장 → HTML 생성
python run.py --render-only  # 저장된 최신 JSON으로 HTML만 재생성
```

## CP3: 뉴스 수집 + Gemini 해설

Finnhub로 당일 시장 뉴스를 수집하고, Google Gemini API로 "왜 이렇게 움직였나" 해설을
생성해 JSON과 HTML에 함께 담는다.

### API 키 설정 (필수)

`.env.example`를 참고해 `.env`에 키 두 개를 넣는다 (`.env`는 git에 커밋되지 않음).

- `FINNHUB_API_KEY` — https://finnhub.io 무료 가입 후 발급
- `GEMINI_API_KEY` — https://aistudio.google.com 에서 발급 (무료 티어 제공, 해설 생성용)

키가 없으면 해당 단계는 건너뛰고 숫자·HTML은 정상 생성된다.

```bash
python run.py                  # 수집 → 뉴스 → Gemini 해설 → JSON 저장 → HTML
python run.py --no-commentary  # Gemini 호출 없이 숫자·뉴스만
python run.py --render-only     # 저장된 JSON(해설 포함)으로 HTML만 재생성
```
