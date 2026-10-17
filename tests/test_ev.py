"""턴·리버 EV 채점 테스트. ev_rust 바이너리가 없으면(CI 포함) 건너뜀."""

from collections import defaultdict
from pathlib import Path

import pytest

from hand_review import ev_engine
from hand_review.analyze import Stats, action_name, analyze_hand, load_hands, score_decision

S = Path(__file__).parent.parent / "samples"
# 양극화(밸류+에어) vs 블러프캐처, 리버 Ks7d2c3h9s, 팟 10bb, 스택 10bb
RANGES = ("KK,77,22,54s,65s", "QQ,JJ")
RIVER = {"board": ["Ks", "7d", "2c", "3h", "9s"], "pot_bb": 10.0, "eff_bb": 10.0, "oop": 0, "path": []}
needs_engine = pytest.mark.skipif(not ev_engine.available(), reason="ev_rust 미빌드 (선택 기능)")


def test_action_name_and_nearest():
    assert action_name("cc", 0, 0, 100, 20) == "CHECK"
    assert action_name("cc", 0, 6, 100, 20) == "CALL"
    assert action_name("cbr", 15, 0, 100, 20) == "BET 75"
    assert action_name("cbr", 100, 0, 100, 20) == "ALLIN"
    assert ev_engine.nearest_action("BET 70", ["CHECK", "BET 33", "BET 75", "ALLIN"]) == "BET 75"
    assert ev_engine.nearest_action("RAISE 250", ["FOLD", "CALL"]) is None


@needs_engine
def test_mixed_actions_cost_nothing():
    # 균형에서 섞는 액션은 EV가 같다 → 빈도 근사((1-freq)*pot)와 달리 loss ≈ 0
    assert score_decision(dict(RIVER), 0, "5s4s", "ALLIN", RANGES) < 0.1  # 에어 블러프
    facing = {**RIVER, "path": ["ALLIN"]}
    assert score_decision(facing, 1, "QhQd", "CALL", RANGES) < 0.1  # 블러프캐처 콜
    assert score_decision(facing, 1, "QhQd", "FOLD", RANGES) < 0.1  # 블러프캐처 폴드


@needs_engine
def test_missed_value_bet_is_scored_end_to_end():
    stats = defaultdict(Stats)
    for hh in load_hands(S / "ev" / "turn_river_checks.phh"):
        analyze_hand(hh, stats, ev_ranges=RANGES)
    hero, villain = stats["Hero"], stats["Villain"]
    assert hero.decisions == villain.decisions == 2  # 턴·리버 각 1결정, 플랍은 채점 안 함
    assert hero.ev_loss_bb > 3  # 리버 KK 체크 = 밸류 벳을 놓침 (솔버 기준 약 3.3bb)
    assert villain.ev_loss_bb < 0.1
