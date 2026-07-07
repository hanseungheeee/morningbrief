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
python run.py                  # 수집 → 뉴스 → Gemini 해설 → JSON 저장 → HTML → 텔레그램 알림
python run.py --no-commentary  # Gemini 호출 없이 숫자·뉴스만
python run.py --no-notify       # 텔레그램 알림 없이 실행 (테스트용)
python run.py --render-only     # 저장된 JSON(해설 포함)으로 HTML만 재생성
```

## CP4: 자동화 + 배포

매일 아침 자동으로 브리핑을 생성해 GitHub Pages에 배포하고 텔레그램으로 알린다.

### 전체 자동 실행 흐름

```
launchd (매일 07:00 KST)
  └─ scripts/run_daily.sh
       ├─ venv 파이썬으로 run.py 실행
       │    └─ 수집 → 뉴스 → 해설 → JSON 저장 → HTML 렌더 → 텔레그램 알림
       └─ output/ 변경분 git commit ("brief: YYYY-MM-DD") → push
              └─ GitHub Actions 가 output/ 을 GitHub Pages 로 배포
```

### 추가 환경 변수 (`.env`)

```
TELEGRAM_BOT_TOKEN=<@BotFather 토큰>
TELEGRAM_CHAT_ID=<본인 chat id>
GITHUB_PAGES_URL=https://<아이디>.github.io/<저장소>/
```

### GitHub Pages 설정 (최초 1회, 웹에서)

`output/` 을 Pages 소스로 쓰기 위해 GitHub Actions 방식을 사용한다
(`.github/workflows/deploy-pages.yml` 포함됨).

1. GitHub 저장소 → **Settings** → **Pages**
2. **Build and deployment → Source** 를 **GitHub Actions** 로 선택
3. main 에 push 될 때마다 워크플로가 `output/` 을 자동 배포
4. 배포 후 `https://<아이디>.github.io/<저장소>/` 에서 확인

### 스케줄러 설치 (launchd)

```bash
# 1) 스크립트 실행 권한 (한 번만)
chmod +x scripts/run_daily.sh

# 2) plist 를 LaunchAgents 로 복사
cp scripts/com.morningbrief.plist ~/Library/LaunchAgents/

# 3) 로드 (등록)
launchctl load ~/Library/LaunchAgents/com.morningbrief.plist

# 즉시 한 번 테스트 실행
launchctl start com.morningbrief

# 해제(제거)하려면
launchctl unload ~/Library/LaunchAgents/com.morningbrief.plist
```

매일 오전 **7시(맥 로컬 시간=KST)** 에 실행된다. 미국장 마감(KST 새벽 5~6시, 서머타임에 따라)
이후라 마감 데이터가 들어온다. 실행 로그는 `logs/` 에 쌓인다.

> ⚠️ **맥이 절전(sleep) 상태면 launchd 작업이 실행되지 않는다.** 뚜껑을 닫아두거나
> 잠자기면 그 시각 브리핑을 건너뛴다. 필요하면 아래처럼 매일 06:55에 자동 기상하도록 설정할 수 있다(선택):
>
> ```bash
> sudo pmset repeat wake MTWRFSU 06:55:00
> ```
>
> (해제: `sudo pmset repeat cancel`)

### 수동 실행

```bash
source venv/bin/activate
python run.py            # 전체 파이프라인 (알림 포함)
# 또는 스크립트 통째로 (커밋·푸시까지)
./scripts/run_daily.sh
```
