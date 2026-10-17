from collections import defaultdict
from pathlib import Path

from hand_review.analyze import Stats, analyze_hand, icm, load_hands

S = Path(__file__).parent.parent / "samples"


def test_allin_ev_and_preflop_stats():
    stats = defaultdict(Stats)
    for hh in load_hands(S / "cash" / "cash_allin.phh"):
        analyze_hand(hh, stats, samples=20000)
    hero, v1, v2 = stats["Hero"], stats["Villain1"], stats["Villain2"]
    assert hero.net_bb == 100.5  # 401칩 팟 획득 - 200 투자, bb=2
    # AA vs KK 프리플랍 ≈ 82%: 0.82*401 - 200 ≈ 128.8칩 ≈ 64bb
    assert 60 < hero.ev_bb < 69, hero.ev_bb
    assert abs(hero.ev_bb + v2.ev_bb + v1.ev_bb) < 1e-6  # 제로섬
    assert (hero.vpip, hero.pfr, hero.threebet, hero.threebet_opp) == (1, 1, 0, 0)
    assert (v2.vpip, v2.pfr, v2.threebet, v2.threebet_opp) == (1, 1, 1, 1)
    assert (v1.vpip, v1.threebet_opp) == (0, 1)


def test_pokerstars_no_allin():
    stats = defaultdict(Stats)
    for hh in load_hands(S / "cash" / "pokerstars_cash.txt"):
        analyze_hand(hh, stats)
    hero = stats["Hero"]
    # 팟 1.45 - 레이크 0.02 = 1.43 수령, 투자 0.70 → +0.73 = 7.3bb
    assert round(hero.net_bb, 6) == 7.3 and hero.ev_bb == hero.net_bb
    assert stats["VillainB"].vpip == 1 and stats["VillainA"].vpip == 0


def test_pokerstars_tournament_antes_and_shown_cards():
    stats = defaultdict(Stats)
    for hh in load_hands(S / "mtt" / "pokerstars_mtt.txt"):
        analyze_hand(hh, stats, samples=20000)
    hero = stats["Hero"]
    assert hero.net_bb == -25.0  # 앤티 10 + 2490 올인 = 2500칩, bb=100
    # AQo vs JJ ≈ 43%: 0.43*5060 - 2500 ≈ -324칩 ≈ -3.2bb (쇼다운 카드로 올인 EV 계산)
    assert -4.5 < hero.ev_bb < -2.0, hero.ev_bb


def test_icm():
    assert all(abs(e - 100 / 3) < 1e-9 for e in icm([1, 1, 1], [50, 30, 20]))
    a, b = icm([3000, 1000], [100])
    assert abs(a - 75) < 1e-9 and abs(b - 25) < 1e-9
    big, mid, small = icm([5000, 3000, 2000], [50, 30, 20])
    assert big < 50 * 1.0 and big / 100 < 0.5  # 칩 50%여도 상금 비중은 50% 미만


def test_unreadable_and_unfinished_hands_are_flagged(tmp_path):
    import pytest

    plo = tmp_path / "plo.txt"
    plo.write_text((S / "cash" / "pokerstars_cash.txt").read_text().replace("Hold'em No Limit", "Omaha Pot Limit"))
    assert list(load_hands(plo)) == [None]  # 조용히 사라지지 않고 None으로 표시

    unfinished = tmp_path / "cut.phh"
    unfinished.write_text(
        'variant = "NT"\nantes = [0, 0]\nblinds_or_straddles = [1, 2]\nmin_bet = 2\n'
        'starting_stacks = [100, 100]\nactions = ["d dh p1 AsKs", "d dh p2 QhQd", "p1 cbr 6"]\n'
    )
    (hh,) = load_hands(unfinished)
    with pytest.raises(ValueError):
        analyze_hand(hh, defaultdict(Stats))


def test_fold_to_raise_counts_postflop_raises_only():
    stats = defaultdict(Stats)
    for hh in load_hands(S / "postflop" / "postflop_decision.phh"):
        analyze_hand(hh, stats)
    # Hero는 플랍 벳(레이즈 아님)에 폴드 → F2R에 안 셈. 프리플랍 레이즈도 제외
    assert (stats["Hero"].raise_faced, stats["Villain"].raise_faced) == (0, 0)

    for hh in load_hands(S / "postflop" / "fold_to_raise.phh"):
        analyze_hand(hh, stats)
    # Villain 벳 → Hero 레이즈 → Villain 폴드
    assert (stats["Villain"].raise_faced, stats["Villain"].folded_to_raise) == (1, 1)
    assert stats["Hero"].raise_faced == 0
