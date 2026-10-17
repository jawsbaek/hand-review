# hand-review

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Existing Python 3.12+ CLI, PokerKit and Textual. The requested replay extends this project with a standalone local HTML report; no web service or frontend dependency is needed.

## Users

The player reviewing their own captured Pokerist hands after a session. The interface and explanations are in Korean, matching the existing CLI.

## Product Purpose

Replay captured hands like a game and compare the player's recorded action/sizing with solver candidates and practical coaching recommendations using the evidence available at the time of each decision. Show a representative recommendation first, with frequencies, EVs, assumptions and range editing in the details.

## Operating Context

Input is a local Pokerist JSONL export. Open a generated report in a browser, step through streets and actions, pause at hero decisions, and filter the review list by classification. An optional practice mode hides the actual decision until the user chooses an action.

## Capabilities and Constraints

- Source project: jawsbaek/hand-review v0.3.0. Preserve the existing commands.
- Real hand exports and generated reports stay local and must not be committed or transmitted.
- Suit 4 has an unknown glyph: preserve `/s4` rather than claiming it is a spade.
- Stack-boundary net may include top-ups. Pot contribution events are not payout records.
- Do not infer decision quality from the result or from future board/opponent cards.
- Solver EV is optional and limited to supported heads-up postflop states and a finite sizing tree. Default ranges are visible, editable modelling priors; explicit overrides remain available.
- Cover preflop and multiway decisions with separately labelled response/checkdown model estimates; disclose missing information and withhold unsupported recommendations.
- Practical coaching retains a baseline when personal evidence is inadequate. Hypothetical opponent-response scenarios must be labelled as assumptions, never measured professional or individual behavior.
- Saved reports work offline; an optional loopback-only workbench recalculates edited ranges without external services.

## Evidence on Hand

Existing CLI/TUI, solver wrapper, tests and synthetic sample histories. Local exports are available for validation; their contents are excluded from the repository.

## Product Principles

- Keep the original observation intact; flag missing information.
- Make every classification explainable and conservative.
- Separate action quality, model assumptions and financial result.
- Work offline after report generation.
