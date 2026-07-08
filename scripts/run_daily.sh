#!/bin/bash
# 매일 아침 브리핑 파이프라인 실행 + GitHub 배포
# launchd(비대화형 셸)에서도 안전하게 돌도록 절대경로·venv 파이썬 직접 사용.

set -o pipefail

# --- 경로 설정 (프로젝트 위치가 바뀌면 여기만 수정) ---
PROJECT_DIR="/Users/han/projects/morning-brief"
VENV_PY="$PROJECT_DIR/venv/bin/python"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/run_daily.log"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR" || { echo "프로젝트 폴더 없음: $PROJECT_DIR"; exit 1; }

echo "===== $(date '+%Y-%m-%d %H:%M:%S') 실행 시작 =====" >> "$LOG_FILE"

# 1) 파이프라인 실행 (수집 → 뉴스 → 해설 → JSON → HTML → 텔레그램 알림)
"$VENV_PY" run.py >> "$LOG_FILE" 2>&1
if [ $? -ne 0 ]; then
  echo "[$(date '+%H:%M:%S')] run.py 실패 (로그 확인)" >> "$LOG_FILE"
fi

# 2) output/ 변경사항만 커밋·푸시 → GitHub Actions 가 Pages 로 배포
TODAY=$(date '+%Y-%m-%d')
git add output/
if git diff --cached --quiet; then
  echo "[$(date '+%H:%M:%S')] output 변경 없음, 커밋 생략" >> "$LOG_FILE"
else
  git commit -m "brief: $TODAY" >> "$LOG_FILE" 2>&1
  if git push origin main >> "$LOG_FILE" 2>&1; then
    echo "[$(date '+%H:%M:%S')] 푸시 완료" >> "$LOG_FILE"
  else
    echo "[$(date '+%H:%M:%S')] 푸시 실패 (인증/네트워크 확인)" >> "$LOG_FILE"
  fi
fi

echo "===== $(date '+%H:%M:%S') 실행 종료 =====" >> "$LOG_FILE"
