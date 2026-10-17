"""Generate a self-contained, offline Pokerist replay report."""

import json
from collections import Counter
from importlib.resources import files
from pathlib import Path

from hand_review.pokerist import load_pokerist, replay_hand
from hand_review.review import review_hand


def build_report(path, ranges=None):
    records, errors, duplicates = load_pokerist(path)
    hands = [review_hand(replay_hand(raw, i), ranges) for i, raw in enumerate(records, 1)]
    grades = Counter(d["review"]["grade"] for h in hands for d in h["decisions"])
    return {
        "version": 1,
        "hands": hands,
        "errors": errors,
        "duplicates": duplicates,
        "grades": dict(grades),
        "ranges": {"oop": ranges[0], "ip": ranges[1]} if ranges else None,
    }


def write_report(path, output, ranges=None):
    path, output = Path(path), Path(output)
    if output.resolve() == path.resolve() or output.suffix.lower() != ".html":
        raise ValueError("출력은 입력과 다른 .html 파일이어야 합니다.")
    report = build_report(path, ranges)
    if not report["hands"]:
        details = "; ".join(report["errors"][:3]) or "pokerist-hand JSONL 파일이 없습니다."
        raise ValueError(f"재생 가능한 핸드 없음: {details}")
    # Escape '<' even in JSON script data: malicious nicknames must not close
    # the data element. The UI renders all untrusted strings with textContent.
    data = json.dumps(report, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c")
    template = files("hand_review").joinpath("replay.html").read_text(encoding="utf-8")
    html = template.replace("__HAND_REVIEW_DATA__", data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return report
