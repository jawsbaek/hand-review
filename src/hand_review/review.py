"""Decision reviews use only pre-action information, never the recorded result."""

import functools
import itertools
import math
import subprocess

from pokerkit import StandardHighHand

from hand_review import ev_engine
from hand_review.pokerist import canonical_card

RANKS = "23456789TJQKA"
HAND_NAMES = {
    "HIGH_CARD": "하이 카드",
    "ONE_PAIR": "원페어",
    "TWO_PAIR": "투페어",
    "THREE_OF_A_KIND": "트립스",
    "STRAIGHT": "스트레이트",
    "FLUSH": "플러시",
    "FULL_HOUSE": "풀하우스",
    "FOUR_OF_A_KIND": "포카드",
    "STRAIGHT_FLUSH": "스트레이트 플러시",
}


@functools.lru_cache(maxsize=2048)
def made_hand(cards, board):
    """Find the current nuts by enumerating possible opponent hole cards.

    This is hand strength on the visible board, not showdown equity or EV.
    Suits are canonicalized consistently; the displayed suit-4 label stays intact.
    """
    if len(board) < 3:
        return None, False
    own = tuple(map(canonical_card, cards))
    visible = tuple(map(canonical_card, board))
    if len(set(own + visible)) != len(own + visible):
        return None, False
    hand = StandardHighHand.from_game("".join(own), "".join(visible))
    deck = [r + s for r in RANKS for s in "hdcs" if r + s not in own + visible]
    any_worse, nuts = False, True
    for combo in itertools.combinations(deck, 2):
        opponent = StandardHighHand.from_game("".join(combo), "".join(visible))
        if opponent > hand:
            nuts = False
            break
        any_worse |= opponent < hand
    return HAND_NAMES.get(hand.entry.label.name, str(hand.entry.label)), nuts and any_worse


def _review(grade, title, reason, recommendation, basis="heuristic", **extra):
    return {"grade": grade, "title": title, "reason": reason, "recommendation": recommendation, "basis": basis, **extra}


def heuristic_review(context, action):
    if not context["trustworthy"]:
        return _review(
            "unscored",
            "기록 확인이 먼저입니다",
            "시작·카드·베팅 기록이 불완전합니다.",
            "핸드의 기록 경고를 확인하세요.",
            "unavailable",
        )
    board, cards = context["board"], context["cards"]
    ranks = sorted((RANKS.index(canonical_card(c)[0]) + 2 for c in cards), reverse=True)
    hi, lo = ranks
    pair = hi == lo
    suited = canonical_card(cards[0])[1] == canonical_card(cards[1])[1]
    name, bb = action["name"], context["bb"]
    if not bb:
        return _review(
            "unscored", "BB 미확인", "금액을 BB로 비교할 수 없습니다.", "블라인드 기록을 확인하세요.", "unavailable"
        )
    if not board:
        premium = (pair and hi >= 12) or (hi == 14 and lo == 13)
        weak = not pair and ((hi <= 11 and lo <= 5 and hi - lo >= 4) or (not suited and hi <= 13 and lo <= 7))
        early = context["position"] in {"UTG", "UTG+1", "MP", "LJ"}
        if name == "FOLD" and pair and hi >= 13:
            return _review(
                "blunder",
                "프리미엄 페어 폴드",
                "AA·KK의 프리플랍 폴드는 우선 확인할 장면입니다. 특수 상황은 반영하지 않았습니다.",
                "콜·레이즈와 비교해 보세요.",
            )
        if name == "FOLD" and weak and context["to_call"] >= bb:
            return _review(
                "best",
                "약한 핸드의 추가 투자 절제",
                "연결성이 낮은 핸드를 폴드해 추가 칩 투입을 피했습니다. 기본 전략에 따른 후보입니다.",
                "상대 오픈 크기와 포지션을 함께 확인하세요.",
            )
        if name in {"BET", "RAISE"} and premium and action["paid"] <= 12 * bb and context["raises"] <= 1:
            return _review(
                "best",
                "프리미엄 핸드로 주도권 확보",
                "강한 시작 핸드로 공격했습니다. 정확한 베팅 크기의 최적성은 계산하지 않았습니다.",
                "상대 레인지에 따라 레이즈 크기를 검토하세요.",
            )
        if (
            weak
            and name in {"CALL", "BET", "RAISE"}
            and (context["to_call"] >= 4 * bb or (early and action["paid"] >= bb))
        ):
            return _review(
                "blunder",
                "약한 시작 핸드에 추가 투자",
                "불리한 포지션 또는 큰 콜 비용에 비해 시작 핸드의 연결성이 낮습니다. EV 계산은 없는 검토 후보입니다.",
                "폴드를 우선 비교하세요.",
            )
        if name in {"BET", "RAISE"} and action["paid"] > 30 * bb and not premium and context["active"] >= 3:
            return _review(
                "blunder",
                "멀티웨이에서 큰 프리플랍 투자",
                "프리미엄이 아닌 핸드로 30BB 넘게 투자했습니다. 상대 레인지와 유효 스택을 먼저 확인할 장면입니다.",
                "작은 레이즈·콜·폴드와 비교하세요.",
            )
    else:
        strength, nuts = made_hand(tuple(cards), tuple(board))
        if nuts and name in {"BET", "RAISE"}:
            return _review(
                "best",
                "현재 넛 핸드로 밸류 추구",
                f"공개된 보드에서 {strength}보다 강한 상대 조합이 없습니다. "
                "공격 방향을 좋게 볼 수 있지만 사이즈의 최적성은 미확인입니다.",
                "더 작은 크기로 받을 수 있는 콜도 비교하세요.",
                strength=strength,
            )
        if nuts and name == "FOLD":
            return _review(
                "blunder",
                "현재 넛 핸드를 폴드",
                f"현재 보드에서 {strength}가 최상위입니다. 향후 카드의 위험과 유효 스택을 함께 검토해야 합니다.",
                "콜·레이즈를 비교하세요.",
                strength=strength,
            )
        if nuts and name == "CHECK" and len(board) == 5:
            return _review(
                "review",
                "리버 밸류 벳 검토",
                "현재 넛 핸드로 체크했습니다. 상대가 뒤에서 베팅할 수 있어 체크만으로 실수라고 확정할 수는 없습니다.",
                "상대가 콜할 레인지와 체크 유도를 비교하세요.",
                strength=strength,
            )
    return _review(
        "unscored",
        "추가 분석이 필요한 결정",
        "단순 규칙만으로 최선의 액션을 구분하기 어렵습니다. 승패는 평가에 사용하지 않았습니다.",
        "레인지와 베팅 의도를 기록해 복기하세요.",
        "unavailable",
    )


def solver_review(context, action, hero_seat, ranges):
    """Score supported HU turn/river spots through v0.3.0's real EV engine."""
    street, bb = context["street"], context["bb"]
    if not context["trustworthy"] or len(context["board"]) not in (4, 5) or not street or not bb:
        return None, "솔버 범위: 기록이 완전한 헤즈업 턴·리버만 지원합니다."
    if context["active"] != 2 or street["oop"] is None or street["pot_bb"] <= 0 or street["eff_bb"] <= 0:
        return None, "이 결정은 지원하는 헤즈업 스택 상태가 아닙니다."
    chosen = action.get("solver_name", action["name"])
    sizes = {33, 75} | {int(n.split()[1]) for n in [*street["path"], chosen] if n.startswith("BET ")}
    try:
        r = ev_engine.solve_node(
            list(map(canonical_card, street["board"])),
            *ranges,
            street["pot_bb"],
            street["eff_bb"],
            "oop" if hero_seat == street["oop"] else "ip",
            "".join(map(canonical_card, context["cards"])),
            path=street["path"],
            bet_sizes=",".join(f"{s}%" for s in sorted(sizes)),
            raise_sizes="3x",
            max_mem_gib=1.0,
            timeout_seconds=45,
        )
        mapped = ev_engine.nearest_action(chosen, r["actions"])
        evs, exploitability = r["ev"], r["exploitability"]
        if mapped is None or not evs or not all(math.isfinite(v) for v in evs.values()):
            return None, "실제 액션을 솔버 트리에 대응할 수 없었습니다."
        if not math.isfinite(exploitability) or exploitability > street["pot_bb"] * 0.01:
            return None, "솔버가 수렴 기준(시작 팟의 1%)을 충족하지 못해 등급을 보류했습니다."
        loss = max(0.0, max(evs.values()) - evs[mapped])
        grade = "blunder" if loss >= 2 else "best" if loss <= max(0.1, 2 * exploitability) else "review"
        best = max(evs, key=evs.get)
        return _review(
            grade,
            "레인지 가정 아래 EV 비교",
            f"최선 {best} 대비 실제 {mapped}의 EV 차이는 {loss:.2f}BB입니다.",
            "고정 OOP/IP 레인지와 가장 가까운 트리 사이즈를 사용한 근사입니다. 레인지를 바꿔 비교하세요.",
            "solver",
            loss_bb=round(loss, 4),
            evs=evs,
            mapped_action=mapped,
            actual_action=chosen,
            approximate=mapped != chosen,
            exploitability_bb=exploitability,
        ), None
    except (RuntimeError, FileNotFoundError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError) as e:
        return None, "솔버 시간 제한 초과" if isinstance(
            e, subprocess.TimeoutExpired
        ) else "솔버 계산 불가: 레인지·트리·엔진 상태를 확인하세요."


def review_hand(hand, ranges=None):
    for d in hand["decisions"]:
        context, action = d["context"], d["action"]
        review = heuristic_review(context, action)
        if ranges:
            scored, note = solver_review(context, action, hand["hero"]["seat"], ranges)
            if scored:
                review = scored
            else:
                review["solver_note"] = note
        d["review"] = review
        pot = context["eligible_pot"]
        call = min(context["to_call"], context["stack"]) if context["stack"] is not None else context["to_call"]
        d["spot"] = {
            "to_call": call,
            "stack": context["stack"],
            "pot": pot,
            "active": context["active"],
            "can_raise": context["stack"] is not None
            and context["stack"] > context["to_call"]
            and context.get("raise_reopened", True)
            and (
                not context.get("players")
                or any(p["seat"] != context["hero_seat"] and _live_stack(p) for p in context["players"])
            ),
            "pot_odds": call / (pot + call) if pot and call else None,
        }
        del d["context"]  # The browser needs observations and reviews, not solver inputs per snapshot.
    return hand


def _live_stack(player):
    return not player["folded"] and not player["departed"] and player["stack"] is not None and player["stack"] > 0
