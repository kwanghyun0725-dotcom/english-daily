# 매일 영어 표현 인스타 자동 게시

매일 아침 7시(한국시간)에 "오늘의 영어 표현" 카드를 만들어 인스타그램에 자동으로 올립니다.
GitHub Actions에서 돌아가므로 컴퓨터를 켜둘 필요가 없고, 비용도 들지 않습니다.

## 어떻게 동작하나요

1. `data/expressions.json`에서 아직 안 올린 표현을 순서대로 하나 꺼냅니다.
2. `templates/card.html`을 채워 1080×1350 JPEG 카드를 만듭니다 (`posts/YYYY-MM-DD.jpg`).
3. 그 이미지를 저장소에 커밋합니다 → `raw.githubusercontent.com` 공개 URL이 생깁니다.
   (인스타 API는 "공개된 URL의 이미지"만 받기 때문에 이 단계가 필요합니다.)
4. 인스타그램 Graph API로 컨테이너를 만들고 발행합니다.
5. `data/state.json`에 기록해 다음 날 같은 표현이 또 나오지 않게 합니다.

## 폴더 구조

```
data/expressions.json   표현 30개 (여기만 고치면 콘텐츠가 바뀝니다)
data/state.json         어디까지 올렸는지 기록 — 직접 건드릴 필요 없음
templates/card.html     카드 디자인. 색·폰트·문구는 여기서 수정
src/content.py          표현 선택 + 캡션/해시태그 생성
src/render.py           HTML → JPEG 렌더링 (Playwright)
src/post.py             인스타그램 API 호출
src/main.py             build / publish / preview 명령
.github/workflows/daily-post.yml   매일 게시 + 주간 토큰 갱신 (하나로 통합)
posts/                  생성된 카드 이미지가 쌓이는 곳
```

## 필요한 설정값

GitHub 저장소 → Settings → Secrets and variables → Actions

**Secrets** (암호화됨, 공개 저장소여도 안전)

| 이름 | 설명 |
| --- | --- |
| `IG_USER_ID` | 인스타그램 프로 계정의 숫자 ID |
| `IG_ACCESS_TOKEN` | 장기(long-lived) 액세스 토큰 |
| `GH_PAT` | (선택) 토큰 자동 갱신용. `secrets: write` 권한 |

**Variables**

| 이름 | 값 |
| --- | --- |
| `IG_HANDLE` | 카드 하단에 찍힐 계정명. 예: `@my_english` |
| `IG_API_BASE` | (선택) 페이스북 로그인 방식이면 `https://graph.facebook.com` |

발급 절차는 `설정 가이드` 문서를 참고하세요.

## 직접 실행해보기

```bash
pip install -r requirements.txt
python -m playwright install chromium
sudo apt-get install -y fonts-noto-cjk fonts-crosextra-caladea   # 한글/세리프 폰트

python -m src.main preview 0        # 0번 표현 카드 미리보기 (build/ 에 생성)
python -m src.main build            # 오늘 카드 + 캡션 생성
DRY_RUN=1 GITHUB_REPOSITORY=owner/repo python -m src.main publish   # 게시 없이 확인
```

GitHub에서는 Actions 탭 → "매일 영어 표현 게시" → **Run workflow**로 수동 실행할 수 있고,
`dry_run`을 체크하면 실제 게시 없이 결과물만 아티팩트로 받아볼 수 있습니다.

## 표현 추가하기

`data/expressions.json` 배열 끝에 같은 형식으로 붙이면 됩니다.
예문의 `**...**` 부분이 카드에서 갈색 굵은 글씨로 강조됩니다.

```json
{
  "phrase": "call it a day",
  "ipa": "/kɔːl ɪt ə deɪ/",
  "ko": "오늘은 여기까지 하자",
  "note": "한두 문장 설명",
  "examples": [
    { "en": "Let's **call it a day**.", "ko": "오늘은 여기까지 하죠." }
  ],
  "tags": ["직장"]
}
```

30개를 다 돌면 자동으로 처음으로 돌아갑니다.

## 알아둘 점

- 인스타 API는 계정당 24시간에 100건까지 게시할 수 있습니다. 하루 1건이라 여유롭습니다.
- 이미지는 JPEG만 지원하고, 가로세로 비율은 4:5 ~ 1.91:1 사이여야 합니다. (이 카드는 4:5)
- 장기 토큰은 60일마다 만료되므로, 워크플로 마지막 단계가 매주 월요일에 갱신합니다.
- GitHub Actions의 예약 실행은 서버가 붐비면 몇십 분 늦어질 수 있습니다.
