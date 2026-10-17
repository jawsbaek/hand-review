"""Generate a self-contained, offline Pokerist replay report."""

import json
from collections import Counter
from importlib.resources import files
from pathlib import Path

from hand_review.pokerist import load_pokerist, replay_hand
from hand_review.profiles import Evidence
from hand_review.review import review_hand


def build_report(path, ranges=None, analysis_options=None, cache_dir=None):
    records, errors, duplicates = load_pokerist(path)
    hands = [replay_hand(raw, i) for i, raw in enumerate(records, 1)]
    if analysis_options:
        from hand_review.recommendations import analyze_cached

        evidence = Evidence(hands)
        for h in hands:
            prior = evidence.before(h)
            for d in h["decisions"]:
                context = d["context"]
                overrides = None
                if ranges and context["street"] and context["active"] == 2:
                    oop = context["street"]["oop"]
                    seats = [p["seat"] for p in context["street"].get("players", [])]
                    if oop in seats:
                        overrides = {str(s): ranges[0] if s == oop else ranges[1] for s in seats}
                d["analysis"] = analyze_cached(context, prior, analysis_options, overrides, cache_dir)
    for h in hands:
        review_hand(h, ranges if not analysis_options else None)
    grades = Counter(d["review"]["grade"] for h in hands for d in h["decisions"])
    return {
        "version": 2 if analysis_options else 1,
        "hands": hands,
        "errors": errors,
        "duplicates": duplicates,
        "grades": dict(grades),
        "ranges": {"oop": ranges[0], "ip": ranges[1]} if ranges else None,
        "analysis": {"samples": analysis_options.samples, "solver": analysis_options.solver}
        if analysis_options
        else None,
    }


def render_report(report):
    data = json.dumps(report, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c")
    template = files("hand_review").joinpath("replay.html").read_text(encoding="utf-8")
    if (report.get("analysis") or {}).get("live_token"):
        template = template.replace("connect-src 'none'", "connect-src 'self'")
    return template.replace("__HAND_REVIEW_DATA__", data)


def write_report(path, output, ranges=None, analysis_options=None, cache_dir=None):
    path, output = Path(path), Path(output)
    if output.resolve() == path.resolve() or output.suffix.lower() != ".html":
        raise ValueError("출력은 입력과 다른 .html 파일이어야 합니다.")
    report = build_report(path, ranges, analysis_options, cache_dir)
    if not report["hands"]:
        details = "; ".join(report["errors"][:3]) or "pokerist-hand JSONL 파일이 없습니다."
        raise ValueError(f"재생 가능한 핸드 없음: {details}")
    # Escape '<' even in JSON script data: malicious nicknames must not close
    # the data element. The UI renders all untrusted strings with textContent.
    html = render_report(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return report
