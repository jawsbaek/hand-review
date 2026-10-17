"""postflop-solver(Rust) 기반 액션별 EV PoC.

EV 정의 (postflop-solver expected_values_detail 그대로):
  EV(a) = 해당 노드 이후 hero 스택의 기대 변화량 + 이미 팟에 있던 칩 중 hero가 가져가는 몫.
  즉 "지금 노드에서 hero가 앞으로 팟에서 회수할 칩 - 앞으로 추가로 넣을 칩".
  FOLD = 0, 쇼다운에서 지는 체크 = 0, 상대 체크백 시 이기는 체크 = 현재 팟.
  이미 넣은 칩(sunk)은 비용으로 치지 않으므로 같은 노드의 액션 간 차이(EV loss)가 바로 칩 손실.
단위: 입력 pot/eff_stack과 동일 (내부적으로 SCALE배 정수 칩으로 풀고 되돌림).

빌드: cargo build --release --manifest-path ev_rust/Cargo.toml
"""

import json
import subprocess
import time
from pathlib import Path

BIN = Path(__file__).parent / "ev_rust" / "target" / "release" / "ev_rust"
# ponytail: 솔버가 i32 칩만 받으므로 100배 스케일 (0.01 단위 해상도), 소수 bb 더 필요하면 키울 것
SCALE = 100


def solve_node(
    board,
    oop_range,
    ip_range,
    pot,
    eff_stack,
    hero,
    hero_combo,
    bet_size_pct=50,
    path=(),
    bet_sizes=None,
    raise_sizes="",
    target_expl_pct=0.1,
    max_iter=1000,
    max_mem_gib=8.0,
    **extra,
) -> dict:
    """원시 결과(actions/evs/strategy/exploitability/solve_ms/mem_bytes) 반환. path = 액션 이름(찬스 노드는 카드)."""
    req = {
        "board": list(board),
        "oop_range": oop_range,
        "ip_range": ip_range,
        "pot": round(pot * SCALE),
        "eff_stack": round(eff_stack * SCALE),
        "bet_sizes": bet_sizes or f"{bet_size_pct}%",
        # ponytail: 기본은 레이즈 없음(검증 스팟 사양), 실전 트리는 raise_sizes="2.5x" 등 넘길 것
        "raise_sizes": raise_sizes,
        "hero": hero,
        "hero_combo": hero_combo,
        "path": list(path),
        "target_expl_pct": target_expl_pct,
        "max_iter": max_iter,
        "max_mem_gib": max_mem_gib,  # 트리 메모리 추정치 초과 시 솔브 전에 중단
        **extra,  # add_allin_threshold / force_allin_threshold / merging_threshold / compress
    }
    if not BIN.exists():
        raise FileNotFoundError(f"{BIN} 없음: cargo build --release --manifest-path ev_rust/Cargo.toml")
    p = subprocess.run([BIN], input=json.dumps(req), capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ev_rust 실패: {p.stderr.strip()}")
    out = json.loads(p.stdout)
    out["evs"] = [v / SCALE for v in out["evs"]]
    out["ev"] = dict(zip(out["actions"], out["evs"], strict=True))
    out["pot"] /= SCALE
    out["exploitability"] /= SCALE
    return out


def action_evs(
    board, oop_range, ip_range, pot, eff_stack, hero, hero_combo, bet_size_pct=50, **opts
) -> dict[str, float]:
    """hero_combo의 액션별 EV (pot 단위와 동일). opts: path, bet_sizes, raise_sizes, target_expl_pct, max_iter."""
    r = solve_node(board, oop_range, ip_range, pot, eff_stack, hero, hero_combo, bet_size_pct, **opts)
    return r["ev"]


if __name__ == "__main__":
    spot = dict(
        board=["Ks", "7d", "2c", "3h", "9s"],
        oop_range="KK,77,22,54s,65s",
        ip_range="QQ,JJ",
        pot=10,
        eff_stack=10,
        bet_size_pct=100,
    )
    # 허용오차: 목표 exploitability = 팟의 0.1% (0.01) -> 무차별 액션 간 EV 차 < 0.05 (팟 0.5%)로 체크
    TOL = 0.05

    t = time.perf_counter()
    air = solve_node(hero="oop", hero_combo="5s4s", **spot)
    river_ms = (time.perf_counter() - t) * 1000
    print(
        "air 5s4s:",
        air["actions"],
        air["evs"],
        "strat",
        air["strategy"],
        f"expl={air['exploitability']:.4f} solve={air['solve_ms']:.0f}ms wall={river_ms:.0f}ms",
    )
    ev = air["ev"]
    bet = next(k for k in ev if k != "CHECK")  # 100% 팟 = 스택이라 "BET 100" 또는 "ALLIN"
    # 1. 혼합 콤보는 무차별
    assert 0.05 < air["strategy"][1] < 0.95, "air should mix"
    assert abs(ev["CHECK"] - ev[bet]) < TOL, ev
    # 3. 쇼다운 가치 0인 에어의 체크 EV = 0 (체크백되면 지고, 베팅 받으면 폴드 -> 회수 0)
    assert abs(ev["CHECK"]) < 1e-6, ev

    kk = action_evs(hero="oop", hero_combo="KcKd", **spot)
    print("value KcKd:", kk)
    # 2. 밸류는 베팅 >= 체크
    assert kk[bet] >= kk["CHECK"] - 1e-6, kk

    ip = solve_node(hero="ip", hero_combo="QhQd", path=[bet], **spot)
    print("IP QhQd vs bet:", ip["ev"], "strat", ip["strategy"])
    ipev = ip["ev"]
    # 4. 블러프캐처 콜/폴드 무차별 (FOLD = 0 정의)
    assert ipev["FOLD"] == 0.0 and abs(ipev["CALL"] - ipev["FOLD"]) < TOL, ipev

    # 실전 플랍: 100bb SRP (BTN open vs BB call, 팟 5.5bb, 스택 97.5bb)
    # 플랍 33%/75%, 턴 66%, 리버 75%, 레이즈 3x -> 트리 4.7GiB (전 스트리트 33/75 + 2.5x면 27GiB)
    t = time.perf_counter()
    flop = solve_node(
        board=["Qs", "Jh", "2d"],
        oop_range="QQ-22,AQs-A2s,K9s+,Q9s+,J9s+,T8s+,97s+,86s+,75s+,64s+,54s,ATo+,KTo+,QTo+,JTo",
        ip_range="22+,A2s+,K5s+,Q8s+,J8s+,T7s+,96s+,86s+,75s+,64s+,54s,A8o+,KTo+,QTo+,JTo",
        pot=5.5,
        eff_stack=97.5,
        hero="oop",
        hero_combo="AhKd",
        bet_sizes="33%,75%",
        turn_bet_sizes="66%",
        river_bet_sizes="75%",
        raise_sizes="3x",
        target_expl_pct=0.5,
    )
    print(f"flop AhKd: {flop['ev']} strat {flop['strategy']}")
    print(
        f"flop solve={flop['solve_ms'] / 1000:.1f}s wall={time.perf_counter() - t:.1f}s "
        f"mem={flop['mem_bytes'] / 2**30:.2f}GiB expl={flop['exploitability']:.4f}bb"
    )
    print("OK")
