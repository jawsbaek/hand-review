"""TUI 화면을 SVG로 캡처해 captures/에 저장. `uv run capture.py`로 실행.

렌더링 서버 없이도 리뷰 가능하도록, 캡처한 SVG에서 셀 텍스트를 좌표순으로
추출해 터미널 화면을 그대로 재구성한 .txt도 같이 남긴다(svg_to_text).
"""

import asyncio
import html
import re
import sys
from pathlib import Path

from analyze import compute_hand_rows, icm
from poker_tui import PokerApp

OUT = Path(__file__).parent / "captures"


def svg_to_text(svg: str) -> str:
    """Textual export_screenshot()의 <text x= y=>glyph</text> 셀들을 줄 단위로 복원."""
    cells = [
        (float(y), float(x), html.unescape(text))
        for x, y, text in re.findall(r'<text[^>]*x="([\d.]+)"[^>]*y="([\d.]+)"[^>]*>([^<]*)</text>', svg)
    ]
    lines = {}
    for y, x, text in cells:
        lines.setdefault(round(y, 1), []).append((x, text))
    out = []
    for y in sorted(lines):
        row = sorted(lines[y])
        out.append("".join(t for _, t in row).rstrip())
    return "\n".join(out)


async def capture(name: str, app: PokerApp, tab_id: str | None = None):
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        if tab_id:
            app.query_one("TabbedContent").active = tab_id
            await pilot.pause()
        svg = app.export_screenshot(simplify=True)
        OUT.mkdir(exist_ok=True)
        (OUT / f"{name}.svg").write_text(svg)
        (OUT / f"{name}.txt").write_text(svg_to_text(svg))
        print(f"captured {name}")


async def main():
    hand_rows, _, _ = compute_hand_rows(Path(__file__).parent / "samples" / "cash", None, 500)
    icm_result = ([5000, 3000, 2000], [50, 30, 20], icm([5000, 3000, 2000], [50, 30, 20]))
    mtt_summary = (3, 100.0, 150.0, 2)

    await capture("hands", PokerApp(hand_rows, mtt_summary, icm_result), "hands")
    await capture("mtt", PokerApp(hand_rows, mtt_summary, icm_result), "mtt")
    await capture("icm", PokerApp(hand_rows, mtt_summary, icm_result), "icm")
    await capture("empty_hands", PokerApp([], None, None), "hands")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
