import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from hand_review import ev_engine
from hand_review.pokerist import canonical_card, load_pokerist, replay_hand
from hand_review.replay import build_report, write_report
from hand_review.review import made_hand, review_hand, solver_review


def event(name, seat=None, paid=None, stack=None, total=None, stage="Preflop", status="2", **extra):
    attrs = {"STATUS": status, **extra}
    for key, value in (("AMOUNT", paid), ("D_AMOUNT", stack), ("T_S_AMOUNT", total)):
        if value is not None:
            attrs[key] = str(value)
    return {
        "event": name,
        "stage": stage,
        "who": seat,
        "nick": "Hero" if seat == 0 else f"Player{seat}",
        "attrs": attrs,
        # Deliberately emulate the export's unsafe fallback amount.
        "amount": paid if paid is not None else stack,
    }


def synthetic_hand():
    return {
        "_key": "synthetic-only-1",
        "kind": "pokerist-hand",
        "started_ts": 1700000000000,
        "ended_ts": 1700000060000,
        "table_id": "Synthetic demo",
        "net": 12,
        "hero": {"seat": 0, "nick": "Hero", "position": "SB", "cards": ["K♦", "Q♥"]},
        "board": ["A♥", "J/s4", "T/s4", "2♣", "8♦"],
        "pot": 18,
        "positions": {"0": "SB", "1": "BB", "2": "BTN"},
        "integrity": [],
        "showdown": [{"place": 1, "cards": [{"label": "T♥"}, {"label": "T♦"}]}],
        "revealed": [],
        "actions": [
            event("GS_SMALL_BLIND", 0, stack=100, status="1"),
            event("GS_SMALL_BLIND", 0, 1, 99, 1),
            event("GS_BIG_BLIND", 1, 2, 98, 2),
            event("GS_CALL", 2, 2, 98, 2),
            event("GS_CALL", 0, 1, 98, 2),
            event("GS_CHECK", 1, 2, 98, 2),
            event("GS_COLLECT_POT", POT="600", STAKE="999"),
            event("GS_FLOP", stage="Flop"),
            event("GS_CHECK", 0, stack=98, stage="Flop"),
            event("GS_BET", 1, 4, 94, 4, "Flop"),
            event("GS_CALL", 2, 4, 94, 4, "Flop"),
            event("GS_RAISE", 0, 16, 82, 16, "Flop"),
            event("GS_FOLD", 1, 4, 94, 4, "Flop"),
            event("GS_FOLD", 2, 4, 94, 4, "Flop"),
            event("GS_COLLECT_POT", stage="Flop", POT="9999"),
            event("HAND_FINISHED", stage="Flop"),
        ],
    }


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "hands.jsonl"
    path.write_text(json.dumps(synthetic_hand(), ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def test_import_keeps_unicode_separators_and_counts_broken_lines_and_duplicates(tmp_path):
    raw = synthetic_hand()
    raw["actions"][2]["nick"] = "Player\u0085Name\u2028Test"
    line = json.dumps(raw, ensure_ascii=False)
    source = tmp_path / "input.jsonl"
    source.write_text("\ufeff" + line + "\n" + line + '\n{"cut":\n', encoding="utf-8")
    hands, errors, duplicates = load_pokerist(source)
    assert len(hands) == duplicates == len(errors) == 1
    assert hands[0]["actions"][2]["nick"] == "Player\u0085Name\u2028Test"
    assert ":3:" in errors[0]


def test_only_committed_payments_change_chips_and_snapshots_are_independent():
    hand = replay_hand(synthetic_hand(), 1)
    frames = hand["frames"]
    assert len(hand["decisions"]) == 3  # SB offer/forced post is not a choice.
    assert frames[0]["pot"] == 0
    assert next(f for f in frames if f["label"] == "Flop 공개")["pot"] == 6
    assert frames[-1]["pot"] == 30  # check/fold stale AMOUNT and COLLECT_POT never pay chips.
    assert frames[-1]["recorded_pot"] == 18
    hero = next(p for p in frames[-1]["players"] if p["seat"] == 0)
    assert (hero["stack"], hero["total"]) == (82, 18)  # no fictional payout
    assert frames[0]["players"][0]["stack"] == 100
    assert frames[0]["players"][0]["bet"] == 0
    assert hand["decisions"][-1]["context"]["to_call"] == 4
    assert hand["decisions"][-1]["action"]["name"] == "RAISE"


def test_big_blind_option_bet_is_a_raise_to_the_total_street_amount():
    raw = synthetic_hand()
    raw["hero"]["seat"], raw["hero"]["nick"] = 1, "Player1"
    raw["actions"] = [
        event("GS_SMALL_BLIND", 0, 1, 99, 1),
        event("GS_BIG_BLIND", 1, 2, 98, 2),
        event("GS_CALL", 2, 2, 98, 2),
        event("GS_CALL", 0, 1, 98, 2),
        event("GS_BET", 1, 4, 94, 6),
        event("GS_FOLD", 2, stack=98),
        event("GS_FOLD", 0, stack=98),
        event("HAND_FINISHED"),
    ]
    raw["board"], raw["showdown"], raw["pot"], raw["net"] = [], [], 6, 4
    hand = replay_hand(raw, 1)
    (d,) = hand["decisions"]
    assert d["context"]["to_call"] == 0
    assert d["action"] == {"seat": 1, "name": "RAISE", "label": "레이즈", "paid": 4, "to": 6}
    assert "레이즈" in hand["frames"][d["action_frame"]]["label"]


@pytest.mark.parametrize("all_in,active", [(False, 2), (True, 3)])
def test_departed_players_keep_contributions_and_all_in_pot_eligibility(all_in, active):
    raw = synthetic_hand()
    preflop = raw["actions"][:7]
    if all_in:
        preflop[3] = event("GS_CALL", 2, 2, 0, 2)
    newcomer = event("GS_NEW_PLAYER", 2, stack=1000)
    newcomer["nick"] = "Replacement"
    raw["actions"] = preflop + [
        event("GS_STANDUP_DESK", 2),
        newcomer,
        event("GS_FLOP", stage="Flop"),
        event("GS_CHECK", 0, stack=98, stage="Flop"),
        event("GS_BET", 1, 4, 94, 4, "Flop"),
        event("GS_CALL", 0, 4, 94, 4, "Flop"),
        event("HAND_FINISHED", stage="Flop"),
    ]
    raw["pot"], raw["net"] = 14, 8
    hand = replay_hand(raw, 1)
    flop = next(d for d in hand["decisions"] if d["stage"] == "Flop")
    assert flop["context"]["active"] == active
    assert (flop["context"]["street"] is not None) == (not all_in)
    departure = next(f for f in hand["frames"] if f.get("action", {}) and f["action"]["name"] == "LEAVE")
    departed = next(p for p in departure["players"] if p["seat"] == 2)
    assert departed["departed"] and not departed["folded"]
    assert departed["total"] == 2 and departure["pot"] == 6
    assert departed["all_in"] == all_in
    assert departed["stack"] == (0 if all_in else 98)
    assert hand["frames"][-1]["pot"] == 14
    assert hand["frames"][-1]["players"][2]["nick"] == "Player2"


def test_departure_with_unknown_stack_does_not_create_confident_grades():
    raw = synthetic_hand()
    del raw["actions"][3]["attrs"]["D_AMOUNT"]
    raw["actions"].insert(7, event("GS_STANDUP_DESK", 2))
    raw["actions"] = [a for i, a in enumerate(raw["actions"]) if not (i > 7 and a["who"] == 2)]
    hand = review_hand(replay_hand(raw, 1))
    assert any("이탈" in w and "스택" in w for w in hand["warnings"])
    assert all(d["review"]["grade"] == "unscored" for d in hand["decisions"])


def test_replay_never_shows_future_board_or_opponent_cards():
    hand = replay_hand(synthetic_hand(), 1)
    for frame in hand["frames"]:
        assert len(frame["board"]) == (0 if frame["stage"] == "Preflop" else 3)
        if not frame["finished"]:
            assert all(not p["cards"] for p in frame["players"] if p["seat"] != 0)
    assert hand["frames"][-1]["players"][1]["cards"] == ["T♥", "T♦"]
    assert hand["decisions"][-1]["context"]["board"] == ["A♥", "J/s4", "T/s4"]


def test_hand_boundary_contamination_and_missing_start_are_flagged():
    raw = synthetic_hand()
    raw["actions"].extend([event("GS_RIVER", stage="River"), event("GS_CALL", 0, 50, 32, 50, "River")])
    hand = review_hand(replay_hand(raw, 1))
    assert hand["net"] is None
    assert hand["frames"][-1]["board"] == []
    assert hand["frames"][-1]["recorded_pot"] is None
    assert all(d["review"]["grade"] == "unscored" for d in hand["decisions"])
    raw["actions"] = raw["actions"][3:-2]
    partial = replay_hand(raw, 1)
    assert partial["warnings"] and partial["frames"][-1]["pot"] is None


@pytest.mark.parametrize("trailing_event", ["GS_OWN_CARDS", "GS_SMALL_BLIND", "GS_BIG_BLIND", "GS_ANTE"])
def test_new_hand_metadata_after_finish_is_never_reused(trailing_event):
    raw = synthetic_hand()
    raw["hero"]["cards"] = ["4♥", "7♦"]
    raw["actions"].append(event(trailing_event, 0, status="1"))
    hand = review_hand(replay_hand(raw, 1))
    assert hand["warnings"] and hand["net"] is None
    assert hand["hero"]["cards"] == [] and hand["hero"]["position"] is None
    assert all(not f["board"] and not f["players"][0]["cards"] for f in hand["frames"])
    assert all(d["review"]["basis"] == "unavailable" for d in hand["decisions"])


def test_normal_attention_tail_does_not_poison_completed_hand():
    raw = synthetic_hand()
    raw["actions"].append(event("GS_START_ATTENTION", stage="Flop"))
    hand = review_hand(replay_hand(raw, 1))
    assert not hand["warnings"] and hand["net"] == 12
    assert hand["decisions"][-1]["review"]["grade"] == "best"


def test_all_in_without_d_amount_subtracts_payment_and_does_not_use_final_stack():
    raw = synthetic_hand()
    raw["actions"][11] = event("GS_RAISE", 0, 98, total=98, stage="Flop")
    hand = replay_hand(raw, 1)
    hero = hand["frames"][-1]["players"][0]
    assert hero["all_in"] and hero["stack"] == 0


def test_result_and_future_board_do_not_change_review():
    raw = synthetic_hand()
    original = review_hand(replay_hand(raw, 1))
    raw["net"] = -100000
    raw["board"][3:] = ["A♣", "Q♦"]
    raw["showdown"] = [{"place": 1, "cards": [{"label": "4♥"}, {"label": "4♦"}]}]
    changed = review_hand(replay_hand(raw, 1))
    assert [d["review"] for d in changed["decisions"]] == [d["review"] for d in original["decisions"]]
    assert changed["decisions"][-1]["review"]["grade"] == "best"
    assert changed["decisions"][-1]["review"]["basis"] == "heuristic"
    assert "loss_bb" not in changed["decisions"][-1]["review"]


def test_nuts_handles_suit_four_and_shared_board_without_claiming_equity():
    assert canonical_card("10/s4") == "Ts"
    assert made_hand(("K♦", "Q♥"), ("A♥", "J/s4", "T/s4")) == ("스트레이트", True)
    assert not made_hand(("2♥", "3♦"), ("A/s4", "K/s4", "Q/s4", "J/s4", "T/s4"))[1]


def test_inline_report_escapes_script_injection_and_loads_packaged_template(source, tmp_path):
    raw = synthetic_hand()
    evil = '</script><script>globalThis.pwned=1</script><img src=x onerror="alert(1)">'
    raw["hero"]["nick"] = evil
    for a in raw["actions"]:
        if a["who"] == 0:
            a["nick"] = evil
    source.write_text(json.dumps(raw), encoding="utf-8")
    out = tmp_path / "report.html"
    write_report(source, out)
    html = out.read_text()
    assert evil not in html
    payload = json.loads(re.search(r'<script type="application/json" id="report-data">(.*?)</script>', html)[1])
    assert payload["hands"][0]["hero"]["nick"] == evil
    assert "connect-src 'none'" in html
    with pytest.raises(ValueError):
        write_report(source, source)


def test_solver_receives_pre_action_path_only_and_preserves_ev_units(monkeypatch):
    context = {
        "trustworthy": True,
        "board": ["K/s4", "7♦", "2♣", "3♥", "9/s4"],
        "cards": ["K♥", "K♦"],
        "bb": 2,
        "active": 2,
        "street": {
            "oop": 0,
            "path": ["CHECK"],
            "pot_bb": 10,
            "eff_bb": 10,
            "board": ["K/s4", "7♦", "2♣", "3♥", "9/s4"],
        },
    }
    calls = []

    def solve(*args, **kwargs):
        calls.append((args, kwargs))
        return {"actions": ["CHECK", "BET 75"], "ev": {"CHECK": 1.0, "BET 75": 4.2}, "exploitability": 0.001}

    monkeypatch.setattr(ev_engine, "solve_node", solve)
    scored, note = solver_review(context, {"name": "CHECK"}, 1, ("KK", "QQ,JJ"))
    assert note is None and scored["grade"] == "blunder" and scored["loss_bb"] == 3.2
    assert calls[0][0][:4] == (["Ks", "7d", "2c", "3h", "9s"], "KK", "QQ,JJ", 10)
    assert calls[0][1]["path"] == ["CHECK"]
    assert calls[0][1]["timeout_seconds"] == 45
    context["active"] = 3
    assert solver_review(context, {"name": "CHECK"}, 1, ("KK", "QQ"))[0] is None
    assert len(calls) == 1


def test_solver_failure_or_nonconvergence_never_creates_a_grade(monkeypatch):
    context = {
        "trustworthy": True,
        "board": ["K/s4", "7♦", "2♣", "3♥"],
        "cards": ["K♥", "K♦"],
        "bb": 2,
        "active": 2,
        "street": {"oop": 0, "path": [], "pot_bb": 10, "eff_bb": 10, "board": ["K/s4", "7♦", "2♣", "3♥"]},
    }
    monkeypatch.setattr(
        ev_engine, "solve_node", lambda *a, **k: {"actions": ["CHECK"], "ev": {"CHECK": 1}, "exploitability": 1}
    )
    assert solver_review(context, {"name": "CHECK"}, 0, ("KK", "QQ"))[0] is None

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired("ev_rust", 45)

    monkeypatch.setattr(ev_engine, "solve_node", timeout)
    assert "시간 제한" in solver_review(context, {"name": "CHECK"}, 0, ("KK", "QQ"))[1]


@pytest.mark.parametrize("damage", ["bad_card", "bad_seat", "bad_amount", "bad_stage", "bad_action"])
def test_malformed_record_is_reported_and_other_hands_still_load(tmp_path, damage):
    bad = synthetic_hand()
    if damage == "bad_card":
        bad["hero"]["cards"][0] = "X?"
    elif damage == "bad_seat":
        bad["hero"]["seat"] = None
    elif damage == "bad_amount":
        bad["actions"][1]["attrs"]["AMOUNT"] = "NaN"
    elif damage == "bad_stage":
        bad["actions"][1]["stage"] = "Unknown"
    else:
        bad["actions"][1] = None
    path = tmp_path / "input.jsonl"
    path.write_text(json.dumps(bad) + "\n" + json.dumps(synthetic_hand()), encoding="utf-8")
    report = build_report(path)
    assert len(report["hands"]) == len(report["errors"]) == 1


def test_cli_creates_offline_report_and_rejects_one_sided_ranges(source, tmp_path):
    out = tmp_path / "view.html"
    result = subprocess.run(
        [sys.executable, "-m", "hand_review.analyze", "replay", str(source), "-o", str(out)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0 and out.exists() and "1핸드" in result.stdout
    rejected = subprocess.run(
        [sys.executable, "-m", "hand_review.analyze", "replay", str(source), "--oop-range", "AA"],
        capture_output=True,
        text=True,
    )
    assert rejected.returncode == 2


def test_incomplete_hand_has_no_result_and_stale_metadata_does_not_assign_a_payout():
    raw = copy.deepcopy(synthetic_hand())
    raw["actions"].pop()
    hand = replay_hand(raw, 1)
    assert hand["net"] is None and not any(f["finished"] for f in hand["frames"])
    assert hand["warnings"]


def test_short_stack_pot_odds_exclude_ineligible_side_pot_and_cannot_raise():
    raw = synthetic_hand()
    raw["actions"][8] = event("GS_CHECK", 0, stack=3, stage="Flop")
    # Model a known short stack at the start, without a fictional mid-hand top-up.
    raw["actions"][0]["attrs"]["D_AMOUNT"] = "5"
    raw["actions"][1]["attrs"]["D_AMOUNT"] = "4"
    raw["actions"][4]["attrs"]["D_AMOUNT"] = "3"
    raw["actions"][11] = event("GS_CALL", 0, 3, total=3, stage="Flop")
    hand = review_hand(replay_hand(raw, 1))
    spot = hand["decisions"][-1]["spot"]
    # Totals before call: Hero 2, opponents 6 each. Hero's final total is 5.
    # Eligible pot is 2+5+5, not 2+6+6; required equity = 3/(12+3).
    assert spot["pot_odds"] == 0.2 and not spot["can_raise"]


@pytest.mark.skipif(not ev_engine.available(), reason="optional ev_rust engine not built")
def test_real_solver_scores_demo_hu_turn_and_river_without_scoring_multiway():
    report = build_report(Path(__file__).parents[1] / "samples/pokerist/demo.jsonl", ("KK,77,22,54s,65s", "QQ,JJ"))
    scored = [(h, d) for h in report["hands"] for d in h["decisions"] if d["review"]["basis"] == "solver"]
    assert len(scored) == 2
    assert {d["stage"] for _, d in scored} == {"Turn", "River"}
    assert all(d["spot"]["active"] == 2 and d["review"]["loss_bb"] >= 0 for _, d in scored)


def test_public_demo_covers_both_candidate_filters_with_valid_synthetic_hands():
    report = build_report(Path(__file__).parents[1] / "samples/pokerist/demo.jsonl")
    assert not report["errors"] and all(not h["warnings"] for h in report["hands"])
    assert report["grades"]["blunder"] > 0 and report["grades"]["best"] > 0
    assert any(
        d["stage"] == "Preflop" and d["spot"]["to_call"] == 0 and d["action"]["name"] == "RAISE"
        for h in report["hands"]
        for d in h["decisions"]
    )
