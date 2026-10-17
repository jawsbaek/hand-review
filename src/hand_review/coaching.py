"""Bounded, reproducible action EVs against explicit response/range assumptions.

This is NOT an equilibrium solver. It simulates the rest of the current betting
round (at most one opponent counter-raise), then checks down sampled runouts.
Unknown folded cards are marginalized without modelling their range (no bunching
inference). Sampling error and sensitivity to opponent assumptions are separate.
No outcome, future board, revealed opponent cards, or recorded hero choice enters
the recommendation seed, ranges or candidate selection.
"""

import bisect
import functools
import hashlib
import itertools
import json
import math
import random
import re

from hand_review.pokerist import canonical_card

VERSION = "response-checkdown-v1"
RANKS, SUITS = "23456789TJQKA", "hdcs"
POSITIONS = {p: i for i, p in enumerate(("SB", "BB", "UTG", "UTG+1", "UTG+2", "MP", "LJ", "HJ", "CO", "BTN"))}
FRACTIONS = (0.25, 0.5, 0.75, 1.0, 1.5)
SCENARIOS = (
    ("baseline", "기본 응답 가정", 0.0),
    ("overfold", "폴드 확률 +15%p", 0.15),
    ("sticky", "폴드 확률 −15%p", -0.15),
)


def card_id(card):
    return 4 * RANKS.index(card[0]) + SUITS.index(card[1])


@functools.lru_cache(maxsize=65536)
def rank7(cards):
    """Comparable exact standard high-poker rank for five to seven cards."""
    counts, suits = [0] * 15, [[] for _ in range(4)]
    for card in cards:
        rank, suit = card // 4 + 2, card % 4
        counts[rank] += 1
        suits[suit].append(rank)

    def straight(ranks):
        bits = sum(1 << r for r in set(ranks))
        for high in range(14, 5 - 1, -1):
            mask = 31 << (high - 4)
            if bits & mask == mask:
                return high
        return 5 if bits & 16444 == 16444 else 0  # A,2,3,4,5

    groups = sorted(((n, r) for r, n in enumerate(counts) if n), reverse=True)
    flush = next((sorted(s, reverse=True) for s in suits if len(s) >= 5), [])
    sf = straight(flush) if flush else 0
    if sf:
        result = (8, sf)
    elif groups[0][0] == 4:
        q = groups[0][1]
        result = (7, q, max(r for _, r in groups if r != q))
    elif groups[0][0] == 3 and groups[1][0] >= 2:
        result = (6, groups[0][1], groups[1][1])
    elif flush:
        result = (5, *flush[:5])
    elif high := straight(r for _, r in groups):
        result = (4, high)
    elif groups[0][0] == 3:
        result = (3, groups[0][1], *sorted((r for _, r in groups[1:]), reverse=True)[:2])
    elif groups[0][0] == groups[1][0] == 2:
        pair = sorted((r for n, r in groups if n == 2), reverse=True)[:2]
        result = (2, *pair, max(r for _, r in groups if r not in pair))
    elif groups[0][0] == 2:
        result = (1, groups[0][1], *sorted((r for _, r in groups[1:]), reverse=True)[:3])
    else:
        result = (0, *sorted((r for _, r in groups), reverse=True)[:5])
    return (*result, *([0] * (6 - len(result))))


def hand_class(a, b):
    hi, lo = sorted((a // 4, b // 4), reverse=True)
    return RANKS[hi] + RANKS[lo] + ("" if hi == lo else "s" if a % 4 == b % 4 else "o")


def _score(name):
    hi, lo = (RANKS.index(x) + 2 for x in name[:2])
    return hi + lo * 0.6 + (12 if hi == lo else 2 if name.endswith("s") else 0) - max(0, hi - lo - 1) * 0.6


CLASSES = sorted(
    {hand_class(a, b) for a, b in itertools.combinations(range(52), 2)},
    key=lambda name: (_score(name), name),
    reverse=True,
)


@functools.lru_cache(maxsize=512)
def parse_range(text):
    """Explicit classes, exact combos, '+', and weights. Reject, never repair, bad input."""
    if not isinstance(text, str) or not text.strip() or len(text) > 16000:
        raise ValueError("레인지는 1~16000자의 핸드 문자열이어야 합니다.")
    weights = {}
    if text.strip().lower() in {"random", "100%"}:
        return tuple((a, b, 1.0) for a, b in itertools.combinations(range(52), 2))
    for token in text.replace(" ", "").split(","):
        name, _, weight = token.partition(":")
        try:
            w = float(weight) if weight else 1.0
        except ValueError as error:
            raise ValueError("레인지 가중치를 확인하세요.") from error
        if not math.isfinite(w) or not 0 <= w <= 1:
            raise ValueError("레인지 가중치는 0~1이어야 합니다.")
        exact = re.fullmatch(r"([2-9TJQKA][hdcs])([2-9TJQKA][hdcs])", name)
        if exact:
            a, b = sorted(card_id(c) for c in exact.groups())
            if a == b:
                raise ValueError("같은 카드 두 장을 레인지에 넣을 수 없습니다.")
            weights[a, b] = w
            continue
        if not re.fullmatch(r"[2-9TJQKA]{2}[so]?\+?", name):
            raise ValueError("레인지 형식: AA,TT+,AKs,AJo:0.5,AhKd 또는 random")
        plus, base = name.endswith("+"), name.removesuffix("+")
        hi, lo = (RANKS.index(c) for c in base[:2])
        if hi < lo or (hi == lo and len(base) != 2):
            raise ValueError("레인지의 높은 랭크를 먼저 적으세요.")
        allowed = set()
        for h in CLASSES:
            x, y = (RANKS.index(c) for c in h[:2])
            suit = len(base) == 2 or h.endswith(base[2:])
            match = x == hi and y == lo
            if plus:
                match = x == y >= hi if hi == lo else x == hi and lo <= y < hi
            if suit and match:
                allowed.add(h)
        for a, b in itertools.combinations(range(52), 2):
            if hand_class(a, b) in allowed:
                weights[a, b] = w
    result = tuple((a, b, w) for (a, b), w in sorted(weights.items()) if w > 0)
    if not result:
        raise ValueError("레인지에 양수 가중치의 조합이 없습니다.")
    return result


def default_ranges(context):
    """Versioned modelling priors, not professional or solved preflop charts."""
    result = {}
    before = [a for a in context["history"] if a["stage"] == "Preflop"]
    for p in context["players"]:
        if p["folded"] or p["departed"] and not p["all_in"]:
            continue
        text = "random"
        if context["board"]:
            actions = [a["name"] for a in before if a["seat"] == p["seat"]]
            width = {
                "UTG": 0.20,
                "UTG+1": 0.22,
                "UTG+2": 0.24,
                "MP": 0.25,
                "LJ": 0.25,
                "HJ": 0.30,
                "CO": 0.35,
                "BTN": 0.45,
                "SB": 0.40,
                "BB": 0.65,
            }.get(p["position"], 0.35)
            width *= 0.7 if "RAISE" in actions or "BET" in actions else 1
            if "CALL" not in actions and "RAISE" not in actions and "BET" not in actions:
                width = 1.0
            selected, mass = [], 0
            for name in CLASSES:
                selected.append(name)
                mass += 6 if len(name) == 2 else 4 if name.endswith("s") else 12
                if mass >= 1326 * width:
                    break
            text = ",".join(selected)
        if p["seat"] == context["hero_seat"]:
            combo = "".join(map(canonical_card, context["cards"]))
            own = sorted(card_id(canonical_card(c)) for c in context["cards"])
            if not any((a, b) == tuple(own) for a, b, _ in parse_range(text)):
                text += "," + combo
        result[str(p["seat"])] = text
    return result


@functools.lru_cache(maxsize=32768)
def policy_equity(own, board, opponent_range="random"):
    """Small deterministic HU equity estimate used by the response policy.

    This policy approximation is not the rollout payoff or an opponent read.
    Policy RNG never shares the sampled world's unrevealed cards.
    """
    if not board and opponent_range == "random":
        candidates = parse_range(hand_class(*own))
        own = candidates[0][:2]
    rng = random.Random(str((own, board, opponent_range)))
    available = [c for c in range(52) if c not in own + board]
    combos, cumulative, mass = [], [], 0.0
    for a, b, weight in parse_range(opponent_range):
        if a not in own + board and b not in own + board:
            combos.append((a, b))
            mass += weight
            cumulative.append(mass)
    if not mass:
        return 0.5  # A policy off its assumed range remains explicitly approximate.
    value = 0.0
    for _ in range(32):
        other = combos[bisect.bisect_left(cumulative, rng.random() * mass)]
        runout = board + tuple(rng.sample([c for c in available if c not in other], 5 - len(board)))
        a, b = rank7(tuple(sorted(own + runout))), rank7(tuple(sorted(other + runout)))
        value += (a > b) + 0.5 * (a == b)
    return value / 32


def _distribution(context, player, text, dead):
    combos, cumulative, mass = [], [], 0.0
    current = [a for a in context["history"] if a["stage"] == context["stage"] and a["seat"] == player["seat"]]
    for a, b, weight in parse_range(text):
        if a in dead or b in dead:
            continue
        for action in current:
            name = action["name"]
            if name not in {"CALL", "BET", "RAISE", "CHECK"}:
                continue
            board = tuple(card_id(canonical_card(c)) for c in action["board"])
            eq = policy_equity((a, b), board)
            if name in {"BET", "RAISE"}:
                weight *= 0.03 + 0.97 / (1 + math.exp(-18 * (eq - 0.61)))
            elif name == "CALL":
                weight *= 0.1 + 0.9 / (1 + math.exp(-15 * (eq - 0.43)))
            else:
                weight *= 0.25 + 0.75 * (1 - eq)
        mass += weight
        combos.append((a, b))
        cumulative.append(mass)
    if not mass:
        raise ValueError("보드·내 카드와 충돌하지 않는 상대 조합이 없습니다.")
    return combos, cumulative


def action(kind, paid, bet, pot, bb):
    return {
        "kind": kind,
        "paid_bb": round(paid / bb, 4),
        "to_bb": round((bet + paid) / bb, 4),
        "pot_pct": round(100 * paid / pot, 1) if pot else None,
    }


def candidates(context, extra_fraction=None):
    hero = next(p for p in context["players"] if p["seat"] == context["hero_seat"])
    bb, pot = context["bb"], context["pot"]
    bet, stack, call = hero["bet"], hero["stack"], min(context["to_call"], hero["stack"])
    rows = (
        [action("FOLD", 0, bet, pot, bb), action("CALL", call, bet, pot, bb)]
        if call
        else [action("CHECK", 0, bet, pot, bb)]
    )
    opponents = [
        p
        for p in context["players"]
        if p["seat"] != hero["seat"] and not p["folded"] and not p["departed"] and p["stack"] > 0
    ]
    if not opponents or not context["raise_reopened"] or stack <= call:
        return rows
    maximum = max(p["bet"] + p["stack"] for p in opponents)
    high = bet + context["to_call"]
    minimum = max(bb, context["min_raise_to"] - bet)
    # A legal full raise can exceed the opponent's remaining matching stack.
    # Keep its announced amount; settlement returns any uncalled excess.
    cap = min(stack, max(minimum, maximum - bet))
    kind = "RAISE" if high else "BET"
    fractions = (*FRACTIONS, *([extra_fraction] if extra_fraction else []))
    amounts = [minimum, cap]
    amounts.extend((high - bet + f * (pot + call)) if high else f * pot for f in fractions)
    for paid in sorted({round(min(cap, x), 8) for x in amounts if x > call}):
        if paid + 1e-8 < minimum and paid + 1e-8 < stack:
            continue  # Only a short all-in may be smaller than a full raise.
        rows.append(action(kind, paid, bet, pot, bb))
    return rows


def _settle(players, ranks, hero, spent):
    """Layered pots include dead contributions, ties, short calls and uncalled returns."""
    levels, previous, winnings = sorted({p["total"] for p in players if p["total"] > 0}), 0.0, 0.0
    for level in levels:
        contributors = [p for p in players if p["total"] >= level - 1e-8]
        value = (level - previous) * len(contributors)
        eligible = [p for p in contributors if not p["folded"] and (not p["departed"] or p["all_in"])]
        if len(contributors) == 1:
            winners = contributors  # Uncalled excess is returned, not won from an opponent.
        elif eligible:
            best = max(ranks[p["seat"]] for p in eligible)
            winners = [p for p in eligible if ranks[p["seat"]] == best]
        else:
            winners = []
        if any(p["seat"] == hero for p in winners):
            winnings += value / len(winners)
        previous = level
    return winnings - spent


def _rollout(context, chosen, holes, ranks, draws, shift):
    bb, hero = context["bb"], context["hero_seat"]
    if chosen["kind"] == "FOLD":
        return 0.0
    players = [{**p} for p in context["players"]]
    by_seat = {p["seat"]: p for p in players}
    board = tuple(card_id(canonical_card(c)) for c in context["board"])
    live = [p for p in players if not p["folded"] and (not p["departed"] or p["all_in"])]
    order = sorted((p["seat"] for p in live), key=lambda s: (POSITIONS.get(by_seat[s]["position"], 50), s))
    h = by_seat[hero]
    spent = chosen["paid_bb"] * bb

    def pay(p, amount):
        amount = min(p["stack"], max(0.0, amount))
        p["stack"] -= amount
        p["bet"] += amount
        p["total"] += amount
        p["all_in"] = p["stack"] < 1e-8
        return amount

    pay(h, spent)
    high = max(p["bet"] for p in players)
    previous_high = h["bet"] - spent + context["to_call"]
    aggressor = next(
        (
            a["seat"]
            for a in reversed(context["history"])
            if a["stage"] == context["stage"] and a["name"] in {"BET", "RAISE"}
        ),
        None,
    )
    if chosen["kind"] in {"BET", "RAISE"}:
        aggressor = hero
    pending = {
        p["seat"]
        for p in live
        if p["seat"] != hero
        and p["stack"] > 0
        and (chosen["kind"] in {"BET", "RAISE"} or p["bet"] < high - 1e-8 or p["seat"] not in context["acted"])
    }
    cursor, escalations, turns = order.index(hero), 0, 0
    last_raise = max(bb, context["min_raise_to"] - (h["bet"] - spent + context["to_call"]))
    last_raise = max(last_raise, high - previous_high)
    while pending and turns < 4 * len(order):
        cursor = (cursor + 1) % len(order)
        seat = order[cursor]
        if seat not in pending:
            continue
        pending.remove(seat)
        p = by_seat[seat]
        if p["folded"] or p["stack"] <= 0:
            continue
        turns += 1
        remaining = [x for x in live if not x["folded"]]
        if len(remaining) == 1:
            pending.clear()
            break
        pot = sum(x["total"] for x in players)
        cost = min(p["stack"], max(0.0, high - p["bet"]))
        target = (
            aggressor
            if aggressor is not None and aggressor != seat
            else next(x["seat"] for x in remaining if x["seat"] != seat)
        )
        equity = policy_equity(holes[seat], board, context["policy_ranges"][str(target)]) ** (len(remaining) - 1)
        odds = cost / (pot + cost) if cost else 0.0
        u = draws[seat][min(escalations, 2)]
        if cost:
            fold = 1 / (1 + math.exp(max(-50, min(50, 20 * (equity - odds - 0.025)))))
            fold = min(1.0, max(0.0, fold + (shift if seat != hero else 0)))
            if u < fold:
                p["folded"] = True
                continue
        able = any(x["seat"] != seat and not x["folded"] and x["stack"] > 0 for x in live)
        aggressive = seat != hero and able and escalations < 1 and equity > 0.68
        aggressive &= u > 0.75 if cost else u > 0.5
        minimum = high + last_raise - p["bet"]
        if aggressive and p["stack"] > max(cost, minimum):
            old = high
            pay(p, max(minimum, cost + 0.75 * (pot + cost)))
            high = p["bet"]
            last_raise = max(last_raise, high - old)
            escalations += 1
            aggressor = seat
            pending = {x["seat"] for x in live if x["seat"] != seat and not x["folded"] and x["stack"] > 0}
        else:
            pay(p, cost)
        if seat == hero:
            spent = h["total"] - next(x["total"] for x in context["players"] if x["seat"] == hero)
    if pending:
        raise ValueError("응답 모델의 베팅 라운드가 종료되지 않았습니다.")
    return _settle(players, ranks, hero, spent) / bb


def estimate(context, overrides=None, samples=256):
    """Return recommendation + explicit scenarios. Never call a scenario a measured read."""
    if not isinstance(samples, int) or not 16 <= samples <= 4096:
        raise ValueError("모델 샘플 수는 16~4096이어야 합니다.")
    if not context["trustworthy"] or not context["bb"] or len(context["cards"]) != 2:
        return {"status": "unavailable", "note": "카드·블라인드·베팅 기록이 불완전하여 추천을 보류합니다."}
    active = [p for p in context["players"] if not p["folded"] and (not p["departed"] or p["all_in"])]
    if len(active) < 2 or any(p["stack"] is None for p in active):
        return {"status": "unavailable", "note": "참가자 스택을 확인할 수 없어 추천을 보류합니다."}
    ranges = default_ranges(context)
    if overrides:
        if set(overrides) - set(ranges):
            raise ValueError("참가 중인 좌석의 레인지만 수정할 수 있습니다.")
        ranges.update(overrides)
    for text in ranges.values():
        parse_range(text)
    hero = context["hero_seat"]
    own = tuple(card_id(canonical_card(c)) for c in context["cards"])
    if not any({a, b} == set(own) for a, b, _ in parse_range(ranges[str(hero)])):
        raise ValueError("내 레인지에 현재 내 카드 조합을 포함하세요.")
    board = tuple(card_id(canonical_card(c)) for c in context["board"])
    dead = set(own + board)
    opponents = [p for p in active if p["seat"] != hero]
    distributions = {
        p["seat"]: _distribution({**context, "stage": context.get("stage", "Preflop")}, p, ranges[str(p["seat"])], dead)
        for p in opponents
    }
    seed_data = {
        "version": VERSION,
        "cards": own,
        "board": board,
        "ranges": ranges,
        "players": [
            {k: p[k] for k in ("seat", "position", "stack", "bet", "total", "folded", "departed", "all_in")}
            for p in context["players"]
        ],
        "history": context["history"],
        "samples": samples,
    }
    # History contains action observations but no identities, results or future cards.
    rng = random.Random(hashlib.sha256(json.dumps(seed_data, sort_keys=True).encode()).digest())
    worlds = []
    for _ in range(samples):
        for _attempt in range(3000):
            holes, used = {hero: own}, set(dead)
            for p in opponents:
                choices, cumulative = distributions[p["seat"]]
                combo = choices[bisect.bisect_left(cumulative, rng.random() * cumulative[-1])]
                if any(c in used for c in combo):
                    break
                holes[p["seat"]] = combo
                used.update(combo)
            else:
                break
        else:
            raise ValueError("여러 상대 레인지의 카드 충돌이 많습니다. 레인지를 넓혀 확인하세요.")
        runout = board + tuple(rng.sample([c for c in range(52) if c not in used], 5 - len(board)))
        ranks = {seat: rank7(tuple(sorted(cards + runout))) for seat, cards in holes.items()}
        draws = {p["seat"]: (rng.random(), rng.random(), rng.random()) for p in active}
        worlds.append((holes, ranks, draws))
    context = {**context, "policy_ranges": ranges}
    rows = candidates(context)

    def evaluate(options, shift):
        result = []
        for option in options:
            values = [_rollout(context, option, *w, shift) for w in worlds]
            mean = sum(values) / samples
            variance = sum((x - mean) ** 2 for x in values) / max(1, samples - 1)
            result.append(
                {**option, "ev_bb": round(mean, 4), "se_bb": round(math.sqrt(variance / samples), 4), "frequency": None}
            )
        return result

    first = evaluate(rows, 0)
    winner = max(first, key=lambda a: a["ev_bb"])
    if winner["kind"] in {"BET", "RAISE"}:
        # One bounded refinement, independent of the player's recorded choice.
        f = winner["pot_pct"] / 100
        for refined in (max(0.125, f - 0.125), f + 0.125):
            for option in candidates(context, refined):
                if option not in rows:
                    rows.append(option)
    scenarios = []
    for ident, title, shift in SCENARIOS:
        estimates = evaluate(rows, shift)
        best = max(estimates, key=lambda a: a["ev_bb"])
        close = [a for a in estimates if best["ev_bb"] - a["ev_bb"] <= 2 * math.hypot(best["se_bb"], a["se_bb"])]
        scenarios.append(
            {
                "id": ident,
                "title": title,
                "fold_shift": shift,
                "recommendation": best,
                "actions": estimates,
                "indistinguishable": len(close),
            }
        )
    stable = len({(s["recommendation"]["kind"], s["recommendation"]["to_bb"]) for s in scenarios}) == 1
    # With sparse reads, favor a candidate whose lower estimate survives every
    # tested response scenario. This is robustness to THESE assumptions, not a
    # worst-case guarantee against arbitrary opponents.
    conservative = max(
        range(len(rows)),
        key=lambda i: (
            min(s["actions"][i]["ev_bb"] - 2 * s["actions"][i]["se_bb"] for s in scenarios),
            -rows[i]["paid_bb"],
        ),
    )
    return {
        "status": "ready",
        "method": "model",
        "version": VERSION,
        "samples": samples,
        "recommendation": scenarios[0]["actions"][conservative],
        "actions": scenarios[0]["actions"],
        "selection": "세 응답 가정에서 EV−2표준오차의 최솟값을 비교한 보수적 모델 추천",
        "scenarios": scenarios,
        "stable": stable,
        "ranges": ranges,
        "assumptions": [
            "기본 레인지는 검증된 프로 차트가 아닌 수정 가능한 모델 사전 가정입니다.",
            "현재 스트리트의 응답과 상대 재공격 1회까지 계산한 뒤 남은 보드는 체크다운합니다.",
            "응답 정책은 직전 공격자 레인지 대비 근사 승률과 팟 오즈를 사용하며, 다인 승률은 독립 근사합니다.",
            "±15%p는 관측된 성향이 아닌 가정 실험입니다. 개인별 자동 보정은 적용하지 않습니다.",
            "EV 오차는 샘플링 오차이며 레인지·응답 모델이 틀리는 위험은 포함하지 않습니다.",
            "레이크 0 가정. 폴드한 사람의 카드 분포와 이후 스트리트 베팅은 모델링하지 않습니다.",
        ],
    }
