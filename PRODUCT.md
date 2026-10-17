# hand-review

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Existing Python 3.12+ CLI, PokerKit and Textual. The requested replay extends this project with a standalone local HTML report; no web service or frontend dependency is needed.

## Users

The player reviewing their own captured Pokerist hands after a session. The interface and explanations are in Korean, matching the existing CLI.

## Product Purpose

Replay captured hands like a game and distinguish questionable decisions from good decisions, with the evidence available at the time of each action.

## Operating Context

Input is a local Pokerist JSONL export. Open a generated report in a browser, step through streets and actions, pause at hero decisions, and filter the review list by classification. An optional practice mode hides the actual decision until the user chooses an action.

## Capabilities and Constraints

- Source project: jawsbaek/hand-review v0.3.0. Preserve the existing commands.
- Real hand exports and generated reports stay local and must not be committed or transmitted.
- Suit 4 has an unknown glyph: preserve `/s4` rather than claiming it is a spade.
- Stack-boundary net may include top-ups. Pot contribution events are not payout records.
- Do not infer decision quality from the result or from future board/opponent cards.
- Solver EV is optional and limited to supported heads-up turn/river states with explicit ranges. Clearly distinguish heuristic review candidates and unavailable analysis.

## Evidence on Hand

Existing CLI/TUI, solver wrapper, tests and synthetic sample histories. Local exports are available for validation; their contents are excluded from the repository.

## Product Principles

- Keep the original observation intact; flag missing information.
- Make every classification explainable and conservative.
- Separate action quality, model assumptions and financial result.
- Work offline after report generation.
