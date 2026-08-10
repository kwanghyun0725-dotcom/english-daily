"""표현 데이터 로드 · 오늘 올릴 항목 선택 · 캡션 생성."""
import html
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "expressions.json"
STATE = ROOT / "data" / "state.json"

# GitHub Actions 는 값이 없으면 빈 문자열을 넣어주므로 `or` 로 받아야 한다.
HANDLE = os.environ.get("IG_HANDLE") or "@your_account"

BASE_TAGS = [
    "영어공부", "영어표현", "생활영어", "영어회화", "하루한문장",
    "영어독학", "직장인영어", "영어스터디", "영어초보", "미드영어",
    "englishtips", "learnenglish", "dailyenglish", "englishidioms", "englishphrases",
]


def load():
    with open(DATA, encoding="utf-8") as f:
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


def pick(items, state):
    """아직 안 올린 것 중 다음 순번. 한 바퀴 다 돌면 처음으로 돌아감."""
    idx = state.get("next_index", 0) % len(items)
    return idx, items[idx]


def _bold_html(text):
    """**...** -> <b>...</b> (HTML 이스케이프 후)"""
    esc = html.escape(text, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)


def _plain(text):
    return text.replace("**", "")


def render_rows(item):
    parts = []
    for ex in item["examples"]:
        parts.append(
            '<div class="row">'
            f'<div class="en">{_bold_html(ex["en"])}</div>'
            f'<div class="ko">{html.escape(ex["ko"], quote=False)}</div>'
            "</div>"
        )
    return "\n  ".join(parts)


def build_html(item, number):
    tpl = (ROOT / "templates" / "card.html").read_text(encoding="utf-8")
    phrase = html.escape(item["phrase"], quote=False)
    out = (
        tpl.replace("{{NO}}", f"{number:03d}")
        .replace("{{PHRASE}}", phrase)
        .replace("{{IPA}}", html.escape(item.get("ipa", ""), quote=False))
        .replace("{{KO}}", html.escape(item["ko"], quote=False))
        .replace("{{NOTE}}", html.escape(item["note"], quote=False))
        .replace("{{ROWS}}", render_rows(item))
        .replace("{{HANDLE}}", html.escape(HANDLE, quote=False))
    )
    return out


def build_caption(item, number):
    lines = []
    lines.append(f"📌 {item['phrase']} — {item['ko']}")
    lines.append("")
    lines.append(item["note"])
    lines.append("")
    lines.append("✍️ 이렇게 써요")
    for ex in item["examples"]:
        lines.append(f"· {_plain(ex['en'])}")
        lines.append(f"  → {ex['ko']}")
    lines.append("")
    lines.append("💬 이 표현으로 문장 하나 만들어서 댓글에 남겨보세요!")
    lines.append("")
    lines.append("매일 아침 7시, 영어 표현 한 개씩 올려요.")
    lines.append(f"저장해두고 꺼내 보세요 🔖  {HANDLE}")
    lines.append("")
    tags = list(dict.fromkeys(item.get("tags", []) + BASE_TAGS))
    lines.append(" ".join("#" + t.replace(" ", "") for t in tags))
    return "\n".join(lines)
