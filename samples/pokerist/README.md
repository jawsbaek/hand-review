# Synthetic Pokerist replay examples

Every record in `demo.jsonl` is hand-authored synthetic data. Player names,
timestamps, stacks, actions and results do not come from a real session.

The four hands demonstrate a flop nut-straight raise, a weak preflop call
facing a large raise, a disciplined fold, and a heads-up checked turn/river
that can be compared using the example ranges in the root README.

```sh
uv run hand-review replay samples/pokerist/demo.jsonl -o reports/demo.html
```

Keep personal exports outside `samples/`; generated HTML includes private hand
data and belongs in the ignored `reports/` directory.
