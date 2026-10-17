# hand-review

[English](README.md)

내 온라인 포커 핸드 히스토리를 분석하는 작은 CLI입니다. [PokerKit](https://github.com/uoftcprg/pokerkit) 기반.

- **프리플랍 지표**: VPIP, PFR, 3Bet
- **성적**: net bb, bb/100, **올인 EV bb/100** (올인 시점 equity로 운을 걷어낸 손익)
- **ICM**: Malmuth-Harville 칩 → 상금 기대값
- **토너먼트 ROI / ITM** (CSV 입력)
- **터미널 UI**(Textual), 열 정렬 가능
- **GTO 솔버 래퍼(선택)**: [TexasSolver](https://github.com/bupticybee/TexasSolver)로 포스트플랍 스팟 계산

> 세션이 끝난 뒤 자기 핸드를 복기하는 용도입니다. 실시간 플레이 보조 도구가 아니며, 플레이 중에 쓰지 마세요.
> 서드파티 도구 사용 전 포커 사이트 이용약관을 확인하세요.

## 빠른 시작

[uv](https://docs.astral.sh/uv/)와 Python 3.12 이상이 필요합니다.

설치 없이 바로 실행:

```sh
uvx --from git+https://github.com/jawsbaek/hand-review hand-review icm --stacks 5000 3000 2000 --payouts 50 30 20
```

`hand-review` 명령을 설치하려면 `uv tool install git+https://github.com/jawsbaek/hand-review`, 샘플 핸드로 해보려면 clone:

```sh
git clone https://github.com/jawsbaek/hand-review.git
cd hand-review
uv sync
uv run hand-review hands samples/cash
```

## 사용법

clone한 폴더에서는 앞에 `uv run`을 붙이세요.

```sh
hand-review hands <파일|폴더> [--hero 이름] [--samples 5000]
hand-review icm --stacks 5000 3000 2000 --payouts 50 30 20
hand-review mtt samples/mtt/tournaments.csv
hand-review tui --hands samples/cash --mtt samples/mtt/tournaments.csv --stacks 5000 3000 2000 --payouts 50 30 20
```

`--samples`는 올인 equity 몬테카를로 샘플 수입니다. 읽을 수 없거나, 미지원 변형이거나, 중간에 끊긴 핸드는 건너뛰고 리포트 끝에 개수를 표시합니다. 중복 핸드는 한 번만 셉니다.

### 지원 입력

| 입력 | 비고 |
|---|---|
| `.phh` / `.phhs` | [Poker Hand History](https://phh.readthedocs.io/). 좌석이 아니라 이름으로 묶이도록 `players`를 꼭 적으세요. |
| PokerStars `.txt` | NL 홀덤 캐시·토너먼트. 레이크와 앤티 반영. |
| MTT CSV | 헤더 `date,name,buyin,prize`. `samples/mtt/tournaments.csv` 참고. |

### 솔버 (선택)

```sh
./scripts/setup_solver.sh   # curl, shasum, unzip 필요. TexasSolver v0.2.0을 ~/.cache/hand-review/solver에 받고 SHA-256 검증
uv run python -m hand_review.solver   # 자가 점검: 작은 플랍 스팟 풀기
```

다른 위치를 쓰려면 `HAND_REVIEW_SOLVER_DIR`을 지정하세요. Apple Silicon에서는 macOS 빌드가 Rosetta로 실행됩니다(`softwareupdate --install-rosetta`).
`ranges.py`는 PioSOLVER 스타일 `핸드,weight` CSV 레인지를 TexasSolver 레인지 문자열로 바꿉니다.

## 구조

| 파일 | 역할 |
|---|---|
| `src/hand_review/analyze.py` | CLI(`hand-review`). 핸드 로딩, PokerKit으로 재생, 지표 집계, ICM, MTT ROI |
| `src/hand_review/tui.py` | 같은 결과를 탭으로 보여주는 Textual 앱 |
| `src/hand_review/solver.py` | TexasSolver를 서브프로세스로 실행해 전략 트리 반환 |
| `src/hand_review/ranges.py` | 레인지 CSV → 솔버 레인지 문자열 |
| `scripts/capture.py` | TUI 화면을 `captures/*.svg` + `.txt`로 저장(리뷰용) |
| `scripts/setup_solver.sh` | TexasSolver 다운로드·검증 |

`hands` 흐름: `load_hands`(PHH / PokerStars 파서, 레이크·앤티 보정) → `reveal_shown_cards`(쇼다운 카드를 딜 단계에 채워 올인 equity 계산 가능하게) → `analyze_hand`가 액션을 재생하며 프리플랍 지표와 첫 올인 시점 팟 equity 계산 → 플레이어별 `Stats` → 표 출력.

## 알려진 한계

- 올인 equity는 몬테카를로(5000샘플 기준 약 ±0.7%).
- `players` 없는 PHH는 좌석(`p1`, `p2`…)으로 묶임.
- 스트래들: 가장 큰 블라인드를 bb로 간주.
- 캐시와 토너먼트를 한 폴더에 섞으면 bb 단위가 섞임. 폴더를 나누세요.
- PokerStars 텍스트만 파싱. 다른 사이트(GG 등)는 파서 추가 필요.
- ICM은 전수 계산이라 파이널 테이블(약 9명)까지만 실용적.

## 개발

```sh
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pytest
```

## 라이선스

MIT, [LICENSE](LICENSE) 참고.

의존성: PokerKit(MIT), Textual(MIT). TexasSolver는 AGPL-3.0이며 이 리포에 **포함되지 않습니다**. `setup_solver.sh`가 별도로 내려받고 `solver.py`는 외부 프로그램으로 실행만 합니다.
