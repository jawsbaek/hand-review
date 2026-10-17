"""Compare actual play with equilibrium candidates and explicit coaching scenarios."""

import copy
import functools
import hashlib
import json
import math
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from hand_review import coaching, ev_engine
from hand_review.pokerist import canonical_card
from hand_review.profiles import evidence_for


@dataclass(frozen=True)
class AnalysisOptions:
    samples: int = 128
    solver: bool = True
    solver_timeout: float = 12
    node_locks: bool = True


def _rows(result, context):
    if result.get("min_bet") != 1:
        raise ValueError("1BB 최소 베팅을 보장하는 EV 엔진으로 다시 빌드해야 합니다.")
    if len(result.get("amounts", [])) != len(result["actions"]):
        raise ValueError("정확한 금액을 제공하는 EV 엔진으로 다시 빌드해야 합니다.")
    if not math.isfinite(result["exploitability"]) or result["exploitability"] > context["street"]["pot_bb"] * 0.01:
        raise ValueError("솔버 수렴 기준을 충족하지 못했습니다.")
    probabilities = result["strategy"]
    if len(probabilities) != len(result["actions"]) or not all(
        math.isfinite(x) and 0 <= x <= 1.001 for x in probabilities
    ):
        raise ValueError("솔버 빈도를 확인할 수 없습니다.")
    if abs(sum(probabilities) - 1) > 0.01:
        raise ValueError("솔버 빈도의 합이 1이 아닙니다.")
    if abs(result["pot"] - context["pot"] / context["bb"]) > 0.05:
        raise ValueError("이전 액션의 트리 대응으로 팟이 달라져 정확한 사이징 추천을 보류합니다.")
    hero = next(p for p in context["players"] if p["seat"] == context["hero_seat"])
    bet, stack = hero["bet"] / context["bb"], hero["stack"] / context["bb"]
    rows = []
    for name, amount, frequency in zip(result["actions"], result["amounts"], probabilities, strict=True):
        ev = result["ev"][name]
        if not math.isfinite(ev):
            raise ValueError("유효한 솔버 EV가 아닙니다.")
        paid, to = amount["paid"], amount["to"]
        if amount["kind"] in {"BET", "RAISE"}:
            minimum = 1 if amount["kind"] == "BET" else context["min_raise_to"] / context["bb"] - bet
            minimum = min(stack, minimum)
            if paid < minimum - 1e-8:
                if not amount.get("is_all_in"):
                    raise ValueError("솔버 트리에 최소 베팅·레이즈보다 작은 일반 베팅이 있습니다.")
                # HU solves truncate both stacks to the effective stack. A deep
                # hero must still announce a legal full bet/raise; its unmatched
                # excess returns, leaving the solved EV and frequency unchanged.
                paid, to = minimum, bet + minimum
            if paid > stack + 1e-8:
                raise ValueError("솔버 금액이 실제 남은 스택을 초과합니다.")
        rows.append(
            {
                "kind": amount["kind"],
                "paid_bb": round(paid, 4),
                "to_bb": round(to, 4),
                "uncalled_return_bb": round(paid - amount["paid"], 4),
                "frequency": frequency,
                "pot_pct": round(100 * paid / result["pot"], 1) if result["pot"] else None,
                "ev_bb": ev,
                "se_bb": None,
                "engine_action": name,
            }
        )
    return rows


def _representative(rows):
    # Equilibrium mixes can have equal EVs within numerical error. Respect the
    # calculated frequency instead of declaring a noisy max-EV action mandatory.
    return max(rows, key=lambda a: (a["frequency"], -a["paid_bb"]))


def shifted_locks(responses, shift):
    """Perturb fold response per combo, preserving other conditional action ratios.

    This is an explicit what-if, not an inference of combo-level frequencies from
    observed aggregate folds. Nodes after a check without a fold action are left
    unrestricted. Only first response nodes on the current board are touched.
    """
    result = []
    for node in responses:
        actions, strategy = node["actions"], list(node["strategy"])
        if "FOLD" not in actions or len(strategy) % len(actions):
            continue
        n, fold = len(strategy) // len(actions), actions.index("FOLD")
        fallback = actions.index("CALL") if "CALL" in actions else next(i for i in range(len(actions)) if i != fold)
        for hand in range(n):
            total = sum(strategy[a * n + hand] for a in range(len(actions)))
            if total <= 0:
                continue
            old = strategy[fold * n + hand] / total
            new = min(1.0, max(0.0, old + shift))
            for a in range(len(actions)):
                if a != fold:
                    strategy[a * n + hand] = (
                        (1 - new) * strategy[a * n + hand] / (total * (1 - old)) if old < 1 - 1e-7 else 0
                    )
            if old >= 1 - 1e-7:
                strategy[fallback * n + hand] = 1 - new
            strategy[fold * n + hand] = new
        result.append({"history": node["history"], "strategy": strategy})
    return result


def solve_recommendation(context, ranges, options):
    street = context["street"]
    unavailable = {"status": "unavailable", "note": "현재 엔진의 헤즈업 포스트플랍 분석 범위 밖입니다."}
    if not options.solver:
        return {"status": "unavailable", "note": "솔버 계산을 끈 상태입니다."}
    if not ev_engine.available():
        return {"status": "unavailable", "note": "이 환경에 선택적 EV 엔진이 설치되지 않았습니다."}
    if not context["trustworthy"] or len(context["board"]) not in (3, 4, 5) or not street or context["active"] != 2:
        return unavailable
    if street["oop"] is None or street["pot_bb"] <= 0 or street["eff_bb"] <= 0:
        return unavailable
    players = street.get("players", [])
    if len(players) != 2:
        return unavailable
    oop = street["oop"]
    ip = next(p["seat"] for p in players if p["seat"] != oop)
    params = {
        "board": list(map(canonical_card, street["board"])),
        "oop_range": ",".join(coaching.CLASSES) if ranges[str(oop)].lower() in {"random", "100%"} else ranges[str(oop)],
        "ip_range": ",".join(coaching.CLASSES) if ranges[str(ip)].lower() in {"random", "100%"} else ranges[str(ip)],
        "pot": street["pot_bb"],
        "eff_stack": street["eff_bb"],
        "hero": "oop" if context["hero_seat"] == oop else "ip",
        "hero_combo": "".join(map(canonical_card, context["cards"])),
        "path": street["path"],
        "bet_sizes": ",".join(
            f"{s}%"
            for s in sorted(
                {25, 50, 75, 100, 150} | {float(a.split()[1]) for a in street["path"] if a.startswith("BET ")}
            )
        ),
        "raise_sizes": "2x,3x",
        "max_mem_gib": 1.0,
        "min_bet": 1.0,
        "max_iter": 1000,
        "timeout_seconds": options.solver_timeout,
        "include_responses": options.node_locks,
    }
    try:
        result = ev_engine.solve_node(**params)
        rows = _rows(result, context)
        representative = _representative(rows)
        # A bounded finer bet grid. Candidate construction never uses the actual
        # hero action, which is compared only after recommendation generation.
        if representative["kind"] == "BET" and 12.5 <= (pct := representative["pot_pct"]) <= 200:
            sizes = sorted({25, 50, 75, 100, 150, round(pct - 12.5, 2), round(pct + 12.5, 2)} - {0})
            refined = {**params, "bet_sizes": ",".join(f"{s}%" for s in sizes)}
            try:
                refined_result = ev_engine.solve_node(**refined)
                refined_rows = _rows(refined_result, context)
                params, result, rows = refined, refined_result, refined_rows
            except (RuntimeError, ValueError, subprocess.TimeoutExpired):
                pass  # Keep the converged coarse solve, explicitly report its grid.
        scenarios = []
        if options.node_locks:
            for ident, title, shift in coaching.SCENARIOS[1:]:
                locks = shifted_locks(result.get("responses", []), shift)
                if not locks:
                    continue
                try:
                    adjusted = ev_engine.solve_node(**{**params, "locks": locks, "include_responses": False})
                    adjusted_rows = _rows(adjusted, context)
                    scenarios.append(
                        {
                            "id": ident,
                            "title": title,
                            "status": "ready",
                            "method": "node_lock",
                            "actions": adjusted_rows,
                            "recommendation": _representative(adjusted_rows),
                            "constrained_exploitability_bb": adjusted["exploitability"],
                        }
                    )
                except (RuntimeError, ValueError, subprocess.TimeoutExpired):
                    scenarios.append(
                        {
                            "id": ident,
                            "title": title,
                            "status": "unavailable",
                            "note": "이 가정은 계산 상한 내에 수렴하지 못했습니다.",
                        }
                    )
        return {
            "status": "ready",
            "method": "solver",
            "recommendation": _representative(rows),
            "actions": rows,
            "scenarios": scenarios,
            "ranges": ranges,
            "exploitability_bb": result["exploitability"],
            "solve_ms": result["solve_ms"],
            "bet_sizes": params["bet_sizes"],
            "raise_sizes": params["raise_sizes"],
            "note": "수정 가능한 스트리트 시작 레인지와 후보 트리 안의 근사 균형입니다. "
            "대표 추천은 가장 높은 빈도의 액션입니다."
            + (
                " 유효 스택보다 큰 미매칭분은 반환되는 합법 선언액으로 표시했습니다."
                if any(a["uncalled_return_bb"] > 0 for a in rows)
                else ""
            ),
            "scenario_note": "가정 실험은 현재 보드의 상대 첫 응답 노드만 고정합니다. "
            "락 상태의 수렴 수치는 자유로운 상대에 대한 손실 보장이 아닙니다.",
        }
    except subprocess.TimeoutExpired:
        return {"status": "unavailable", "note": "솔버 계산 시간 상한을 넘어 모델 추정만 제공합니다."}
    except (ValueError, RuntimeError, FileNotFoundError, KeyError, StopIteration) as error:
        note = (
            str(error)
            if isinstance(error, ValueError)
            else "레인지·경로·메모리 상한 때문에 이 장면의 솔버 계산을 완료하지 못했습니다."
        )
        return {"status": "unavailable", "note": note}


def analyze(context, evidence, options, overrides=None):
    context = copy.deepcopy(context)
    try:
        model = coaching.estimate(context, overrides, options.samples)
    except ValueError as error:
        return {
            "status": "unavailable",
            "note": str(error),
            "model": {"status": "unavailable"},
            "solver": {"status": "unavailable", "note": "입력 가정을 먼저 확인하세요."},
        }
    if model["status"] != "ready":
        return {
            "status": "unavailable",
            "note": model["note"],
            "model": model,
            "solver": {"status": "unavailable", "note": "관측 기록을 먼저 확인하세요."},
        }
    solver = solve_recommendation(context, model["ranges"], options)
    players = [
        p
        for p in context["players"]
        if p["seat"] != context["hero_seat"] and not p["folded"] and (not p["departed"] or p["all_in"])
    ]
    return {
        "status": "ready",
        "model": model,
        "solver": solver,
        "coaching": {
            "basis": "solver_baseline" if solver["status"] == "ready" else "model_baseline",
            "recommendation": (solver if solver["status"] == "ready" else model)["recommendation"],
            "personal_adjustment": False,
            "note": "노드·사이즈별 충분한 개인 표본이 없어 기본 추천을 유지합니다. "
            "가정 실험은 상대의 실제 성향 판정이 아닙니다.",
        },
        "evidence": evidence_for(players, evidence),
        "range_labels": [
            {"seat": p["seat"], "position": p["position"], "hero": p["seat"] == context["hero_seat"]}
            for p in context["players"]
            if str(p["seat"]) in model["ranges"]
        ],
    }


@functools.lru_cache(maxsize=8)
def _revision(stamps):
    base = Path(__file__).parent
    source = b"".join(
        (base / name).read_bytes()
        for name in ("coaching.py", "recommendations.py", "pokerist.py", "profiles.py", "ev_engine.py")
    )
    return hashlib.sha256(source + repr(stamps).encode()).hexdigest()


def analyze_cached(context, evidence, options, overrides=None, cache_dir=None):
    """A private local cache invalidated by inputs, settings, source and engine build."""
    if cache_dir is None:
        return analyze(context, evidence, options, overrides)
    base = Path(__file__).parent
    stamps = tuple(
        (base / name).stat().st_mtime_ns
        for name in ("coaching.py", "recommendations.py", "pokerist.py", "profiles.py", "ev_engine.py")
    ) + (ev_engine.BIN.stat().st_mtime_ns if ev_engine.available() else 0,)
    payload = {
        "context": context,
        "evidence": evidence,
        "options": asdict(options),
        "overrides": overrides,
        "revision": _revision(stamps),
    }
    key = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
    folder = Path(cache_dir)
    path = folder / (key + ".json")
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        pass
    result = analyze(context, evidence, options, overrides)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=folder, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(result, stream, ensure_ascii=True, allow_nan=False)
        os.replace(temporary, path)
    except OSError:
        pass  # An unavailable cache must not change or prevent the calculation.
    return result
