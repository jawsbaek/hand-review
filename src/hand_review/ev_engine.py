"""postflop-solver(Rust, ev_rust/) 기반 액션별 EV 엔진 — 선택 기능.

ev_rust/는 AGPL-3.0-or-later(postflop-solver 파생물). 이 파일은 그 바이너리를 별도 프로세스로
실행하고 JSON만 주고받으므로 MIT로 남는다. 바이너리가 없으면 available()이 False.

EV 정의 (postflop-solver expected_values_detail 그대로):
  EV(a) = 해당 노드 이후 hero 스택의 기대 변화량 + 이미 팟에 있던 칩 중 hero가 가져가는 몫.
  즉 "지금 노드에서 hero가 앞으로 팟에서 회수할 칩 - 앞으로 추가로 넣을 칩".
  FOLD = 0, 쇼다운에서 지는 체크 = 0, 상대 체크백 시 이기는 체크 = 현재 팟.
  이미 넣은 칩(sunk)은 비용으로 치지 않으므로 같은 노드의 액션 간 차이(EV loss)가 바로 칩 손실.
단위: 입력 pot/eff_stack과 동일 (내부적으로 SCALE배 정수 칩으로 풀고 되돌림).

빌드: cargo build --release --manifest-path ev_rust/Cargo.toml
"""

import json
import os
import subprocess
from pathlib import Path

# 레포 루트의 ev_rust/에서 빌드한 바이너리. 다른 위치(설치형 실행 등)는 HAND_REVIEW_EV_BIN으로 지정
_REPO_BIN = Path(__file__).parents[2] / "ev_rust" / "target" / "release" / "ev_rust"
BIN = Path(os.environ.get("HAND_REVIEW_EV_BIN", _REPO_BIN))
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


def available():
    return BIN.exists()


def nearest_action(want, names):
    """정확히 같은 이름, 없으면 같은 종류(BET/RAISE) 중 %가 가장 가까운 액션. ev_rust의 nearest와 같은 규칙."""
    if want in names:
        return want
    kind, _, pct = want.partition(" ")
    if not pct:
        return None
    same = [n for n in names if n.startswith(kind + " ")]
    return min(same, key=lambda n: abs(float(n.partition(" ")[2]) - float(pct)), default=None)
