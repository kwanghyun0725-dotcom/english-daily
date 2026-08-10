name: 매일 영어 표현 게시

on:
  schedule:
    # 22:00 UTC = 한국시간 다음날 07:00
    - cron: "0 22 * * *"
  workflow_dispatch:
    inputs:
      dry_run:
        description: "실제 게시 없이 이미지/캡션만 생성"
        type: boolean
        default: false

permissions:
  contents: write

concurrency:
  group: daily-post
  cancel-in-progress: false

env:
  TZ: Asia/Seoul

jobs:
  post:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: 한글/세리프 폰트 설치
        run: |
          sudo apt-get update -qq
          sudo apt-get install -y -qq fonts-noto-cjk fonts-crosextra-caladea
          fc-cache -f

      - name: 의존성 설치
        run: |
          pip install -r requirements.txt
          python -m playwright install --with-deps chromium

      - name: 카드 이미지 + 캡션 생성
        env:
          IG_HANDLE: ${{ vars.IG_HANDLE }}
        run: python daily_post.py build

      - name: 이미지 커밋 & 푸시
        id: push_image
        if: ${{ inputs.dry_run != true }}
        run: |
          set -e
          git config user.name  "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add posts/
          git commit -m "chore: 카드 이미지 추가 ($(date +%F))" || echo "변경 없음"
          for i in 1 2 3; do
            git pull --rebase --autostash && git push && break
            echo "푸시 재시도 ${i}/3"; sleep 10
          done
          echo "sha=$(git rev-parse HEAD)" >> "$GITHUB_OUTPUT"

      - name: 인스타그램 게시
        env:
          IG_USER_ID: ${{ secrets.IG_USER_ID }}
          IG_ACCESS_TOKEN: ${{ secrets.IG_ACCESS_TOKEN }}
          IG_API_BASE: ${{ vars.IG_API_BASE || 'https://graph.instagram.com' }}
          IMAGE_COMMIT_SHA: ${{ steps.push_image.outputs.sha }}
          DRY_RUN: ${{ inputs.dry_run && '1' || '0' }}
        run: python daily_post.py publish

      - name: 진행 상태 저장
        if: ${{ inputs.dry_run != true }}
        run: |
          set -e
          git config user.name  "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add state.json
          git commit -m "chore: 게시 상태 갱신 ($(date +%F))" || echo "변경 없음"
          for i in 1 2 3; do
            git pull --rebase --autostash && git push && exit 0
            echo "푸시 재시도 ${i}/3"; sleep 10
          done
          echo "::error::state.json 푸시 실패 — 다음 실행에서 같은 표현이 다시 선택될 수 있습니다."
          exit 1

      - name: 생성물 업로드 (확인용)
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: card-${{ github.run_number }}
          path: |
            posts/
            build/meta.json
          retention-days: 14

      # ── 토큰 갱신 (월요일에만) ───────────────────────────────────
      # 인스타 장기 토큰은 60일 뒤 만료됩니다. 매주 한 번 갱신해두면 만료될 일이 없어요.
      # GH_PAT 시크릿이 있으면 새 토큰을 자동으로 저장하고, 없으면 남은 기간만 알려줍니다.
      - name: 액세스 토큰 갱신
        if: ${{ always() && inputs.dry_run != true }}
        continue-on-error: true
        env:
          IG_ACCESS_TOKEN: ${{ secrets.IG_ACCESS_TOKEN }}
          IG_API_BASE: ${{ vars.IG_API_BASE || 'https://graph.instagram.com' }}
          FB_APP_ID: ${{ secrets.FB_APP_ID }}
          FB_APP_SECRET: ${{ secrets.FB_APP_SECRET }}
          GH_TOKEN: ${{ secrets.GH_PAT }}
          REPO: ${{ github.repository }}
        run: |
          if [ "$(date +%u)" != "1" ]; then
            echo "오늘은 월요일이 아니라 토큰 갱신을 건너뜁니다."
            exit 0
          fi

          if [[ "$IG_API_BASE" == *"graph.facebook.com"* ]]; then
            if [ -z "${FB_APP_ID:-}" ] || [ -z "${FB_APP_SECRET:-}" ]; then
              echo "::warning::페이스북 로그인 방식은 FB_APP_ID / FB_APP_SECRET 이 필요합니다. 건너뜁니다."
              exit 0
            fi
            URL="https://graph.facebook.com/v26.0/oauth/access_token?grant_type=fb_exchange_token&client_id=${FB_APP_ID}&client_secret=${FB_APP_SECRET}&fb_exchange_token=${IG_ACCESS_TOKEN}"
          else
            URL="https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=${IG_ACCESS_TOKEN}"
          fi

          curl -sS "$URL" > /tmp/resp.json
          python3 - <<'PY'
          import json
          d = json.load(open('/tmp/resp.json'))
          if 'access_token' not in d:
              raise SystemExit(f"갱신 실패: {d}")
          print(f"새 토큰 발급 완료 · 남은 유효기간 {round(d.get('expires_in', 0)/86400, 1)}일")
          open('/tmp/new_token', 'w').write(d['access_token'])
          PY

          if [ -n "${GH_TOKEN:-}" ]; then
            gh secret set IG_ACCESS_TOKEN --repo "$REPO" --body "$(cat /tmp/new_token)"
            echo "IG_ACCESS_TOKEN 시크릿을 새 토큰으로 갱신했습니다."
          else
            echo "::warning::GH_PAT 시크릿이 없어 자동 저장은 건너뜁니다. 유효기간만 확인했어요."
          fi
