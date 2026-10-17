import copy
import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest
from pokerkit import StandardHighHand

from hand_review import ev_engine
from hand_review.coaching import _rollout, _settle, action, candidates, card_id, estimate, parse_range, rank7
from hand_review.pokerist import player_key, replay_hand
from hand_review.profiles import Evidence
from hand_review.recommendations import AnalysisOptions, analyze, shifted_locks, solve_recommendation


def cards(ids):
    return "".join("23456789TJQKA"[i // 4] + "hdcs"[i % 4] for i in ids)


def demo():
    return [
        json.loads(x) for x in (Path(__file__).parents[1] / "samples/pokerist/demo.jsonl").read_text().split("\n") if x
    ]


def context():
    return {
        "stage": "River",
        "hero_seat": 0,
        "cards": ["A♥", "A♦"],
        "board": ["2/s4", "3♣", "4♥", "8/s4", "9♦"],
        "position": "SB",
        "bb": 1,
        "pot": 20,
        "eligible_pot": 20,
        "stack": 10,
        "to_call": 10,
        "trustworthy": True,
        "active": 2,
        "street": None,
        "min_raise_to": 20,
        "raise_reopened": True,
        "acted": [],
        "history": [],
        "players": [
            {
                "seat": 0,
                "position": "SB",
                "stack": 10,
                "total": 5,
                "bet": 0,
                "folded": False,
                "departed": False,
                "all_in": False,
            },
            {
                "seat": 1,
                "position": "BB",
                "stack": 0,
                "total": 15,
                "bet": 10,
                "folded": False,
                "departed": False,
                "all_in": True,
            },
        ],
    }


def test_fast_evaluator_matches_independent_pokerkit_ordering():
    rng = random.Random(7282)
    for size in (5, 6, 7):
        for _ in range(120):
            a, b = tuple(sorted(rng.sample(range(52), size))), tuple(sorted(rng.sample(range(52), size)))
            x, y = StandardHighHand.from_game(cards(a)), StandardHighHand.from_game(cards(b))
            assert (rank7(a) > rank7(b)) == (x > y)
            assert (rank7(a) == rank7(b)) == (x == y)
    assert rank7(tuple(sorted(card_id(c) for c in ("Ah", "2h", "3h", "4h", "5h", "Ks", "Qc"))))[:2] == (8, 5)


def test_weighted_ranges_validate_combos_plus_and_blocked_cards():
    assert len(parse_range("AA,AKs")) == 10
    assert len(parse_range("TT+")) == 30
    assert len(parse_range("ATs+")) == 16
    assert parse_range("AhKd:0.5")[0][2] == 0.5
    for bad in ("", "AA:NaN", "AA:2", "AhAh", "invalid", "KAs", "AA:0"):
        with pytest.raises(ValueError):
            parse_range(bad)


def test_default_range_assumptions_are_reproducible_across_process_hash_seeds():
    code = (
        "import json, sys; from hand_review.coaching import default_ranges; "
        "print(json.dumps(default_ranges(json.load(sys.stdin)), sort_keys=True))"
    )
    outputs = [
        subprocess.check_output(
            [sys.executable, "-c", code],
            input=json.dumps(context()),
            text=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        for seed in ("1", "2")
    ]
    assert outputs[0] == outputs[1]


def test_exact_river_call_fold_values_ties_and_departed_all_in():
    c = context()
    c["players"][1]["departed"] = True
    result = estimate(c, {"1": "KcKd"}, samples=16)
    assert result["status"] == "ready"
    assert {a["kind"]: a["ev_bb"] for a in result["actions"]} == {"FOLD": 0, "CALL": 20}
    assert all(a["se_bb"] == 0 for a in result["actions"])
    assert result["recommendation"]["kind"] == "CALL"
    c["board"] = ["T♥", "J♥", "Q♥", "K♥", "A♥"]
    c["cards"] = ["2♦", "2♣"]
    tied = estimate(c, {"1": "3c3d"}, samples=16)
    assert next(a["ev_bb"] for a in tied["actions"] if a["kind"] == "CALL") == 5


def test_layered_pot_accounting_returns_unmatched_excess_and_splits_side_pots():
    players = [
        {"seat": s, "total": total, "folded": False, "departed": False, "all_in": True}
        for s, total in enumerate((100, 50, 100))
    ]
    assert _settle(players, {0: 2, 1: 3, 2: 1}, 0, 50) == 50
    players = players[:2]
    players[0]["total"], players[1]["total"] = 300, 100
    assert _settle(players, {0: 1, 1: 2}, 0, 300) == -100
    players[1]["folded"] = True
    assert _settle(players, {0: 1, 1: 2}, 0, 300) == 100


def test_legal_sizes_handle_bb_option_minimum_raise_and_closed_action():
    c = replay_hand(demo()[-1], 1)["decisions"][0]["context"]
    rows = candidates(c)
    assert rows[0]["kind"] == "CHECK"
    assert all(a["kind"] == "RAISE" and a["to_bb"] >= 2 for a in rows[1:])
    c["raise_reopened"] = False
    assert [a["kind"] for a in candidates(c)] == ["CHECK"]


def test_minimum_raise_exceeding_matching_stack_keeps_legal_amount_and_returns_excess():
    c = context()
    c["players"][0]["stack"] = 100
    c["players"][1].update(stack=1, all_in=False)
    c["policy_ranges"] = {"0": "AhAd", "1": "KcKd"}
    raises = [a for a in candidates(c) if a["kind"] == "RAISE"]
    assert [(a["to_bb"], a["paid_bb"]) for a in raises] == [(20, 20)]
    holes = {0: (card_id("Ah"), card_id("Ad")), 1: (card_id("Kc"), card_id("Kd"))}
    draws = {0: (1, 1, 1), 1: (1, 1, 1)}  # The short opponent calls its last chip.
    assert _rollout(c, raises[0], holes, {0: 2, 1: 1}, draws, 0) == 21
    assert _rollout(c, raises[0], holes, {0: 1, 1: 2}, draws, 0) == -11
    c["players"][0]["stack"] = 15
    assert next(a for a in candidates(c) if a["kind"] == "RAISE")["to_bb"] == 15


def betting_player(seat, position, stack, bet, total=None):
    return {
        "seat": seat,
        "position": position,
        "stack": stack,
        "bet": bet,
        "total": bet if total is None else total,
        "all_in": stack == 0,
        "folded": False,
        "departed": False,
    }


def river_world():
    board = tuple(map(card_id, ("2h", "3d", "4c", "8s", "9h")))
    holes = {
        0: tuple(map(card_id, ("9d", "9c"))),
        1: tuple(map(card_id, ("8d", "8c"))),
        2: tuple(map(card_id, ("As", "Ah"))),
    }
    ranks = {seat: rank7(tuple(sorted(own + board))) for seat, own in holes.items()}
    return holes, ranks


@pytest.mark.parametrize(("all_in_to", "expected"), [(125, 350), (200, 950)])
def test_opponent_can_reraise_only_when_a_full_raise_reopens_its_action(all_in_to, expected):
    c = context()
    c.update(
        cards=["9♦", "9♣"],
        board=["2♥", "3♦", "4♣", "8/s4", "9♥"],
        pot=200 + all_in_to,
        stack=900,
        active=3,
        to_call=all_in_to - 100,
        min_raise_to=all_in_to + 100,
        raise_reopened=all_in_to >= 200,
        acted=[0, 1, 2],
        history=[{"seat": 2, "stage": "River", "name": "RAISE"}],
        policy_ranges={"0": "random", "1": "random", "2": "random"},
        players=[
            betting_player(0, "SB", 900, 100),
            betting_player(1, "BB", 900, 100),
            betting_player(2, "BTN", 0, all_in_to),
        ],
    )
    chosen = next(a for a in candidates(c) if a["kind"] == "CALL")
    holes, ranks = river_world()
    # SB bet 100, BB called, BTN shoved. Hero always wins this fixed runout.
    # A shove to 125 leaves BB only call/fold; a full raise to 200 reopens it.
    assert _rollout(c, chosen, holes, ranks, {s: (1, 1, 1) for s in holes}, 0) == expected


def test_short_caller_uses_only_the_pot_it_can_win_when_deciding_to_call():
    c = context()
    c.update(
        cards=["9♦", "9♣"],
        board=["2♥", "3♦", "4♣", "8/s4", "9♥"],
        pot=1003,
        stack=2000,
        active=3,
        to_call=1000,
        min_raise_to=2000,
        raise_reopened=True,
        acted=[0, 1, 2],
        history=[{"seat": 1, "stage": "River", "name": "BET"}],
        policy_ranges={"0": "random", "1": "random", "2": "random"},
        players=[
            betting_player(0, "SB", 2000, 0, 1),
            betting_player(1, "BTN", 1000, 1000, 1001),
            betting_player(2, "BB", 10, 0, 1),
        ],
    )
    board = tuple(map(card_id, ("2h", "3d", "4c", "8s", "9h")))
    holes = {
        0: tuple(map(card_id, ("9d", "9c"))),
        1: tuple(map(card_id, ("As", "Ah"))),
        2: tuple(map(card_id, ("8d", "7d"))),
    }
    ranks = {seat: rank7(tuple(sorted(own + board))) for seat, own in holes.items()}
    # The short BB can win 33 by calling 10, not the deep players' 2013.
    # This draw folds using 10/33 odds, but calls using the erroneous 10/2013.
    draws = {s: (0.1, 0.1, 0.1) for s in holes}
    assert _rollout(c, action("CALL", 1000, 0, 1003, 1), holes, ranks, draws, 0) == 1003


def small_heads_up_context(hero_stack=20, opponent_stack=20):
    c = context()
    c.update(
        cards=["A/s4", "A♥"],
        board=["2/s4", "3♥", "4♦", "6♣", "7♣"],
        pot=2,
        stack=hero_stack,
        to_call=0,
        min_raise_to=1,
        players=[betting_player(0, "SB", hero_stack, 0, 1), betting_player(1, "BB", opponent_stack, 0, 1)],
    )
    c["street"] = {
        "board": c["board"],
        "oop": 0,
        "players": copy.deepcopy(c["players"]),
        "pot_bb": 2,
        "eff_bb": min(hero_stack, opponent_stack),
        "path": [],
    }
    return c


@pytest.mark.skipif(not ev_engine.available(), reason="optional Rust engine not built")
@pytest.mark.parametrize(("hero_stack", "opponent_stack"), [(20, 20), (0.5, 20), (20, 0.5)])
def test_solver_minimum_bets_respect_real_stacks_and_short_all_in_exceptions(hero_stack, opponent_stack):
    c = small_heads_up_context(hero_stack, opponent_stack)
    result = solve_recommendation(
        c, {"0": "AsAh,QsQh", "1": "KsKh"}, AnalysisOptions(solver_timeout=8, node_locks=False)
    )
    assert result["status"] == "ready", result
    bets = [a for a in result["actions"] if a["kind"] == "BET"]
    assert bets
    assert all(min(1, hero_stack) <= a["paid_bb"] <= hero_stack for a in bets)
    assert min(a["paid_bb"] for a in bets) == min(1, hero_stack)
    if hero_stack == 20 and opponent_stack == 0.5:
        assert all(a["uncalled_return_bb"] == 0.5 for a in bets)


def test_solver_withholds_results_from_an_engine_without_whole_tree_minimum_support(monkeypatch):
    # The current node looks legal, but an older engine gives no guarantee about
    # the opponent's branches or future streets. It must not be labelled ready.
    monkeypatch.setattr(ev_engine, "available", lambda: True)
    monkeypatch.setattr(
        ev_engine,
        "solve_node",
        lambda **kwargs: {
            "actions": ["CHECK"],
            "amounts": [{"kind": "CHECK", "paid": 0, "to": 0}],
            "strategy": [1],
            "ev": {"CHECK": 2},
            "pot": 2,
            "exploitability": 0,
            "solve_ms": 1,
        },
    )
    result = solve_recommendation(
        small_heads_up_context(), {"0": "AsAh,QsQh", "1": "KsKh"}, AnalysisOptions(node_locks=False)
    )
    assert result["status"] == "unavailable"
    assert "다시 빌드" in result["note"]


def test_model_recommendation_does_not_see_result_future_board_or_recorded_action():
    raw = demo()[0]
    original = replay_hand(raw, 1)["decisions"][0]
    changed = copy.deepcopy(raw)
    changed["net"] = -999
    changed["showdown"] = []
    changed["board"][3:] = ["4♣", "9♦"]
    changed["actions"][4]["event"] = "GS_FOLD"
    altered = replay_hand(changed, 1)["decisions"][0]
    assert original["context"] == altered["context"]
    assert estimate(original["context"], samples=16) == estimate(altered["context"], samples=16)


def test_opponent_range_changes_computed_payoff_and_invalid_ranges_are_withheld():
    c = context()
    c["cards"] = ["Q♥", "Q♦"]
    strong = estimate(c, {"1": "KcKd"}, samples=16)
    weak = estimate(c, {"1": "JcJd"}, samples=16)
    assert strong["recommendation"]["kind"] == "FOLD"
    assert weak["recommendation"]["kind"] == "CALL"
    rejected = analyze(c, {}, AnalysisOptions(samples=16, solver=False), {"1": "QhQd"})
    assert rejected["status"] == "unavailable"


def test_stable_ids_do_not_merge_names_and_only_earlier_complete_hands_are_evidence():
    old = demo()[-1]
    for a in old["actions"]:
        if a["who"] is not None:
            a["attrs"].update(PID=f"synthetic-{a['who']}", PARTNER_ID="synthetic")
            if a["who"] != 1:
                a["nick"] = "Same generic label"
    prior = replay_hand(old, 1)
    target = copy.deepcopy(prior)
    target["started_ts"] = prior["ended_ts"] + 1
    future = copy.deepcopy(prior)
    future["ended_ts"] = target["started_ts"] + 100
    stats = Evidence([prior, target, future]).before(target)
    assert len(stats) == 3
    assert all(s["hands"] == 1 for s in stats.values())
    assert player_key({"PID": "synthetic-0", "PARTNER_ID": "a"}) != player_key(
        {"PID": "synthetic-0", "PARTNER_ID": "b"}
    )


@pytest.mark.skipif(not ev_engine.available(), reason="optional Rust engine not built")
def test_node_lock_recommendation_matches_closed_form_river_bet_ev():
    params = dict(
        board=["2s", "3h", "4d", "6c", "7c"],
        oop_range="AsAh,QsQh",
        ip_range="KsKh",
        pot=20,
        eff_stack=10,
        hero="oop",
        hero_combo="QsQh",
        bet_sizes="a",
        max_iter=2000,
        include_responses=True,
        timeout_seconds=20,
    )
    baseline = ev_engine.solve_node(**params)
    response = next(n for n in baseline["responses"] if "FOLD" in n["actions"])
    n = len(response["strategy"]) // len(response["actions"])
    for fold_probability, expected in ((0.25, -2.5), (0.5, 5.0)):
        locked = [fold_probability] * n + [1 - fold_probability] * n
        result = ev_engine.solve_node(**params, locks=[{"history": response["history"], "strategy": locked}])
        bet = next(a for a in result["actions"] if a != "CHECK")
        assert result["ev"][bet] == pytest.approx(expected, abs=0.03)
        assert result["ev"]["CHECK"] == pytest.approx(0, abs=0.03)
        assert result["strategy"][result["actions"].index(bet)] == pytest.approx(float(expected > 0), abs=0.01)
        assert result["constrained"]
    locks = shifted_locks([response], -0.15)
    assert all(0 <= x <= 1 for x in locks[0]["strategy"])
