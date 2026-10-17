"""포커 핸드 히스토리 분석기: VPIP/PFR/3Bet, bb/100, 올인 EV, ICM, 토너먼트 ROI.

사용법:
  hand-review hands <파일|폴더> [--hero 이름]   # .phh / .phhs / PokerStars .txt
  hand-review icm --stacks 5000 3000 2000 --payouts 50 30 20
  hand-review mtt tournaments.csv              # date,name,buyin,prize
  hand-review tui --hands samples/cash --mtt samples/mtt/tournaments.csv
"""

import argparse
import csv
import re
import warnings
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from functools import partial
from pathlib import Path

from pokerkit import Deck, HandHistory, PokerStarsParser, StandardHighHand, calculate_equities, rake

from hand_review import ev_engine
from hand_review.ranges import load_range_csv

warnings.filterwarnings("ignore", module="pokerkit")


class AntePokerStarsParser(PokerStarsParser):
    # PokerKit 0.7.6의 PokerStars 파서는 앤티를 무시함 → 토너먼트 스택이 틀어짐
    ANTE_POSTING = re.compile(r"(?P<player>.+): posts the ante \D?(?P<ante>[0-9.,]+)")


@dataclass
class Stats:
    hands: int = 0
    net_bb: float = 0.0  # 실제 손익
    ev_bb: float = 0.0  # 올인 시점 equity로 운을 걷어낸 손익
    vpip: int = 0
    pfr: int = 0
    threebet: int = 0
    threebet_opp: int = 0
    raise_faced: int = 0  # 포스트플랍에서 레이즈를 맞은 횟수(벳 제외) (exploit.py 상대 모델링 입력)
    folded_to_raise: int = 0
    decisions: int = 0  # 솔버로 채점한 턴·리버 결정 수 (EV 채점 켰을 때만)
    ev_loss_bb: float = 0.0  # 그 결정들의 EV loss 합: EV(최선 액션) - EV(실제 액션)


def load_hands(path):
    """핸드를 yield, 읽을 수 없는 핸드/파일은 None을 yield(건너뛴 수 집계용)."""
    files = [path] if path.is_file() else sorted(path.rglob("*"))
    for f in files:
        if f.suffix in (".phh", ".phhs"):
            try:
                with f.open("rb") as fp:
                    hands = [HandHistory.load(fp)] if f.suffix == ".phh" else list(HandHistory.load_all(fp))
            except (ValueError, KeyError, TypeError):
                yield None
                continue
            yield from hands
        elif f.suffix == ".txt":
            # ponytail: PokerStars 포맷만 지원, GG 등은 파서 추가 필요
            try:
                text = f.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:  # 폴더 안의 다른 인코딩 메모 파일 하나 때문에 전체가 죽지 않게
                yield None
                continue
            for chunk in re.split(r"\n(?=PokerStars )", text):
                yield from load_pokerstars_hand(chunk)


def load_pokerstars_hand(chunk):
    """PokerKit 파서는 레이크를 0%로 두므로, 요약의 'Total pot X | Rake Y'를 비율로 적용."""
    m = re.search(r"Total pot \D*?([\d.,]+).*?\| Rake \D*?([\d.,]+)", chunk)
    try:  # 미지원 변형(PLO 등)·깨진 핸드: 기본 동작은 traceback만 찍고 버림
        hands = list(AntePokerStarsParser()(chunk, error_status=True))
    except ValueError:
        yield None
        return
    for hh in hands:
        if m:
            total, raked = (Decimal(g.replace(",", "")) for g in m.groups())
            if raked:
                hh.rake = partial(rake, percentage=raked / total)
        yield hh


def allin_ev(state, samples, executor=None):
    """베팅이 끝난 올인 시점이면 플레이어별 팟 기대값(칩)을, 아니면 None."""
    active = [i for i, on in enumerate(state.statuses) if on]
    board = list(state.get_board_cards(0))
    if (
        len(active) < 2
        or len(board) == 5
        or any(state.bets)
        or sum(state.stacks[i] > 0 for i in active) > 1
        or any(c.unknown_status for i in active for c in state.hole_cards[i])
        or any(len(state.hole_cards[i]) != 2 for i in active)
    ):
        return None
    ev = defaultdict(float)
    for pot in state.pots:  # 사이드팟마다 해당 플레이어들끼리 equity 계산
        eligible = [i for i in pot.player_indices if state.statuses[i]]
        equities = calculate_equities(
            [[tuple(state.hole_cards[i])] for i in eligible],
            board,
            2,
            5,
            Deck.STANDARD,
            (StandardHighHand,),
            sample_count=samples,
            executor=executor,
        )
        for i, eq in zip(eligible, equities, strict=True):
            ev[i] += eq * float(pot.unraked_amount)  # 레이크 뺀 팟
    return ev


def reveal_shown_cards(hh):
    """쇼다운에서 공개된 카드를 딜 단계에 채워, 올인 시점에도 상대 카드를 알게 함."""
    shown = {}
    for a in hh.actions:
        who, op, *cards = a.split()
        if op == "sm" and cards and "?" not in cards[0]:
            shown[who] = cards[0]
    hh.actions = [
        f"d dh {a.split()[2]} {shown[a.split()[2]]}" if a.startswith("d dh") and a.split()[2] in shown else a
        for a in hh.actions
    ]


def action_name(op, amount, to_call, all_in_amount, pot):
    """pokerkit 액션 → ev_rust 액션 이름. BET/RAISE는 '현재 팟 대비 %'(ev_rust 표기와 동일)."""
    if op == "f":
        return "FOLD"
    if op == "cc":
        return "CALL" if to_call else "CHECK"
    if amount >= all_in_amount:
        return "ALLIN"
    return f"{'RAISE' if to_call else 'BET'} {round(100 * amount / pot)}"


def score_decision(street, actor, combo, name, ev_ranges):
    """솔버 EV로 결정 하나 채점: (EV loss bb) 또는 채점 불가면 None."""
    # ponytail: 트리 사이즈는 33/75% + 이 스트리트에서 실제로 나온 벳 %, 레이즈는 3x 하나 — 실제 레이즈
    # 사이즈는 가장 가까운 RAISE로 근사. 결정마다 스트리트를 새로 풂(턴 수 초) → 느려지면 노드 여러 개를 한 번에 조회
    path = street["path"]
    sizes = {33, 75} | {int(n.split()[1]) for n in [*path, name] if n.startswith("BET ")}
    try:
        r = ev_engine.solve_node(
            street["board"],
            *ev_ranges,
            street["pot_bb"],
            street["eff_bb"],
            "oop" if actor == street["oop"] else "ip",
            combo,
            path=path,
            bet_sizes=",".join(f"{x}%" for x in sorted(sizes)),
            raise_sizes="3x",
        )
    except RuntimeError:  # 레인지 밖 콤보, 트리 메모리 초과 등
        return None
    chosen = ev_engine.nearest_action(name, r["actions"])
    return None if chosen is None else max(r["evs"]) - r["ev"][chosen]


def analyze_hand(hh, stats, samples=5000, executor=None, ev_ranges=None):
    """ev_ranges=(oop 레인지, ip 레인지)를 주면 턴·리버 헤즈업 결정을 솔버 EV로 채점."""
    reveal_shown_cards(hh)
    names = hh.players or [f"p{i + 1}" for i in range(len(hh.starting_stacks))]
    bb = float(max(hh.blinds_or_straddles))
    start = [float(s) for s in hh.starting_stacks]
    vpip, pfr, tb, tb_opp = set(), set(), set(), set()
    raise_faced, folded_to_raise, street_aggr = defaultdict(int), defaultdict(int), 0
    raises, preflop, ev, to_call = 0, True, None, 0
    street, loss, decisions = None, defaultdict(float), defaultdict(int)
    pot_prev, all_in_prev, holes_prev = 0.0, [0.0] * len(start), [[] for _ in start]

    for state, action in hh.state_actions:
        parts = action.split() if action else []
        if not preflop and parts and parts[0].startswith("p"):
            if to_call and street_aggr >= 2:  # 벳이 아니라 레이즈(이 스트리트 2번째 이상 공격)를 맞음
                i = int(parts[0][1:]) - 1
                raise_faced[i] += 1
                folded_to_raise[i] += parts[1] == "f"
            street_aggr += parts[1] == "cbr"
        if parts[:2] == ["d", "db"]:
            preflop, street_aggr = False, 0
        elif preflop and parts and parts[0].startswith("p"):
            i, op = int(parts[0][1:]) - 1, parts[1]
            if raises == 1:
                tb_opp.add(i)
            if op == "cbr":
                vpip.add(i)
                pfr.add(i)
                if raises == 1:
                    tb.add(i)
                raises += 1
            elif op == "cc" and to_call:
                vpip.add(i)
        if ev_ranges and parts[:2] == ["d", "db"]:
            street = _start_street(state, bb)
        elif street and parts and parts[0].startswith("p") and parts[1] in ("f", "cc", "cbr"):
            i, op = int(parts[0][1:]) - 1, parts[1]
            street["oop"] = street["oop"] if street["oop"] is not None else i  # 스트리트 첫 액터 = OOP
            name = action_name(op, float(parts[2]) if op == "cbr" else 0, to_call, all_in_prev[i], pot_prev)
            if holes_prev[i] and not any(c.unknown_status for c in holes_prev[i]):
                combo = "".join(repr(c) for c in holes_prev[i])
                if (x := score_decision(street, i, combo, name, ev_ranges)) is not None:
                    loss[i] += x
                    decisions[i] += 1
            street["path"].append(name)
        if ev is None and state.status:
            if (pot_ev := allin_ev(state, samples, executor)) is not None:
                ev = {i: pot_ev[i] - (start[i] - float(state.stacks[i])) for i in range(len(start))}
        # state는 같은 객체가 변경되며 재사용되므로 다음 액션용 콜 금액을 값으로 저장
        to_call = state.checking_or_calling_amount if state.actor_index is not None else 0
        pot_prev = float(state.total_pot_amount)  # 칩 단위(벳 %는 비율이라 bb 변환 불필요)
        all_in_prev = [float(b + s) for b, s in zip(state.bets, state.stacks, strict=True)]
        holes_prev = [list(h) for h in state.hole_cards]  # 폴드하면 카드가 사라지므로 액션 전 값
    if state.status:  # 기록이 중간에 끊긴 핸드: 진행 중 스택을 손익으로 세면 안 됨
        raise ValueError("hand not finished")

    for i, name in enumerate(names):
        s = stats[name]
        net = (float(state.stacks[i]) - start[i]) / bb
        s.hands += 1
        s.net_bb += net
        s.ev_bb += ev[i] / bb if ev else net
        s.vpip += i in vpip
        s.pfr += i in pfr
        s.threebet += i in tb
        s.threebet_opp += i in tb_opp
        s.raise_faced += raise_faced[i]
        s.folded_to_raise += folded_to_raise[i]
        s.decisions += decisions[i]
        s.ev_loss_bb += loss[i]


def _start_street(state, bb):
    """턴·리버가 막 깔린 시점, 칩이 남은 두 명만 있으면 채점할 스트리트 정보. 아니면 None."""
    board = [repr(c) for c in state.get_board_cards(0)]
    active = [i for i, on in enumerate(state.statuses) if on]
    # ponytail: 플랍은 채점 안 함(결정), 멀티웨이는 솔버가 헤즈업 전용
    if len(board) < 4 or len(active) != 2 or any(state.stacks[i] <= 0 for i in active):
        return None
    return {
        "board": board,
        "pot_bb": float(state.total_pot_amount) / bb,
        "eff_bb": min(float(state.stacks[i]) for i in active) / bb,
        "oop": None,
        "path": [],
    }


def icm(stacks, payouts):
    """Malmuth-Harville ICM: 칩 스택 → 상금 기대값."""
    ev = [0.0] * len(stacks)

    def go(remaining, place, prob):
        if place == len(payouts) or not remaining:
            return
        total = sum(stacks[i] for i in remaining)
        for i in remaining:
            p = prob * stacks[i] / total
            ev[i] += p * payouts[place]
            go(remaining - {i}, place + 1, p)

    # ponytail: 순열 전수탐색 O(n!/(n-k)!), 파이널 테이블(≤9명)까지만 실용적
    go(frozenset(i for i, s in enumerate(stacks) if s > 0), 0, 1.0)
    return ev


def pct(a, b):
    return f"{100 * a / b:5.1f}" if b else "    -"


HAND_COLUMNS = ("player", "hands", "net bb", "bb/100", "EV bb/100", "VPIP", "PFR", "3Bet", "F2R")


def collect_stats(path, samples, ev_ranges=None):
    """(플레이어별 Stats, 건너뛴 핸드 수, 중복 핸드 수)."""
    stats = defaultdict(Stats)
    seen, skipped, dups = set(), 0, 0
    with ProcessPoolExecutor() as executor:  # 올인 equity 몬테카를로 병렬화
        for hh in load_hands(path):
            if hh is None:
                skipped += 1
                continue
            key = (hh.venue, hh.table, hh.hand)
            if hh.hand is not None and key in seen:
                dups += 1
                continue
            seen.add(key)
            try:
                analyze_hand(hh, stats, samples, executor, ev_ranges)
            except ValueError:
                skipped += 1
    return stats, skipped, dups


def hand_rows(stats, hero):
    rows = [(n, s) for n, s in stats.items() if not hero or n == hero]
    rows.sort(key=lambda r: -r[1].hands)
    rows = [
        (
            n,
            s.hands,
            round(s.net_bb, 1),
            round(100 * s.net_bb / s.hands, 1),
            round(100 * s.ev_bb / s.hands, 1),
            pct(s.vpip, s.hands).strip(),
            pct(s.pfr, s.hands).strip(),
            pct(s.threebet, s.threebet_opp).strip(),
            pct(s.folded_to_raise, s.raise_faced).strip(),
        )
        for n, s in rows
    ]
    return rows


def compute_hand_rows(path, hero, samples):
    """(행 목록, 건너뛴 핸드 수, 중복 핸드 수)."""
    stats, skipped, dups = collect_stats(path, samples)
    return hand_rows(stats, hero), skipped, dups


def report_hands(path, hero, samples, ev_ranges=None):
    stats, skipped, dups = collect_stats(path, samples, ev_ranges)
    rows = hand_rows(stats, hero)
    print(
        f"{'player':<16}{'hands':>6}{'net bb':>9}{'bb/100':>10}{'EV bb/100':>11}"
        f"{'VPIP':>6}{'PFR':>6}{'3Bet':>6}{'F2R':>6}"
    )
    for n, hands, net, bb100, ev100, vpip, pfr, tb, f2r in rows[:20]:
        print(f"{n:<16}{hands:>6}{net:>9.1f}{bb100:>10.1f}{ev100:>11.1f}{vpip:>6}{pfr:>6}{tb:>6}{f2r:>6}")
    if ev_ranges:
        print("\n턴·리버 결정 EV loss (솔버 기준, 헤즈업 팟, 카드를 아는 결정만)")
        print(f"{'player':<16}{'결정':>6}{'loss bb':>10}{'bb/결정':>10}")
        for n, s in sorted(stats.items(), key=lambda r: -r[1].decisions):
            if s.decisions and (not hero or n == hero):
                print(f"{n:<16}{s.decisions:>6}{s.ev_loss_bb:>10.2f}{s.ev_loss_bb / s.decisions:>10.2f}")
    if skipped or dups:
        print(f"\n건너뜀: 읽기 실패/미지원/미완료 {skipped}개, 중복 {dups}개")


def compute_mtt_summary(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    buyin = sum(float(r["buyin"]) for r in rows)
    prize = sum(float(r["prize"]) for r in rows)
    itm = sum(float(r["prize"]) > 0 for r in rows)
    return len(rows), buyin, prize, itm


def report_mtt(path):
    n, buyin, prize, itm = compute_mtt_summary(path)
    print(f"토너먼트 {n}개 | 바이인 {buyin:.2f} | 상금 {prize:.2f} | 손익 {prize - buyin:+.2f}")
    print(f"ROI {pct(prize - buyin, buyin)}% | ITM {pct(itm, n)}%")


def run_tui(hands_path=None, hero=None, samples=5000, mtt_path=None, icm_stacks=None, icm_payouts=None):
    from hand_review.tui import PokerApp

    hand_rows, skipped, dups = compute_hand_rows(hands_path, hero, samples) if hands_path else (None, 0, 0)
    mtt_summary = compute_mtt_summary(mtt_path) if mtt_path else None
    icm_result = (icm_stacks, icm_payouts, icm(icm_stacks, icm_payouts)) if icm_stacks else None
    app = PokerApp(hand_rows, mtt_summary, icm_result)
    if skipped or dups:
        app.sub_title = f"건너뜀 {skipped}개, 중복 {dups}개"
    app.run()


def main():
    ap = argparse.ArgumentParser(prog="hand-review")
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hands")
    h.add_argument("path", type=Path)
    h.add_argument("--hero")
    h.add_argument("--samples", type=int, default=5000)
    h.add_argument("--oop-range", help="턴·리버 EV 채점용 OOP 레인지 (문자열 'AA,KQs:0.5' 또는 CSV 경로)")
    h.add_argument("--ip-range", help="턴·리버 EV 채점용 IP 레인지 (문자열 또는 CSV 경로)")
    r = sub.add_parser("replay", help="Pokerist JSONL을 로컬 브라우저 복기 화면으로 변환")
    r.add_argument("path", type=Path)
    r.add_argument("--output", "-o", type=Path, default=Path("reports/replay.html"))
    r.add_argument("--oop-range", help="선택적 헤즈업 턴·리버 EV 분석용 OOP 레인지")
    r.add_argument("--ip-range", help="선택적 헤즈업 턴·리버 EV 분석용 IP 레인지")
    i = sub.add_parser("icm")
    i.add_argument("--stacks", type=float, nargs="+", required=True)
    i.add_argument("--payouts", type=float, nargs="+", required=True)
    m = sub.add_parser("mtt")
    m.add_argument("path", type=Path)
    t = sub.add_parser("tui")
    t.add_argument("--hands", type=Path)
    t.add_argument("--hero")
    t.add_argument("--samples", type=int, default=5000)
    t.add_argument("--mtt", type=Path)
    t.add_argument("--stacks", type=float, nargs="+")
    t.add_argument("--payouts", type=float, nargs="+")
    a = ap.parse_args()
    for p in (getattr(a, "path", None), getattr(a, "hands", None), getattr(a, "mtt", None)):
        if p is not None and not p.exists():
            ap.error(f"경로 없음: {p}")

    if a.cmd in {"hands", "replay"}:
        ev_ranges = None
        if a.oop_range or a.ip_range:
            if not (a.oop_range and a.ip_range):
                ap.error("EV 채점: --oop-range와 --ip-range를 함께 지정해야 함")
            if not ev_engine.available():
                ap.error("EV 채점 엔진 없음: cargo build --release --manifest-path ev_rust/Cargo.toml")
            # ponytail: 레인지는 OOP/IP 고정, 프리플랍·플랍 액션으로 좁히지 않음 — 결과는 거친 근사
            ev_ranges = tuple(load_range_csv(r) if Path(r).is_file() else r for r in (a.oop_range, a.ip_range))
        if a.cmd == "hands":
            report_hands(a.path, a.hero, a.samples, ev_ranges)
        else:
            from hand_review.replay import write_report

            try:
                report = write_report(a.path, a.output, ev_ranges)
            except (OSError, ValueError) as e:
                ap.error(str(e))
            print(f"복기 {len(report['hands'])}핸드 · 중복 {report['duplicates']} · 건너뜀 {len(report['errors'])}")
            print(f"로컬 브라우저에서 열기: {a.output.resolve().as_uri()}")
    elif a.cmd == "icm":
        total = sum(a.stacks)
        for n, (s, e) in enumerate(zip(a.stacks, icm(a.stacks, a.payouts), strict=True), 1):
            print(f"p{n}: 칩 {s:>9.0f} ({100 * s / total:4.1f}%)  ICM ${e:8.2f} ({100 * e / sum(a.payouts):4.1f}%)")
    elif a.cmd == "mtt":
        report_mtt(a.path)
    else:
        if bool(a.stacks) != bool(a.payouts):
            ap.error("tui: --stacks와 --payouts는 함께 지정해야 함")
        if not (a.hands or a.mtt or a.stacks):
            ap.error("tui: --hands, --mtt, --stacks 중 하나 이상 필요")
        run_tui(a.hands, a.hero, a.samples, a.mtt, a.stacks, a.payouts)


if __name__ == "__main__":
    main()
