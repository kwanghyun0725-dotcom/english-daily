"""매일 게시 파이프라인.

사용법:
  python -m src.main build     # 표현 선택 -> 카드 JPEG + 캡션 생성 (.build/)
  python -m src.main publish   # 인스타그램에 게시 -> state.json 갱신
  python -m src.main preview N # N번째 표현 미리보기 (게시 안 함)
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import content
from src.render import render

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
POSTS = ROOT / "posts"
KST = timezone(timedelta(hours=9))


def today_kst():
    return datetime.now(KST).strftime("%Y-%m-%d")


def cmd_build():
    items = content.load()
    state = content.read_state()
    idx, item = content.pick(items, state)
    number = len(state.get("posted", [])) + 1

    date = today_kst()
    # 같은 날 두 번 돌아도 이전 이미지를 덮어쓰지 않도록 순번을 파일명에 넣는다.
    img_name = f"{date}-{idx:03d}.jpg"
    img_path = POSTS / img_name

    render(content.build_html(item, number), img_path)
    caption = content.build_caption(item, number)

    BUILD.mkdir(exist_ok=True)
    meta = {
        "date": date,
        "index": idx,
        "number": number,
        "phrase": item["phrase"],
        "image": f"posts/{img_name}",
        "caption": caption,
    }
    (BUILD / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[build] {date} · No.{number:03d} · {item['phrase']}")
    print(f"[build] 이미지: {img_path}")
    return meta


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

    items = content.load()
    state = content.read_state()

    # 같은 날 이미 올렸으면 중복 게시하지 않는다.
    # (상태 저장 단계가 실패해 재실행되는 경우를 막아준다.)
    already = [p for p in state.get("posted", []) if p.get("date") == meta["date"]]
    if already and os.environ.get("FORCE_POST") != "1":
        print(f"[publish] {meta['date']} 에 이미 게시했습니다 ({already[-1]['phrase']}). 건너뜁니다.")
        print("[publish] 그래도 올리려면 FORCE_POST=1 로 실행하세요.")
        return

    from src.post import post_image

    ig_user_id = os.environ["IG_USER_ID"]
    token = os.environ["IG_ACCESS_TOKEN"]
    media_id = post_image(ig_user_id, token, url, meta["caption"])

    state.setdefault("posted", []).append(
        {
            "date": meta["date"],
            "index": meta["index"],
            "phrase": meta["phrase"],
            "media_id": media_id,
        }
    )
    state["next_index"] = (meta["index"] + 1) % len(items)
    content.write_state(state)
    print(f"[publish] state 갱신 완료 (다음 순번: {state['next_index']})")


def cmd_preview(n):
    items = content.load()
    idx = int(n) % len(items)
    item = items[idx]
    out = BUILD / f"preview-{idx:03d}.jpg"
    render(content.build_html(item, idx + 1), out)
    print(f"[preview] {out}")
    print("-" * 50)
    print(content.build_caption(item, idx + 1))


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
