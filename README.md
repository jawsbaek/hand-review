# poker-play-analyzer

[![CI](https://github.com/jawsbaek/poker-play-analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/jawsbaek/poker-play-analyzer/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[한국어](README.ko.md)

A small command-line analyzer for your own online poker hand histories, built on [PokerKit](https://github.com/uoftcprg/pokerkit).

- **Preflop stats**: VPIP, PFR, 3-bet
- **Results**: net bb, bb/100, and **all-in EV bb/100** (luck removed using equity at the moment players are all in)
- **ICM**: Malmuth-Harville chip-to-prize equity
- **Tournament ROI / ITM** from a simple CSV
- **Terminal UI** (Textual) with sortable tables
- **Optional GTO solver wrapper** around [TexasSolver](https://github.com/bupticybee/TexasSolver) for postflop spots

> For studying your own hands after the session. It is not a real-time assistant; do not use it while playing.
> Check your poker site's terms of service before using any third-party tool.

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+. CLI and TUI output is in Korean (labels such as `칩` = chips, `토너먼트` = tournaments, `건너뜀` = skipped).

```sh
git clone https://github.com/jawsbaek/poker-play-analyzer.git
cd poker-play-analyzer
uv sync
uv run analyze.py hands samples/cash
```

```
player           hands   net bb    bb/100  EV bb/100  VPIP   PFR  3Bet
Hero                 2    107.8    5390.0     3539.4 100.0 100.0     -
Villain1             1     -0.5     -50.0      -50.0   0.0   0.0   0.0
Villain2             1   -100.0  -10000.0    -6298.8 100.0 100.0 100.0
...
```

## Usage

```sh
uv run analyze.py hands <file|folder> [--hero NAME] [--samples 5000]
uv run analyze.py icm --stacks 5000 3000 2000 --payouts 50 30 20
uv run analyze.py mtt samples/mtt/tournaments.csv
uv run analyze.py tui --hands samples/cash --mtt samples/mtt/tournaments.csv --stacks 5000 3000 2000 --payouts 50 30 20
```

`--samples` is the Monte Carlo sample count for all-in equity. Hands that cannot be read, use an unsupported variant, or are cut off are skipped and counted at the end of the report; duplicate hands are counted once.

### Supported input

| Input | Notes |
|---|---|
| `.phh` / `.phhs` | [Poker Hand History](https://phh.readthedocs.io/) files. Include `players` so stats group by name, not seat. |
| PokerStars `.txt` | No-limit Hold'em cash and tournaments. Rake and antes are applied. |
| MTT CSV | Header `date,name,buyin,prize`. See `samples/mtt/tournaments.csv`. |

### Solver (optional)

```sh
./scripts/setup_solver.sh   # needs curl, shasum, unzip; downloads TexasSolver v0.2.0 into .solver/ and verifies its SHA-256
uv run solver.py            # self-check: solves a small flop spot
```

On Apple Silicon the macOS build runs under Rosetta (`softwareupdate --install-rosetta`).
`ranges.py` converts PioSOLVER-style `hand,weight` CSV ranges into TexasSolver range strings.

## How it works

| File | Role |
|---|---|
| `analyze.py` | CLI. Loads hands, replays them with PokerKit, aggregates stats, ICM, MTT ROI |
| `poker_tui.py` | Textual app showing the same results in tabs |
| `capture.py` | Renders TUI screens to `captures/*.svg` + `.txt` for review |
| `solver.py` | Runs TexasSolver as a subprocess and returns its strategy tree |
| `ranges.py` | Range CSV → solver range string |

Flow for `hands`: `load_hands` (PHH / PokerStars parser, with rake and ante fixes) → `reveal_shown_cards` (puts showdown cards back into the deal so all-in equity can be computed) → `analyze_hand` replays each action, records preflop stats, and computes pot equity at the first all-in → `Stats` per player → table.

## Known limitations

- All-in equity is Monte Carlo (about ±0.7% at 5000 samples).
- PHH files without `players` are grouped by seat (`p1`, `p2`, ...).
- Straddles: the largest blind is treated as the big blind.
- Mixing cash and tournament hands in one folder mixes bb units. Keep them in separate folders.
- Only PokerStars text format is parsed; other sites (GG, etc.) need a parser.
- ICM is exact enumeration, practical up to a final table (about 9 players).

## Development

```sh
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pytest
```

## License

MIT, see [LICENSE](LICENSE).

Dependencies: PokerKit (MIT), Textual (MIT). TexasSolver is AGPL-3.0; it is **not** included in this repository. `setup_solver.sh` downloads it separately and `solver.py` only runs it as an external program.
