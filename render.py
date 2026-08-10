"""HTML 카드를 인스타그램 규격 JPEG(1080x1350)로 렌더링."""
import asyncio
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

WIDTH, HEIGHT = 1080, 1350


async def _shot(html_text: str, out_path: Path):
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
            state = await page.get_attribute("html", "data-fitted")
            if state != "1":
                print("  [주의] 글자 크기를 최소까지 줄여도 내용이 넘칩니다. "
                      "설명(note)이나 예문을 조금 줄여주세요.")
            await page.wait_for_timeout(400)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(out_path), type="jpeg", quality=92)
            await browser.close()
    finally:
        Path(tmp).unlink(missing_ok=True)


def render(html_text: str, out_path: Path):
    asyncio.run(_shot(html_text, Path(out_path)))
    return Path(out_path)
