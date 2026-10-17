# hand-review

[English](README.md)

내 온라인 포커 핸드 히스토리를 분석하는 작은 CLI입니다. [PokerKit](https://github.com/uoftcprg/pokerkit) 기반.

- **프리플랍 지표**: VPIP, PFR, 3Bet / 포스트플랍 레이즈에 폴드율(F2R)
- **성적**: net bb, bb/100, **올인 EV bb/100** (올인 시점 equity로 운을 걷어낸 손익)
- **ICM**: Malmuth-Harville 칩 → 상금 기대값
- **토너먼트 ROI / ITM** (CSV 입력)
- **터미널 UI**(Textual), 열 정렬 가능
- **Pokerist 브라우저 복기**: 테이블 재생, 결정별 블런더·베스트 후보 필터, 먼저 선택하는 연습 모드
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
hand-review replay <Pokerist.jsonl|폴더> --output reports/replay.html
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
| Pokerist `.jsonl` | `replay` 전용. `kind: pokerist-hand`, `hero`, `board`, 프로토콜 `actions`를 담은 관측 기록. |
| MTT CSV | 헤더 `date,name,buyin,prize`. `samples/mtt/tournaments.csv` 참고. |

### Pokerist 브라우저 복기

```sh
uv run hand-review replay samples/pokerist/demo.jsonl -o reports/demo.html
open reports/demo.html  # macOS; 다른 OS에서는 브라우저로 파일 열기
```

데모는 모두 합성 데이터입니다. 실제 세션은 본인의 로컬 JSONL 내보내기 파일을 지정하세요.
생성된 HTML 한 파일에 데이터와 화면이 들어가며 인터넷 연결이나 서버가 필요 없습니다.
실제 내보내기 파일과 복기 결과는 로컬에 두세요. 둘 다 gitignore에 포함하고 합성 샘플만 추적합니다.

- 재생·일시 정지·한 단계 이동·타임라인 이동·스트리트 이동·다음 내 결정 이동. 자동 재생은 기본적으로 내 결정에서 멈춥니다.
- 블런더·베스트 **후보** / 검토 / 미평가 필터. 한 핸드에 잘한 결정과 의심스러운 결정이 함께 있을 수 있습니다.
- ‘먼저 선택하기’에서는 내 선택 후 실제 액션과 평가를 공개합니다. 이후에는 실제 기록을 재생하며 가상의 분기를 만들지 않습니다.
- 결과는 기본적으로 숨깁니다. 미래 보드는 해당 스트리트에서, 상대 공개 카드는 마지막 장면에서만 보여줍니다.
- 자리 이탈은 기존 기여금을 유지하며 참가 인원에서 제외합니다. 이미 올인한 플레이어의 팟 참가 권리는 유지하고, 같은 좌석의 새 입장자를 기존 핸드 참가자로 바꾸지 않습니다.
- 레이즈는 스트리트 최종액과 추가 지불액을 구분합니다. 예: BB에서 2BB를 더 냈다면 ‘레이즈 3BB (추가 2BB)’로 표시합니다.

솔버 레인지를 명시하지 않으면 보수적인 **휴리스틱 후보** 분류입니다. GTO 최적해나 계산한 EV를 뜻하지 않습니다. 근거가 부족하면 미평가로 두고, 각 규칙과 한계를 화면에 설명합니다. Net은 기록의 핸드 경계 스택 차이이므로 충전 등이 섞일 수 있습니다. `GS_COLLECT_POT`은 배당으로 해석하지 않습니다. 시작 누락·베팅 모순·미완료·서로 다른 핸드의 기록 혼입은 경고합니다. 슈트 4는 `/s4` 표기를 유지하며 내부 계산의 `s`는 일관된 슈트 대응용 토큰일 뿐입니다.

v0.3.0의 실제 솔버 EV 엔진도 고정 OOP/IP 레인지를 명시해 사용할 수 있습니다.

```sh
cargo build --release --manifest-path ev_rust/Cargo.toml
uv run hand-review replay samples/pokerist/demo.jsonl -o reports/ev-demo.html \
  --oop-range "KK,77,22,54s,65s" --ip-range "QQ,JJ"
```

위 레인지는 합성 헤즈업 샘플용이며 실제 상대의 레인지가 아닙니다. 기록이 완전한 헤즈업 턴·리버만 채점하고 플랍·멀티웨이는 휴리스틱 또는 미평가로 둡니다. 경로 미지원·계산당 45초 제한·메모리 1GiB 제한·수렴 부족은 솔버 등급을 부여하지 않고 표시합니다. 실제 사이즈는 가장 가까운 트리 액션에 대응합니다. EV 손실 2BB 이상은 블런더 후보, 0.1BB와 보고된 exploitability 두 배 중 큰 값 이내는 베스트 후보, 그 외 채점된 결정은 검토입니다.

### 솔버 (선택)

```sh
./scripts/setup_solver.sh   # curl, shasum, unzip 필요. TexasSolver v0.2.0을 ~/.cache/hand-review/solver에 받고 SHA-256 검증
uv run python -m hand_review.solver   # 자가 점검: 작은 플랍 스팟 풀기
```

다른 위치를 쓰려면 `HAND_REVIEW_SOLVER_DIR`을 지정하세요. Apple Silicon에서는 macOS 빌드가 Rosetta로 실행됩니다(`softwareupdate --install-rosetta`).
`ranges.py`는 PioSOLVER 스타일 `핸드,weight` CSV 레인지를 TexasSolver 레인지 문자열로 바꿉니다.

### 턴·리버 EV 채점 (선택, AGPL)

헤즈업 팟에서 카드를 아는 턴·리버 결정마다 `EV(최선 액션) - EV(실제 액션)`을 계산합니다.
[postflop-solver](https://github.com/b-inary/postflop-solver)의 실제 액션별 EV를 쓰므로,
균형에서 섞어 쓰는 액션은 손실 0입니다. 플랍은 채점하지 않습니다.

```sh
cargo build --release --manifest-path ev_rust/Cargo.toml   # Rust 툴체인 필요
uv run hand-review hands samples/ev --oop-range "KK,77,22,54s,65s" --ip-range "QQ,JJ"
```

레인지는 문자열 또는 CSV 경로입니다. OOP/IP별로 고정되고 앞선 액션으로 좁히지 않으므로 숫자는
대략적인 참고용입니다. 트리에 없는 벳 사이즈는 가장 가까운 사이즈로 매핑합니다. 다른 위치의 바이너리를 쓰려면 `HAND_REVIEW_EV_BIN`을 지정하세요.
빌드하지 않아도 `hand-review`는 그대로 동작하고, EV 테스트만 건너뜁니다.

## 구조

| 파일 | 역할 |
|---|---|
| `src/hand_review/analyze.py` | CLI(`hand-review`). 핸드 로딩, PokerKit으로 재생, 지표 집계, ICM, MTT ROI |
| `src/hand_review/tui.py` | 같은 결과를 탭으로 보여주는 Textual 앱 |
| `src/hand_review/pokerist.py` | Pokerist JSONL 검증 및 관측 상태 재구성 |
| `src/hand_review/review.py` | 액션 직전 정보로 휴리스틱 후보 분류·선택적 실제 솔버 EV 비교 |
| `src/hand_review/replay.py`, `replay.html` | 인터넷 연결 없이 여는 브라우저 복기 보고서 |
| `src/hand_review/solver.py` | TexasSolver를 서브프로세스로 실행해 전략 트리 반환 |
| `src/hand_review/ranges.py` | 레인지 CSV → 솔버 레인지 문자열 |
| `src/hand_review/ev_engine.py` | `ev_rust`를 실행(서브프로세스, JSON)해 액션별 EV 반환 |
| `src/hand_review/exploit.py`, `best_response.py` | 라이브러리(아직 CLI 미연결): GTO 전략에 상대 F2R 읽기를 섞되, 읽기가 틀렸을 때 잃을 EV로 상한 |
| `ev_rust/` | postflop-solver 기반 Rust CLI: 스팟을 풀고 노드의 EV 출력 (AGPL-3.0) |
| `scripts/capture.py` | TUI 화면을 `captures/*.svg` + `.txt`로 저장(리뷰용) |
| `scripts/setup_solver.sh` | TexasSolver 다운로드·검증 |

`hands` 흐름: `load_hands`(PHH / PokerStars 파서, 레이크·앤티 보정) → `reveal_shown_cards`(쇼다운 카드를 딜 단계에 채워 올인 equity 계산 가능하게) → `analyze_hand`가 액션을 재생하며 프리플랍 지표와 첫 올인 시점 팟 equity 계산 → 플레이어별 `Stats` → 표 출력.

## 알려진 한계

- 올인 equity는 몬테카를로(5000샘플 기준 약 ±0.7%).
- `players` 없는 PHH는 좌석(`p1`, `p2`…)으로 묶임.
- 스트래들: 가장 큰 블라인드를 bb로 간주.
- 캐시와 토너먼트를 한 폴더에 섞으면 bb 단위가 섞임. 폴더를 나누세요.
- 통계 분석은 PHH/PokerStars를 지원하고 Pokerist 관측 JSONL은 `replay`에서만 지원합니다. 다른 사이트(GG 등)는 파서 추가가 필요합니다.
- ICM은 전수 계산이라 파이널 테이블(약 9명)까지만 실용적.

## 개발

```sh
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pytest
# 브라우저 회귀 검증 (Playwright는 개발 도구이며 실행 의존성은 아닙니다):
npm install --no-save --no-package-lock playwright@1.58.1
npx playwright install chromium
uv run hand-review replay samples/pokerist/demo.jsonl -o reports/demo.html
node scripts/verify_replay.mjs
```

## 라이선스

MIT, [LICENSE](LICENSE) 참고.

의존성: PokerKit(MIT), Textual(MIT). TexasSolver는 AGPL-3.0이며 이 리포에 **포함되지 않습니다**. `setup_solver.sh`가 별도로 내려받고 `solver.py`는 외부 프로그램으로 실행만 합니다.

예외는 `ev_rust/` 하나입니다. postflop-solver(AGPL-3.0-or-later)를 링크하므로 이 폴더만
AGPL-3.0-or-later입니다([ev_rust/LICENSE](ev_rust/LICENSE)). 나머지는 MIT이고, `src/hand_review/ev_engine.py`는
빌드된 바이너리를 별도 프로세스로 실행해 JSON만 주고받습니다.
