# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning: [SemVer](https://semver.org/) (pre-1.0: interfaces may change).

## [0.1.0] - 2026-10-17

### Added
- `analyze.py` CLI: VPIP/PFR/3-bet, net bb, bb/100, all-in EV bb/100 from PHH and PokerStars hand histories
- PokerStars rake and ante handling; showdown cards used for all-in equity
- Skipped/duplicate hand reporting; parallel all-in equity
- ICM (Malmuth-Harville) and tournament ROI/ITM from CSV
- Textual TUI (`analyze.py tui`) and `capture.py` screen capture
- TexasSolver wrapper (`solver.py`), checksum-verified installer, range CSV loader

[0.1.0]: https://github.com/jawsbaek/poker-play-analyzer/releases/tag/v0.1.0
