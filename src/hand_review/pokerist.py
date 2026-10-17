"""Pokerist's observation export -> replay snapshots, without inventing payouts.

AMOUNT is a payment only on committed money events (STATUS=2). Other AMOUNTs
can be stack snapshots or stale bets. COLLECT_POT is never a payout record.
"""

import copy
import json
import math
from pathlib import Path

STREETS = {"Preflop": 0, "Flop": 3, "Turn": 4, "River": 5}
DEALS = {"GS_FLOP": "Flop", "GS_TURN": "Turn", "GS_RIVER": "River"}
MONEY = {"GS_SMALL_BLIND", "GS_BIG_BLIND", "GS_ANTE", "GS_CALL", "GS_BET", "GS_RAISE"}
CHOICES = {"GS_CALL", "GS_BET", "GS_RAISE", "GS_CHECK", "GS_FOLD"}
LABELS = {
    "GS_SMALL_BLIND": "SB",
    "GS_BIG_BLIND": "BB",
    "GS_ANTE": "포스트",
    "GS_CALL": "콜",
    "GS_BET": "벳",
    "GS_RAISE": "레이즈",
    "GS_CHECK": "체크",
    "GS_FOLD": "폴드",
}


def numeric(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (TypeError, ValueError):
        return None


def canonical_card(label):
    """Suit 4 is assigned an internal solver token, not a claimed display glyph."""
    if not isinstance(label, str):
        raise ValueError("카드 형식 오류")
    label = label.replace("10", "T")
    rank = label[:1]
    suit = {"♥": "h", "♦": "d", "♣": "c", "/s4": "s", "♠": "s"}.get(label[1:])
    if rank not in "23456789TJQKA" or not suit:
        raise ValueError("지원하지 않는 카드 표기")
    return rank + suit


def _seat(value):
    n = numeric(value)
    if n is None or n != int(n) or not 0 <= n <= 100:
        raise ValueError("좌석 형식 오류")
    return int(n)


def _eligible(player):
    """A departed all-in player still contests pots; a departed live stack does not."""
    return not player["folded"] and (not player["departed"] or player["all_in"])


def _validate(raw):
    if not isinstance(raw, dict) or raw.get("kind") != "pokerist-hand":
        raise ValueError("pokerist-hand 레코드가 아님")
    hero = raw.get("hero")
    if not isinstance(hero, dict):
        raise ValueError("hero 정보 없음")
    _seat(hero.get("seat"))
    cards, board, actions = hero.get("cards"), raw.get("board"), raw.get("actions")
    if not isinstance(cards, list) or len(cards) != 2 or not isinstance(board, list) or len(board) > 5:
        raise ValueError("홀 카드 또는 보드 형식 오류")
    for c in cards + board:
        canonical_card(c)
    if not isinstance(actions, list) or not actions:
        raise ValueError("액션 기록 없음")
    for a in actions:
        if not isinstance(a, dict) or not isinstance(a.get("event"), str) or not isinstance(a.get("attrs"), dict):
            raise ValueError("액션 형식 오류")
        if a.get("who") is not None:
            _seat(a["who"])
        if a.get("stage") not in STREETS:
            raise ValueError("지원하지 않는 스트리트")
        if a.get("attrs", {}).get("STATUS") == "2" and a.get("event") in MONEY:
            if numeric(a["attrs"].get("AMOUNT")) is None:
                raise ValueError("확정 베팅의 AMOUNT 없음")
    for field in ("showdown", "revealed"):
        entries = raw.get(field, [])
        if not isinstance(entries, list):
            raise ValueError("공개 카드 형식 오류")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("cards"), list):
                raise ValueError("공개 카드 형식 오류")
            _seat(entry.get("place"))
            for card in entry["cards"]:
                if not isinstance(card, dict):
                    raise ValueError("공개 카드 형식 오류")
                canonical_card(card.get("label"))
    if raw.get("net") is not None:
        try:
            if not math.isfinite(float(raw["net"])):
                raise ValueError
        except (TypeError, ValueError) as e:
            raise ValueError("Net 형식 오류") from e


def load_pokerist(path):
    """Return valid, deduplicated records and explicit import diagnostics.

    Split only on LF: Python's splitlines() also splits valid U+0085 inside
    JSON strings (observed in mojibake nicknames in real exports).
    """
    path = Path(path)
    files = [path] if path.is_file() else sorted(path.rglob("*.jsonl"))
    records, errors, seen, duplicates = [], [], set(), 0
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8-sig").split("\n")
        except (OSError, UnicodeError):
            errors.append(f"{f.name}: UTF-8 파일을 읽을 수 없음")
            continue
        for line_no, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                _validate(raw)
            except (ValueError, TypeError, KeyError) as e:
                message = "JSON 형식 오류" if isinstance(e, json.JSONDecodeError) else str(e)
                errors.append(f"{f.name}:{line_no}: {message}")
                continue
            key = raw.get("_key") or json.dumps(raw, sort_keys=True, ensure_ascii=True)
            if str(key) in seen:
                duplicates += 1
            else:
                seen.add(str(key))
                records.append(raw)
    return records, errors, duplicates


def replay_hand(raw, number):
    """Build independent snapshots and pre-action contexts for hero reviews."""
    warnings, actions = [], raw["actions"]
    end_index = next((i for i, a in enumerate(actions) if a["event"] == "HAND_FINISHED"), None)
    finished = end_index is not None
    trailing = actions[end_index + 1 :] if finished else []
    next_hand_events = CHOICES | set(DEALS) | {"GS_OWN_CARDS", "GS_SMALL_BLIND", "GS_BIG_BLIND", "GS_ANTE"}
    boundary_bad = any(a["event"] in next_hand_events for a in trailing)
    if boundary_bad:
        warnings.append(
            "종료 뒤 다른 게임의 액션이 섞여 있어 첫 HAND_FINISHED까지만 재생합니다. 최종 보드·팟·Net은 보류합니다."
        )
    actions = actions[: end_index + 1] if finished else actions
    if not finished:
        warnings.append("종료 이벤트가 없는 미완료 핸드입니다. Net과 결과를 확정하지 않습니다.")
    hero = {key: copy.deepcopy(raw["hero"].get(key)) for key in ("seat", "nick", "cards", "position")}
    hero["seat"] = _seat(hero["seat"])
    hero_seats = {int(a["who"]) for a in actions if a.get("nick") == hero.get("nick") and a.get("who") is not None}
    if len(hero_seats) == 1 and hero["seat"] not in hero_seats:
        hero["seat"] = hero_seats.pop()
        warnings.append("내 좌석 메타데이터와 액션이 달라 액션의 닉네임으로 좌석을 복원했습니다. 포지션은 보류합니다.")
        boundary_bad = True
    if boundary_bad:
        hero["cards"] = []
        warnings.append("핸드 경계가 섞여 내 카드·포지션·보드의 최종 스냅샷을 표시하지 않습니다.")
    board = [] if boundary_bad else raw["board"]
    positions = raw.get("positions", {}) if not boundary_bad else {}
    if not isinstance(positions, dict):
        positions = {}
    players = {}
    for a in actions:
        if a.get("who") is None or a["event"] not in MONEY | CHOICES | {"GS_PLAYER_STAKE", "GS_OWN_CARDS"}:
            continue
        seat, attrs = int(a["who"]), a.get("attrs", {})
        if seat not in players:
            stack = numeric(attrs.get("D_AMOUNT"))
            if stack is not None and a["event"] in MONEY and attrs.get("STATUS") == "2":
                stack += float(attrs["AMOUNT"])
            players[seat] = {
                "seat": seat,
                "nick": str(a.get("nick") or f"좌석 {seat}"),
                "position": positions.get(str(seat)),
                "stack": stack,
                "bet": 0.0,
                "total": 0.0,
                "folded": False,
                "departed": False,
                "all_in": False,
                "cards": [],
            }
    players.setdefault(
        hero["seat"],
        {
            "seat": hero["seat"],
            "nick": str(hero.get("nick") or "Hero"),
            "position": None,
            "stack": None,
            "bet": 0.0,
            "total": 0.0,
            "folded": False,
            "departed": False,
            "all_in": False,
            "cards": [],
        },
    )
    players[hero["seat"]]["cards"] = list(hero["cards"])
    hero["position"] = players[hero["seat"]]["position"]
    bb = next(
        (
            numeric(a["attrs"].get("AMOUNT"))
            for a in actions
            if a["event"] == "GS_BIG_BLIND" and a["attrs"].get("STATUS") == "2"
        ),
        None,
    )
    bb = bb or next(
        (numeric(a["attrs"].get("BIG_BLIND")) for a in actions if numeric(a["attrs"].get("BIG_BLIND"))), None
    )
    forced = {a["event"] for a in actions if a["attrs"].get("STATUS") == "2"}
    complete_start = {"GS_SMALL_BLIND", "GS_BIG_BLIND"} <= forced
    if not complete_start:
        warnings.append("블라인드부터 기록되지 않아 팟·시작 스택의 일부가 미확인입니다. 자동 평가는 보류합니다.")
    if raw.get("integrity"):
        warnings.append("원본에 카드 무결성 경고가 있습니다. 자동 평가는 보류합니다.")
    if len(board) < max(STREETS[a["stage"]] for a in actions):
        warnings.append("스트리트에 필요한 보드 카드가 부족합니다. 자동 평가는 보류합니다.")
    if len(set(map(canonical_card, hero["cards"] + board))) != len(hero["cards"] + board):
        warnings.append("내 카드와 보드에 중복 카드가 있습니다. 자동 평가는 보류합니다.")
    trustworthy = (
        complete_start
        and not boundary_bad
        and not raw.get("integrity")
        and not any("중복 카드" in w or "보드 카드가 부족" in w for w in warnings)
    )
    stage, pot, frames, decisions, raises = "Preflop", 0.0, [], [], 0
    street_context, revealed = None, False

    def snapshot(label, action=None):
        frames.append(
            {
                "stage": stage,
                "board": list(board[: STREETS[stage]]),
                "pot": pot if complete_start else None,
                "label": label,
                "action": action,
                "players": copy.deepcopy(list(players.values())),
                "finished": False,
            }
        )

    def change_street(new):
        nonlocal stage, street_context
        if STREETS[new] <= STREETS[stage]:
            return
        stage = new
        for p in players.values():
            p["bet"] = 0.0
        active = [p for p in players.values() if _eligible(p)]
        street_context = None
        if len(active) == 2 and all(p["stack"] is not None and p["stack"] > 0 for p in active) and bb:
            street_context = {
                "board": list(board[: STREETS[stage]]),
                "pot_bb": pot / bb,
                "eff_bb": min(p["stack"] for p in active) / bb,
                "oop": None,
                "path": [],
            }
        snapshot(f"{new} 공개")

    snapshot("핸드 시작")
    for a in actions:
        event, attrs = a["event"], a.get("attrs", {})
        if event in DEALS:
            change_street(DEALS[event])
        if event == "GS_STANDUP_DESK" and a.get("who") is not None:
            player = players.get(int(a["who"]))
            if player is not None and not player["departed"]:
                change_street(a["stage"])
                player["departed"] = True
                if player["stack"] is None:
                    warnings.append("자리 이탈 시 남은 스택을 확인할 수 없어 자동 평가를 보류합니다.")
                    trustworthy = False
                label = "자리 이탈 · 올인 유지" if player["all_in"] else "자리 이탈"
                snapshot(
                    f"{player['nick']} · {label}",
                    {"seat": player["seat"], "name": "LEAVE", "label": label, "paid": 0.0, "to": player["bet"]},
                )
            continue
        if event not in MONEY | CHOICES or attrs.get("STATUS") != "2" or a.get("who") is None:
            continue
        change_street(a["stage"])
        p = players[int(a["who"])]
        paid = float(attrs["AMOUNT"]) if event in MONEY else 0.0
        to_call = max(0.0, max(x["bet"] for x in players.values()) - p["bet"])
        target = p["bet"] + paid
        if numeric(attrs.get("T_S_AMOUNT")) is not None and event in MONEY:
            if abs(target - float(attrs["T_S_AMOUNT"])) > 0.01:
                message = "스트리트 누적액과 지불액이 다릅니다. 자동 평가는 보류합니다."
                if message not in warnings:
                    warnings.append(message)
                trustworthy = False
            target = float(attrs["T_S_AMOUNT"])
        is_raise = event in {"GS_BET", "GS_RAISE"} and target > max(x["bet"] for x in players.values())
        raises_existing_bet = to_call > 0 or (stage == "Preflop" and max(x["bet"] for x in players.values()) > 0)
        name = "RAISE" if is_raise and raises_existing_bet else "BET" if is_raise else event.removeprefix("GS_")
        label = LABELS.get(f"GS_{name}", LABELS[event])
        action = {"seat": p["seat"], "name": name, "label": label, "paid": paid, "to": target}
        if event in CHOICES:
            if street_context and street_context["oop"] is None:
                street_context["oop"] = p["seat"]
            if p["seat"] == hero["seat"]:
                call = min(to_call, p["stack"]) if p["stack"] is not None else to_call
                eligible_pot = sum(min(x["total"], p["total"] + call) for x in players.values())
                decisions.append(
                    {
                        "frame": len(frames) - 1,
                        "action_frame": len(frames),
                        "stage": stage,
                        "action": action,
                        "context": {
                            "board": list(board[: STREETS[stage]]),
                            "cards": list(hero["cards"]),
                            "position": hero["position"],
                            "pot": pot if complete_start else None,
                            "eligible_pot": eligible_pot if complete_start else None,
                            "bb": bb,
                            "to_call": to_call,
                            "stack": p["stack"],
                            "raises": raises,
                            "active": sum(_eligible(x) for x in players.values()),
                            "trustworthy": trustworthy,
                            "street": copy.deepcopy(street_context),
                        },
                    }
                )
            if street_context:
                solver_name = name
                if name in {"BET", "RAISE"}:
                    if p["stack"] is not None and paid >= p["stack"]:
                        solver_name = "ALLIN"
                    elif pot:
                        solver_name = f"{name} {round(100 * target / pot)}"
                action["solver_name"] = solver_name
                street_context["path"].append(solver_name)
        if event in MONEY:
            pot += paid
            p["total"] += paid
            p["bet"] = target
            p["stack"] = max(0.0, p["stack"] - paid) if p["stack"] is not None else None
            if numeric(attrs.get("D_AMOUNT")) is not None:
                p["stack"] = float(attrs["D_AMOUNT"])
            p["all_in"] = p["stack"] == 0
        p["folded"] |= event == "GS_FOLD"
        raises += is_raise and stage == "Preflop"
        snapshot(f"{p['nick']} · {label}", action)

    if finished:
        # Exported showdown cards have no reliable per-card reveal timestamps.
        # Reveal only in the final frame; never feed them into review decisions.
        for entry in raw.get("showdown", []) + raw.get("revealed", []):
            place = _seat(entry["place"])
            if place not in players or boundary_bad:
                continue
            labels = [c.get("label") for c in entry.get("cards", []) if isinstance(c, dict)]
            if len(labels) == 2:
                players[place]["cards"] = labels
                revealed = True
        snapshot("기록 종료 · 공개 카드" if revealed else "기록 종료 · 상대 카드 미공개")
        frames[-1]["finished"] = True
        frames[-1]["recorded_pot"] = numeric(raw.get("pot")) if not boundary_bad else None
    if not trustworthy:
        for d in decisions:
            d["context"]["trustworthy"] = False
    result = {
        "id": str(raw.get("_key") or number),
        "number": number,
        "started_ts": raw.get("started_ts"),
        "table_id": raw.get("table_id"),
        "hero": hero,
        "bb": bb,
        "net": float(raw["net"]) if raw.get("net") is not None and finished and not boundary_bad else None,
        "warnings": warnings,
        "frames": frames,
        "decisions": decisions,
    }
    return result
