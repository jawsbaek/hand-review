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
| Pokerist `.jsonl` | `replay` / `serve`. `kind: pokerist-hand`, `hero`, `board`, 프로토콜 `actions`를 담은 관측 기록. |
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

각 결정에서 **내 액션·사이징, 솔버 후보, 실전 코칭 추천**을 비교합니다. 레이즈 최종액·추가 지불액·추가액/현재 팟 비율을 구분하고, 상세에서 액션별 EV·계산한 솔버 빈도·모델 오차·레인지 가정을 확인합니다. 기존 블런더·베스트 필터는 이 수치 비교와 별개인 휴리스틱 후보입니다.

v0.3.0의 실제 솔버 EV 엔진도 고정 OOP/IP 레인지를 명시해 사용할 수 있습니다.

```sh
cargo build --release --manifest-path ev_rust/Cargo.toml
uv run hand-review replay samples/pokerist/demo.jsonl -o reports/ev-demo.html \
  --oop-range "KK,77,22,54s,65s" --ip-range "QQ,JJ"
```

위 레인지는 합성 예시용입니다. 지정하지 않으면 화면에 표시되는 버전별 모델 기본 레인지를 사용합니다. 이는 검증된 프리플랍 차트나 실제 상대 레인지가 아닙니다. 솔버는 구조가 완전한 헤즈업 플랍·턴·리버에서 후보 베팅·레이즈 사이즈를 비교하고 유망한 베팅 주변을 한 차례 더 계산합니다. 대표 추천은 계산된 빈도를 따릅니다. 경로·팟 불일치, 메모리 1GiB, 기본 12초/회 시간 상한, 수렴 부족은 솔버 결과를 보류합니다.

재생용 솔버는 계산 전에 양쪽 플레이어와 이후 스트리트의 트리 전체에 1BB 최소 베팅을 적용하며, 실제 짧은 스택의 올인은 허용합니다. 유효 스택 기준 올인은 내 실제 스택에서 합법적인 선언액으로 표시하고 미매칭 초과분은 반환합니다. 이전 EV 바이너리는 다시 빌드해야 하며, 트리 전체의 최소 베팅 보장이 없으면 결과를 보류합니다.

프리플랍·멀티웨이는 재현 가능한 몬테카를로 응답 모델로 계산합니다. 현재 스트리트의 나머지 액션과 상대 재공격 1회까지 시뮬레이션한 뒤 남은 보드는 체크다운합니다. 사라진 기여금 없이 사이드 팟·올인·무승부·미매칭 금액 반환을 계산합니다. 레이크 0, 근사 응답 정책, 폴드한 사람의 카드 분포 미반영을 가정합니다. **이후 스트리트의 베팅이나 핸드 전체의 최적 전략을 계산한 값은 아닙니다.** 기본 코칭은 세 가지 응답 가정의 보수적 추정값을 비교하며, 샘플링 오차와 모델이 틀릴 위험을 구분합니다. `--analysis-samples 512`로 표본을 늘리거나 `--no-solver`로 모델만 계산할 수 있습니다.

응답 모델은 플레이어별 재레이즈 권한을 추적해 숏 올인으로 닫힌 액션을 구분하고, 콜한 사람이 가져갈 수 있는 기여금만으로 팟오즈를 계산합니다. 가져갈 수 없는 사이드팟은 콜의 이익으로 세지 않습니다. 이 규칙 검증이 가정한 응답 정책을 프로 전략으로 검증한 것은 아닙니다.

상대 관측은 닉네임 대신 파트너/플레이어 ID로 구분하고, 해당 핸드 시작 전에 끝난 신뢰 가능한 기록만 사용합니다. 전체 폴드율만으로 조합·보드·사이즈별 전략을 알 수 없어 개인별 자동 공략은 보류합니다. 기본 추천을 유지하면서 폴드 확률 ±15%p 가정 실험을 제공합니다. 지원되는 솔버 장면에서는 현재 보드의 상대 첫 응답 노드를 고정해 다시 풀고, 나머지는 모델 시나리오로 표시합니다. 락 상태의 수렴 수치는 가정이 틀렸을 때의 손실 보장이 아닙니다. 방법 배경: [노드 락킹](https://piosolver.com/docs/viewer/node_locking/), [관측 신뢰도를 반영한 상대 공략 연구](https://proceedings.mlr.press/v5/johanson09a.html). 이 자료들이 현재 구현을 검증한 것은 아닙니다.

레인지를 브라우저에서 수정하고 재계산하려면:

```sh
uv run hand-review serve samples/pokerist/demo.jsonl --port 8765
# http://127.0.0.1:8765/ 열기. 종료: Ctrl+C
```

로컬 분석 화면은 루프백에만 연결하고 Host/Origin·세션 토큰을 확인하며, 계산 결과를 `.hand-review-cache`에 보관합니다. 외부 서비스로 데이터를 보내지 않습니다. HTML 파일에서도 저장된 추천과 가정 실험은 볼 수 있지만 레인지 재계산에는 로컬 분석 프로세스가 필요합니다. 잘못된 입력은 기존 결과를 유지하고 수정할 수 있습니다.

Net은 핸드 경계의 스택 차이여서 충전 등이 섞일 수 있고 `GS_COLLECT_POT`은 배당으로 해석하지 않습니다. 시작 누락·베팅 모순·혼입 경계는 경고합니다. `/s4`는 원문 표기를 보존하며 내부 `s`는 슈트 대응 토큰입니다. 결과·미래 카드·기록된 내 선택은 추천 후보 구성에 사용하지 않습니다.

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
