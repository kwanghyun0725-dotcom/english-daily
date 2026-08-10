"""매일 영어 표현 인스타 자동 게시 — 전체 로직 한 파일.

사용법:
  python daily_post.py build      # 표현 선택 -> 카드 JPEG + 캡션 생성
  python daily_post.py publish    # 인스타그램에 게시 -> state.json 갱신
  python daily_post.py preview 0  # 0번 표현 미리보기 (게시 안 함)
"""
import asyncio
import html as html_mod
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPRESSIONS = ROOT / "expressions.json"
STATE = ROOT / "state.json"
TEMPLATE = ROOT / "card.html"
POSTS = ROOT / "posts"
BUILD = ROOT / "build"

KST = timezone(timedelta(hours=9))
WIDTH, HEIGHT = 1080, 1350

# GitHub Actions 는 값이 없으면 빈 문자열을 넣어주므로 `or` 로 받아야 한다.
HANDLE = os.environ.get("IG_HANDLE") or "@your_account"

BASE_TAGS = [
    "영어공부", "영어표현", "생활영어", "영어회화", "하루한문장",
    "영어독학", "직장인영어", "영어스터디", "영어초보", "미드영어",
    "englishtips", "learnenglish", "dailyenglish", "englishidioms", "englishphrases",
]


# ── 데이터 ────────────────────────────────────────────────────────────
def load_items():
    with open(EXPRESSIONS, encoding="utf-8") as f:
        return json.load(f)


def read_state():
    if STATE.exists():
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"next_index": 0, "posted": []}


def write_state(state):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ── 카드 HTML ─────────────────────────────────────────────────────────
def _bold_html(text):
    esc = html_mod.escape(text, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)


def _plain(text):
    return text.replace("**", "")


def build_html(item, number):
    rows = "\n  ".join(
        '<div class="row">'
        f'<div class="en">{_bold_html(ex["en"])}</div>'
        f'<div class="ko">{html_mod.escape(ex["ko"], quote=False)}</div>'
        "</div>"
        for ex in item["examples"]
    )
    tpl = TEMPLATE.read_text(encoding="utf-8")
    return (
        tpl.replace("{{NO}}", f"{number:03d}")
        .replace("{{PHRASE}}", html_mod.escape(item["phrase"], quote=False))
        .replace("{{IPA}}", html_mod.escape(item.get("ipa", ""), quote=False))
        .replace("{{KO}}", html_mod.escape(item["ko"], quote=False))
        .replace("{{NOTE}}", html_mod.escape(item["note"], quote=False))
        .replace("{{ROWS}}", rows)
        .replace("{{HANDLE}}", html_mod.escape(HANDLE, quote=False))
    )


def build_caption(item, number):
    lines = [f"📌 {item['phrase']} — {item['ko']}", "", item["note"], "", "✍️ 이렇게 써요"]
    for ex in item["examples"]:
        lines.append(f"· {_plain(ex['en'])}")
        lines.append(f"  → {ex['ko']}")
    lines += [
        "",
        "💬 이 표현으로 문장 하나 만들어서 댓글에 남겨보세요!",
        "",
        "매일 아침 7시, 영어 표현 한 개씩 올려요.",
        f"저장해두고 꺼내 보세요 🔖  {HANDLE}",
        "",
    ]
    tags = list(dict.fromkeys(item.get("tags", []) + BASE_TAGS))
    lines.append(" ".join("#" + t.replace(" ", "") for t in tags))
    return "\n".join(lines)


# ── 렌더링 ────────────────────────────────────────────────────────────
async def _shot(html_text, out_path):
    from playwright.async_api import async_playwright

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html_text)
        tmp = f.name
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(args=["--no-sandbox", "--force-color-profile=srgb"])
            page = await browser.new_page(
                viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1
            )
            await page.goto("file://" + tmp)
            await page.wait_for_selector("html[data-fitted]", timeout=15000)
            if await page.get_attribute("html", "data-fitted") != "1":
                print("  [주의] 글자를 최소까지 줄여도 내용이 넘칩니다. 설명이나 예문을 줄여주세요.")
            await page.wait_for_timeout(400)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(out_path), type="jpeg", quality=92)
            await browser.close()
    finally:
        Path(tmp).unlink(missing_ok=True)


def render(html_text, out_path):
    asyncio.run(_shot(html_text, Path(out_path)))
    return Path(out_path)


# ── 인스타그램 API ────────────────────────────────────────────────────
API_VERSION = os.environ.get("IG_API_VERSION", "v26.0")
API_BASE = os.environ.get("IG_API_BASE") or "https://graph.instagram.com"


def _api(path):
    return f"{API_BASE}/{API_VERSION}/{path}"


def _check(r, what):
    if not r.ok:
        raise RuntimeError(f"{what} 실패 [{r.status_code}]: {r.text}")
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"{what} 실패: {data['error']}")
    return data


def post_image(ig_user_id, token, image_url, caption):
    import requests

    r = requests.post(
        _api(f"{ig_user_id}/media"),
        data={"image_url": image_url, "caption": caption, "access_token": token},
        timeout=60,
    )
    cid = _check(r, "컨테이너 생성")["id"]
    print(f"  컨테이너 생성됨: {cid}")

    deadline = time.time() + 180
    last = None
    while time.time() < deadline:
        s = requests.get(
            _api(cid), params={"fields": "status_code,status", "access_token": token}, timeout=30
        )
        data = _check(s, "컨테이너 상태 확인")
        last = data.get("status_code")
        if last == "FINISHED":
            break
        if last == "ERROR":
            raise RuntimeError(f"이미지 처리 실패: {data.get('status')}")
        time.sleep(5)
    else:
        raise RuntimeError(f"컨테이너 처리 시간 초과 (마지막 상태: {last})")

    p = requests.post(
        _api(f"{ig_user_id}/media_publish"),
        data={"creation_id": cid, "access_token": token},
        timeout=60,
    )
    media_id = _check(p, "게시")["id"]
    print(f"  게시 완료: {media_id}")
    return media_id


# ── 명령 ──────────────────────────────────────────────────────────────
def today_kst():
    return datetime.now(KST).strftime("%Y-%m-%d")


def cmd_build():
    items = load_items()
    state = read_state()
    idx = state.get("next_index", 0) % len(items)
    item = items[idx]
    number = len(state.get("posted", [])) + 1

    date = today_kst()
    img_name = f"{date}-{idx:03d}.jpg"
    render(build_html(item, number), POSTS / img_name)

    BUILD.mkdir(exist_ok=True)
    meta = {
        "date": date,
        "index": idx,
        "number": number,
        "phrase": item["phrase"],
        "image": f"posts/{img_name}",
        "caption": build_caption(item, number),
    }
    (BUILD / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[build] {date} · No.{number:03d} · {item['phrase']}")
    print(f"[build] 이미지: {POSTS / img_name}")


def raw_url(rel_path):
    override = os.environ.get("IMAGE_BASE_URL")
    if override:
        return override.rstrip("/") + "/" + rel_path
    repo = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ.get("IMAGE_COMMIT_SHA") or os.environ.get("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{sha}/{rel_path}"


def cmd_publish():
    meta = json.loads((BUILD / "meta.json").read_text(encoding="utf-8"))
    url = raw_url(meta["image"])
    print(f"[publish] 이미지 URL: {url}")

    if os.environ.get("DRY_RUN") == "1":
        print("[publish] DRY_RUN — 실제 게시는 건너뜁니다.")
        print("-" * 50)
        print(meta["caption"])
        print("-" * 50)
        return

    items = load_items()
    state = read_state()
    already = [p for p in state.get("posted", []) if p.get("date") == meta["date"]]
    if already and os.environ.get("FORCE_POST") != "1":
        print(f"[publish] {meta['date']} 에 이미 게시했습니다 ({already[-1]['phrase']}). 건너뜁니다.")
        return

    media_id = post_image(
        os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"], url, meta["caption"]
    )
    state.setdefault("posted", []).append(
        {
            "date": meta["date"],
            "index": meta["index"],
            "phrase": meta["phrase"],
            "media_id": media_id,
        }
    )
    state["next_index"] = (meta["index"] + 1) % len(items)
    write_state(state)
    print(f"[publish] state 갱신 완료 (다음 순번: {state['next_index']})")


def cmd_preview(n):
    items = load_items()
    idx = int(n) % len(items)
    item = items[idx]
    out = BUILD / f"preview-{idx:03d}.jpg"
    render(build_html(item, idx + 1), out)
    print(f"[preview] {out}")
    print("-" * 50)
    print(build_caption(item, idx + 1))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        cmd_build()
    elif cmd == "publish":
        cmd_publish()
    elif cmd == "preview":
        cmd_preview(sys.argv[2] if len(sys.argv) > 2 else 0)
    else:
        print(__doc__)
        sys.exit(1)
