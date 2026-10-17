"""TexasSolver(CFR 솔버) 서브프로세스 래퍼.

사전 준비: ./scripts/setup_solver.sh 로 .solver/console_solver 설치.

사용법(데모):
  uv run solver.py
"""

import json
import platform
import subprocess
import tempfile
from pathlib import Path

SOLVER_DIR = Path(__file__).parent / ".solver"
BINARY = SOLVER_DIR / "console_solver"


def solve(board, oop_range, ip_range, pot, effective_stack, bet_sizes=None, accuracy=1.0, max_iteration=200):
    """스팟을 솔버로 풀어 전략 트리(dict)를 반환.

    board: ["Qs","8d","7h"] 같은 카드 리스트(3~5장)
    oop_range/ip_range: "JTs,43s" 같은 PokerStove 표기 레인지 문자열
    bet_sizes: {(pos, street, kind): pct} — pos는 'oop'/'ip', kind는 'bet'/'raise'/'donk'.
               생략하면 모든 스트리트에 50% bet / 60% raise를 적용(단순 기본값).
    """
    if not BINARY.exists():
        raise FileNotFoundError("솔버 미설치: ./scripts/setup_solver.sh 먼저 실행하세요")
    bet_sizes = bet_sizes or {
        (pos, street, kind): pct
        for pos in ("oop", "ip")
        for street in ("flop", "turn", "river")
        for kind, pct in (("bet", 50), ("raise", 60))
    }
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "result.json"
        script = [
            f"set_pot {pot}",
            f"set_effective_stack {effective_stack}",
            f"set_board {','.join(board)}",
            f"set_range_ip {ip_range}",
            f"set_range_oop {oop_range}",
            *(f"set_bet_sizes {pos},{street},{kind},{pct}" for (pos, street, kind), pct in bet_sizes.items()),
            "set_allin_threshold 1.0",
            "build_tree",
            "set_thread_num 8",  # 12로 올리면 Rosetta 환경에서 SIGSEGV 확인됨 — 올리지 말 것
            f"set_accuracy {accuracy}",
            f"set_max_iteration {max_iteration}",
            "set_use_isomorphism 1",
            "start_solve",
            "set_dump_rounds 1",
            f"dump_result {out_path}",
        ]
        cmd = (["arch", "-x86_64"] if platform.system() == "Darwin" else []) + [str(BINARY)]
        try:
            subprocess.run(
                cmd, input="\n".join(script), capture_output=True, text=True, timeout=300, check=True, cwd=SOLVER_DIR
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"솔버 실패(exit {e.returncode}):\n{(e.stderr or e.stdout)[-2000:]}") from e
        return json.loads(out_path.read_text())


def demo():
    strategy = solve(["Qs", "8d", "7h"], "JTs,43s", "T9s", pot=4, effective_stack=10, max_iteration=50)
    assert strategy["node_type"] == "action_node"
    freqs_by_combo = strategy["strategy"]["strategy"]
    assert set(freqs_by_combo) <= {"4c3c", "4d3d", "4h3h", "4s3s", "JcTc", "JdTd", "JhTh", "JsTs"}
    for combo, freqs in freqs_by_combo.items():
        assert abs(sum(freqs) - 1.0) < 1e-3, f"{combo} 전략 합이 1이 아님: {freqs}"
    print("ok:", strategy["actions"], "node, combos:", len(freqs_by_combo))


if __name__ == "__main__":
    demo()
