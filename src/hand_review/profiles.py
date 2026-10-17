"""Chronological, opportunity-based opponent evidence from stable capture IDs.

Only completed, trustworthy hands ending before the reviewed hand are eligible.
Unknown times/IDs and observations from the hand being reviewed never become a
personal read. Aggregate public behavior cannot identify combo-level policies.
"""

import copy
from collections import defaultdict


def _empty():
    return {"hands": 0, "decisions": 0, "facing_bet": 0, "folds": 0, "calls": 0, "raises": 0}


class Evidence:
    def __init__(self, hands):
        self.hands = hands

    def before(self, hand):
        stats = defaultdict(_empty)
        start = hand.get("started_ts")
        if not isinstance(start, (int, float)):
            return {}
        for past in self.hands:
            end = past.get("ended_ts")
            if past is hand or not isinstance(end, (int, float)) or end >= start or past["warnings"]:
                continue
            if not past["frames"][-1]["finished"]:
                continue
            seen = set()
            for previous, current in zip(past["frames"], past["frames"][1:], strict=False):
                action = current["action"]
                if not action or action["name"] not in {"CHECK", "FOLD", "CALL", "BET", "RAISE"}:
                    continue
                actor = next(p for p in current["players"] if p["seat"] == action["seat"])
                key = actor.get("player_key")
                if not key:
                    continue
                seen.add(key)
                row = stats[key]
                row["decisions"] += 1
                if previous["stage"] != current["stage"]:
                    continue
                old = next(p for p in previous["players"] if p["seat"] == action["seat"])
                cost = max(p["bet"] for p in previous["players"]) - old["bet"]
                if cost > 1e-8:
                    row["facing_bet"] += 1
                    row[{"FOLD": "folds", "CALL": "calls"}.get(action["name"], "raises")] += 1
            for key in seen:
                stats[key]["hands"] += 1
        return copy.deepcopy(dict(stats))


def evidence_for(players, stats):
    """Broad response evidence is displayed, never treated as a node-specific read."""
    result = []
    for p in players:
        row = stats.get(p.get("player_key"), _empty())
        result.append({"seat": p["seat"], **row, "personal_adjustment": False})
    return result
