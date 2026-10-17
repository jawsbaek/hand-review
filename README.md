# hand-review

[![CI](https://github.com/jawsbaek/hand-review/actions/workflows/ci.yml/badge.svg)](https://github.com/jawsbaek/hand-review/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[한국어](README.ko.md)

A small command-line analyzer for your own online poker hand histories, built on [PokerKit](https://github.com/uoftcprg/pokerkit).

- **Preflop stats**: VPIP, PFR, 3-bet; postflop fold-to-raise (F2R)
- **Results**: net bb, bb/100, and **all-in EV bb/100** (luck removed using equity at the moment players are all in)
- **ICM**: Malmuth-Harville chip-to-prize equity
- **Tournament ROI / ITM** from a simple CSV
- **Terminal UI** (Textual) with sortable tables
- **Pokerist replay**: an offline browser table, action playback, decision filters and practice mode
- **Optional GTO solver wrapper** around [TexasSolver](https://github.com/bupticybee/TexasSolver) for postflop spots

> For studying your own hands after the session. It is not a real-time assistant; do not use it while playing.
> Check your poker site's terms of service before using any third-party tool.

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+. CLI and TUI output is in Korean (labels such as `칩` = chips, `토너먼트` = tournaments, `건너뜀` = skipped).

Try it without installing:

```sh
uvx --from git+https://github.com/jawsbaek/hand-review hand-review icm --stacks 5000 3000 2000 --payouts 50 30 20
```

Or install the `hand-review` command (`uv tool install git+https://github.com/jawsbaek/hand-review`), or work from a clone with the sample hands:

```sh
git clone https://github.com/jawsbaek/hand-review.git
cd hand-review
uv sync
uv run hand-review hands samples/cash
```

```
player           hands   net bb    bb/100  EV bb/100  VPIP   PFR  3Bet   F2R
Hero                 2    107.8    5390.0     3539.4 100.0 100.0     -     -
Villain1             1     -0.5     -50.0      -50.0   0.0   0.0   0.0     -
Villain2             1   -100.0  -10000.0    -6298.8 100.0 100.0 100.0     -
...
```

## Usage

From a clone, prefix with `uv run`.

```sh
hand-review hands <file|folder> [--hero NAME] [--samples 5000]
hand-review replay <Pokerist.jsonl|folder> --output reports/replay.html
hand-review icm --stacks 5000 3000 2000 --payouts 50 30 20
hand-review mtt samples/mtt/tournaments.csv
hand-review tui --hands samples/cash --mtt samples/mtt/tournaments.csv --stacks 5000 3000 2000 --payouts 50 30 20
```

`--samples` is the Monte Carlo sample count for all-in equity. Hands that cannot be read, use an unsupported variant, or are cut off are skipped and counted at the end of the report; duplicate hands are counted once.

### Supported input

| Input | Notes |
|---|---|
| `.phh` / `.phhs` | [Poker Hand History](https://phh.readthedocs.io/) files. Include `players` so stats group by name, not seat. |
| PokerStars `.txt` | No-limit Hold'em cash and tournaments. Rake and antes are applied. |
| Pokerist `.jsonl` | `replay` / `serve`. Observation exports with `kind: pokerist-hand`, `hero`, `board`, and protocol `actions`. |
| MTT CSV | Header `date,name,buyin,prize`. See `samples/mtt/tournaments.csv`. |

### Pokerist browser replay

```sh
uv run hand-review replay samples/pokerist/demo.jsonl -o reports/demo.html
open reports/demo.html  # macOS; open the file with a browser on other platforms
```

The demo is entirely synthetic. Use your own local export instead to review a session.
The generated HTML includes all its data and assets, works offline, and makes no external requests.
Keep real exports and generated reports local; both are gitignored (only the synthetic sample is tracked).

- Play, pause, step, scrub, jump to a street or the next hero decision; autoplay pauses at hero decisions by default.
- Filter **blunder / best candidates**, review decisions or unscored decisions. One hand can contain both good and questionable actions.
- Switch to practice mode to choose before seeing the recorded action and review. This compares choices and then resumes the real history; it does not simulate an alternative continuation.
- Results stay hidden by default. Future board cards and opponent cards remain hidden until their replay point; exported opponent reveals appear only at the end.
- Table departures retain their recorded contributions. Departed players leave the action count, while departed all-in players remain eligible for pots. A new occupant does not replace the previous hand participant.
- Raises display the total street amount and, when different, the extra payment separately (for example, raise to 3 BB, adding 2 BB from the big blind).

Each decision now compares the recorded action and sizing with **solver candidates** and a separate **practical coaching recommendation**. Amounts distinguish raise-to totals, extra payments and payment/current-pot percentages. Details include candidate EVs, calculated solver frequencies, model sampling errors and editable range assumptions. The existing blunder/best filters remain heuristic candidates, separate from these numerical comparisons.

Build the optional solver for heads-up postflop equilibrium comparisons and node-lock scenarios:

```sh
cargo build --release --manifest-path ev_rust/Cargo.toml
uv run hand-review replay samples/pokerist/demo.jsonl -o reports/ev-demo.html \
  --oop-range "KK,77,22,54s,65s" --ip-range "QQ,JJ"
```

The example ranges describe the synthetic sample. Without overrides, ranges are versioned, visible **model priors, not solved preflop charts or measured opponent ranges**. The solver supports structurally complete heads-up flop/turn/river states, searches a finite bet/raise grid with bounded bet refinement, and preserves mixed frequencies. Incomplete paths, changed pot amounts, 1 GiB memory limits, timeouts (12 seconds per solve by default) and insufficient convergence withhold the solver result. These limits do not turn a model estimate into a solver result.

Replay solves enforce a 1 BB minimum bet throughout both players' branches and future streets before solving, while retaining genuine short-stack all-ins. Effective-stack all-ins are displayed as legal announced amounts for the player's real stack, with unmatched excess returned. Rebuild older EV binaries: results without the whole-tree minimum-bet guarantee are withheld.

Preflop and multiway coaching uses a reproducible Monte Carlo response model: simulate the rest of the current betting round, allow at most one opponent counter-raise, then check down sampled runouts. It handles dead contributions, all-in side pots, ties and unmatched returns. It assumes zero rake, approximate response policies, and no inference from unknown folded cards. **It does not optimize future-street betting or establish a full-hand optimal strategy.** Default coaching compares conservative estimates across three response assumptions; detail rows show sampling error separately from model uncertainty. Increase precision with `--analysis-samples 512`, or use `--no-solver` for model-only reports.

The response model tracks reopening rights per player, including short all-ins, and calculates call odds from contributions that caller can win. Unreachable side-pot money never improves its call odds. These rule checks do not validate the assumed response policy as professional strategy.

Opponent evidence uses partner/player IDs and only trustworthy completed hands ending before the reviewed hand. Broad aggregate observations cannot identify combo/board/size-specific strategy. Personal automatic exploitation is therefore withheld; the report retains the baseline and offers explicit fold-response ±15 percentage-point experiments. On supported solver states these experiments lock first opponent response nodes on the current board and resolve; other states use model scenarios. Locked-game convergence is not a loss bound against an unrestricted opponent. See [node locking](https://piosolver.com/docs/viewer/node_locking/) and [confidence-aware opponent exploitation](https://proceedings.mlr.press/v5/johanson09a.html) for the methodological background; those sources do not validate this implementation.

To edit ranges and recompute in the browser:

```sh
uv run hand-review serve samples/pokerist/demo.jsonl --port 8765
# Open http://127.0.0.1:8765/ ; Ctrl+C stops the local process.
```

The workbench binds only to loopback, checks Host/Origin and a per-session token, limits its queue, and caches calculations privately in `.hand-review-cache`. It sends no data to external services. The offline HTML still displays saved results and scenarios; live range recomputation requires the local workbench. Invalid input preserves the last valid result and is recoverable in the editor.

Net is the exported stack-boundary difference and may include top-ups; pot collection events are never treated as payouts. Missing starts, contradictory payments, incomplete records and mixed boundaries are flagged. Suit 4 keeps its literal `/s4` label; the internal `s` token is only a consistent suit mapping. Outcomes, future board/opponent cards and the recorded hero choice do not enter recommendation candidate construction.

### Solver (optional)

```sh
./scripts/setup_solver.sh   # needs curl, shasum, unzip; downloads TexasSolver v0.2.0 into ~/.cache/hand-review/solver and verifies its SHA-256
uv run python -m hand_review.solver   # self-check: solves a small flop spot
```

Set `HAND_REVIEW_SOLVER_DIR` to install or look for the solver elsewhere. On Apple Silicon the macOS build runs under Rosetta (`softwareupdate --install-rosetta`).
`ranges.py` converts PioSOLVER-style `hand,weight` CSV ranges into TexasSolver range strings.

### Turn/river EV scoring (optional, AGPL)

Scores each heads-up turn and river decision whose hole cards are known as
`EV(best action) - EV(chosen action)`, using real per-action EVs from
[postflop-solver](https://github.com/b-inary/postflop-solver). Mixed equilibrium actions cost 0.
The flop is not scored.

```sh
cargo build --release --manifest-path ev_rust/Cargo.toml   # needs a Rust toolchain
uv run hand-review hands samples/ev --oop-range "KK,77,22,54s,65s" --ip-range "QQ,JJ"
```

Ranges are a range string or a CSV path. They are fixed per OOP/IP and not narrowed by earlier
actions, so treat the numbers as a rough guide. Off-tree bet sizes map to the nearest size in the
solver tree. To use a binary elsewhere, set `HAND_REVIEW_EV_BIN`. Without the build, `hand-review` works as usual and the EV tests are skipped.

## How it works

| File | Role |
|---|---|
| `src/hand_review/analyze.py` | CLI (`hand-review`). Loads hands, replays them with PokerKit, aggregates stats, ICM, MTT ROI |
| `src/hand_review/tui.py` | Textual app showing the same results in tabs |
| `src/hand_review/pokerist.py` | Validates Pokerist JSONL and reconstructs observation snapshots |
| `src/hand_review/review.py` | Pre-action heuristic candidates and optional real solver EV comparisons |
| `src/hand_review/replay.py`, `replay.html` | Self-contained offline browser report and replay UI |
| `src/hand_review/solver.py` | Runs TexasSolver as a subprocess and returns its strategy tree |
| `src/hand_review/ranges.py` | Range CSV → solver range string |
| `src/hand_review/ev_engine.py` | Runs `ev_rust` (subprocess, JSON) and returns per-action EVs |
| `src/hand_review/exploit.py`, `best_response.py` | Library (not wired into the CLI yet): blends a GTO strategy with an opponent's F2R read, capped by the EV you'd lose if the read is wrong |
| `ev_rust/` | Rust CLI on postflop-solver: solve a spot, print EVs at a node (AGPL-3.0) |
| `scripts/capture.py` | Renders TUI screens to `captures/*.svg` + `.txt` for review |
| `scripts/setup_solver.sh` | Downloads and verifies TexasSolver |

Flow for `hands`: `load_hands` (PHH / PokerStars parser, with rake and ante fixes) → `reveal_shown_cards` (puts showdown cards back into the deal so all-in equity can be computed) → `analyze_hand` replays each action, records preflop stats, and computes pot equity at the first all-in → `Stats` per player → table.

## Known limitations

- All-in equity is Monte Carlo (about ±0.7% at 5000 samples).
- PHH files without `players` are grouped by seat (`p1`, `p2`, ...).
- Straddles: the largest blind is treated as the big blind.
- Mixing cash and tournament hands in one folder mixes bb units. Keep them in separate folders.
- Statistical analysis accepts PHH/PokerStars; Pokerist observation JSONL is supported by `replay` only. Other sites (GG, etc.) need a parser.
- ICM is exact enumeration, practical up to a final table (about 9 players).

## Development

```sh
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pytest
# Browser regression checks (Playwright is a development tool, not a runtime dependency):
npm install --no-save --no-package-lock playwright@1.58.1
npx playwright install chromium
uv run hand-review replay samples/pokerist/demo.jsonl -o reports/demo.html
node scripts/verify_replay.mjs
```

## License

MIT, see [LICENSE](LICENSE).

Dependencies: PokerKit (MIT), Textual (MIT). TexasSolver is AGPL-3.0; it is **not** included in this repository. `setup_solver.sh` downloads it separately and `solver.py` only runs it as an external program.

`ev_rust/` is the one exception: it links postflop-solver (AGPL-3.0-or-later), so that directory is
licensed AGPL-3.0-or-later ([ev_rust/LICENSE](ev_rust/LICENSE)). The rest of the repository stays MIT;
`src/hand_review/ev_engine.py` only runs the built binary as a separate process and exchanges JSON.
