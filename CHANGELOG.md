# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning: [SemVer](https://semver.org/) (pre-1.0: interfaces may change).

## [Unreleased]

### Added
- Optional turn/river decision EV scoring (`hands --oop-range ... --ip-range ...`): EV loss from real per-action EVs via `ev_rust/` (postflop-solver, AGPL-3.0-or-later, built separately). Flop is not scored.
- `F2R` column: postflop fold-to-raise rate per player (raises only, not bets).
- `exploit.py` / `best_response.py`: GTO/exploit blending bounded by an EV-loss budget (library only).

## [0.2.0] - 2026-10-17

### Changed
- Renamed project to **hand-review** (was poker-play-analyzer). GitHub redirects the old URL.
- Installable package with a `hand-review` command (`uvx --from git+https://github.com/jawsbaek/hand-review hand-review ...`). `uv run analyze.py ...` becomes `uv run hand-review ...`.
- Code moved to `src/hand_review/` (`poker_tui.py` → `tui.py`), tests to `tests/`, `capture.py` to `scripts/`.
- Solver is installed to `~/.cache/hand-review/solver` (override with `HAND_REVIEW_SOLVER_DIR`) instead of `.solver/` in the repo.

## [0.1.0] - 2026-10-17

### Added
- `analyze.py` CLI: VPIP/PFR/3-bet, net bb, bb/100, all-in EV bb/100 from PHH and PokerStars hand histories
- PokerStars rake and ante handling; showdown cards used for all-in equity
- Skipped/duplicate hand reporting; parallel all-in equity
- ICM (Malmuth-Harville) and tournament ROI/ITM from CSV
- Textual TUI (`analyze.py tui`) and `capture.py` screen capture
- TexasSolver wrapper (`solver.py`), checksum-verified installer, range CSV loader

[0.2.0]: https://github.com/jawsbaek/hand-review/releases/tag/v0.2.0
[0.1.0]: https://github.com/jawsbaek/hand-review/releases/tag/v0.1.0
