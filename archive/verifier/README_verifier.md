# Second Opinion

**Paste any AI answer. It fact-checks it claim by claim, flags the one or two things that are wrong or unverifiable — each with the source — and never bluffs.**

The point: a model can't catch its own confident mistakes. Self-checking shares the same
blind spots, and a prompt can't fetch the real source to prove the model wrong. So Second
Opinion does the three things a prompt structurally can't:

1. **Retrieve external evidence** — go to real sources the model didn't generate.
2. **Judge independently** — a separate checker grades the claim, not the author grading its own homework.
3. **Calibrate** — confidence is mapped to honest verdicts, because models say "95% sure" on things that are 60% true.

## The experience

```
You:  paste an AI answer
                │
                ▼
   ┌────────────────────────────┐
   │ 1. Decompose into claims    │   "The Eiffel Tower is 450 m tall."
   │ 2. Retrieve evidence        │   → real sources per claim
   │ 3. Judge each independently │   → supported / contradicted / unverified
   │ 4. Calibrate the verdict    │   → honest confidence + the source
   └────────────────────────────┘
                │
                ▼
   Calm output: the 95% that's fine is marked quietly;
   the 1–2 things that need your eyes are flagged, with the source.
```

## Install

```bash
pip install second-opinion-ai
second-opinion "The Eiffel Tower is 450 metres tall and vaccines cause autism."
second-opinion-web       # a local web UI at http://localhost:8000
```

With no API key set, it runs in **mock mode** so you can try it instantly.

## Bring your own key (BYOK)

Real, grounded verification runs on **your** Anthropic key — the package ships none, and
nobody's usage touches anyone else's account. Set it as an env var or a local `.env`:

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # or put it in a .env file (gitignored)
second-opinion-doctor                    # confirm real mode works
```

Your key stays on your machine; the tool never sends it anywhere but Anthropic's API.

## Try it from source (no key needed)

```bash
python -m second_opinion examples/sample_answer.txt
```

Runs in mock mode — canned responses — so you can feel the claim-by-claim experience end to
end. Cloning the repo also gives you the full evaluation suite (below).

## Run it for real (one key)

Real verification is grounded: Claude uses its built-in **web search** to find external
evidence and then judges the claim. That means a single key covers both retrieval and
judgment — no separate search key needed.

```bash
export ANTHROPIC_API_KEY=sk-...
python -m second_opinion.doctor              # one-command check that real mode is live
python -m second_opinion "paste any AI answer here"
python -m second_opinion.eval                # real, grounded scorecard
```

Optional overrides: `SECOND_OPINION_MODEL` (default `claude-sonnet-5`),
`SECOND_OPINION_WEBSEARCH_TOOL` (default `web_search_20260209`).

If the key is missing, the judge falls back to mock and says so — the tool never pretends
to have verified something it didn't. If a real verification call fails, the verdict is
`UNVERIFIED`, never a guess.

## Calibration (the moat: honest confidence)

"90% confident" should mean right 90% of the time. Raw model confidence doesn't — models
are overconfident. So we **fit** a monotonic map (isotonic regression) from raw confidence
to empirical accuracy, on the `dev` split, and **prove it on the held-out `test` split**:

```bash
python -m second_opinion.fit_calibration   # fits dev, reports ECE before/after on test
```

It saves `benchmark/calibration.json`; the CLI and `eval` then load it automatically. With
no fitted map, confidence falls back to a conservative shrink-toward-0.5 (under-claim, never
bluff). A hard cap keeps it from ever asserting 100% or 0% certainty.

## Trust dimensions (beyond true/false)

An answer can betray you in more ways than a false fact. The full taxonomy is in
`TRUST_FAILURES.md`. A claim-type **router** classifies each decomposed claim and sends it to
a specialized checker — adding a dimension = add a route + a checker + a labeled benchmark slice.

Built so far:
- **Factual falsehood / unverifiable** — the grounded judge.
- **Fabricated citations** — source-*existence* check (fabricated → "no such source found";
  misattributed → flagged; real → supported; obscure → unverified, never falsely accused).
  `benchmark/citations.jsonl`.
- **Numeric / math** — recomputed *deterministically in Python* (more reliable than any LLM,
  and free): "recomputed 345,000, but the claim says 3,450,000." `benchmark/numeric.jsonl`.
- **Temporal / recency** — date-aware check for "current state of the world" claims, so stale
  training knowledge (a retired shuttle, a former monarch, "the UK is in the EU") is caught as
  *outdated*, not treated as timeless. `benchmark/temporal.jsonl`.

Next routes: contested-stated-as-settled, high-stakes-no-caveat.

## Factual vs non-factual handling

Most real answers mix advice/opinion with a few factual claims buried inside.

- **Pure opinion/advice** → the triage gate stays calm: *"Nothing to verify — this reads as
  opinion or advice."* It never manufactures an empty scorecard or grades the opinion.
- **Mixed** → claims are split atomically so an embedded factual error surfaces on its own
  while the surrounding advice is left alone. Measured by the mixed-answer eval:

```bash
python -m second_opinion.mixedeval      # catch the embedded error, don't flag the advice
```

## Evaluate everything — one command

You should never need to remember ten sub-commands. This runs the whole suite and prints a
single consolidated report card, then saves a shareable `REPORT.md`:

```bash
python -m second_opinion.report          # detection, calibration, honesty — one card
python -m second_opinion.report --full   # + baselines (ablation) and robustness
```

Everything below is an optional *deep dive* into one metric — the report card above is the
front door.

## Rigor: baselines & ablation

An accuracy number alone proves nothing. This decomposes where the accuracy comes from —
comparing self-critique (no search) vs our prompt (no search) vs the full grounded system,
with Wilson intervals and a McNemar significance test.

```bash
python -m second_opinion.ablation      # value of prompting vs value of retrieval, significance-tested
```

If retrieval adds a big, significant lift, the grounding thesis holds. If self-critique is
already high, the benchmark is too easy/memorised — the eval tells you to make it harder.

## Trust metrics (not just accuracy)

Accuracy alone lies for a trust tool. Three measurements make it an honesty eval:

```bash
python -m second_opinion.eval benchmark/hard_cases.jsonl   # now shows HARM-WEIGHTED catch
python -m second_opinion.honesty                           # bluff rate: does it assert on unknowable claims?
python -m second_opinion.robustness benchmark/hard_mode.jsonl --k 3 --limit 15  # flip rate across runs
```

- **Harm-weighted catch** — misses weighted by how much they'd hurt (a missed "vaccines cause
  autism" ≠ a missed Eiffel height). Flags high-severity misses even when the plain rate looks fine.
- **Self-hallucination (bluff) rate** — over genuinely *unknowable* claims, how often it confidently
  rules instead of honestly saying "unverified." A trust tool that bluffs is worse than none.
- **Run-to-run robustness** — verdict flip rate across K runs. A verdict that changes isn't dependable
  even when often right.

Together they let you claim it's right *and doesn't cry wolf, doesn't bluff, and is stable* —
a far stronger statement than any accuracy number.

## Web demo (the visual)

A local React UI — paste an answer, see the claims verified with sources. Same engine as
the CLI; zero build step (React via CDN), one command.

```bash
python -m second_opinion.web      # open http://localhost:8000
```

Flagged claims (false / unverifiable) surface first with their sources; verified and opinion
claims stay quiet below. Cached, so re-verifying an answer is instant — handy for recording.

## Scaling the benchmark (trustworthy labels at volume)

Hand-authoring doesn't scale, and trusting a generator's labels is a trap. So the generator
plants a *vetted* known-false sentence (and known-true ones) verbatim into a realistic
AI-style answer, and verifies each landed unchanged and un-negated — the label is certain
because we chose the claim, not because we trusted the model.

```bash
python -m second_opinion.generate --n 200 --out benchmark/answers_generated.jsonl
python -m second_opinion.answereval benchmark/answers_generated.jsonl
```

## Limitations & honesty

- Verification quality depends on what's findable on the web. Genuinely obscure claims come
  back **unverified**, not a guess — by design.
- The numbers here are on small, partly self-authored benchmarks. Treat them as *directional*
  until run at scale; the eval flags small samples and its own contamination risk itself.
- It checks **trust** (facts, sources, math, recency), not answer *quality*, completeness, or
  style — on purpose. It won't tell you if an answer is good, only what you can rely on.
- Real mode uses **your** Anthropic key and costs roughly a cent or two per answer; mock mode
  is free. The tool never bundles or transmits a key anywhere but Anthropic's API.
- Contested and opinion claims are left alone, not graded.

## Architecture

| Module          | Job                                                            |
|-----------------|---------------------------------------------------------------|
| `models.py`     | `Claim`, `Evidence`, `Verdict`, `Report` data types           |
| `providers.py`  | LLM + Search; mock + real; typed `JudgeError` for real failures |
| `pipeline.py`   | decompose → retrieve → judge → calibrate → assemble report     |
| `calibration.py`| fitted isotonic confidence map + ECE; honest fallback + cap    |
| `cli.py`        | the terminal experience (claim-by-claim, restraint-first)     |
| `doctor.py`     | real-mode self-check: connection health vs answer accuracy    |
| `eval.py`       | verifier scorecard (catch rate, false-flag, ECE) over the benchmark |
| `mixedeval.py`  | embedded-error eval over whole mixed answers                  |

## v1 scope (deliberately ruthless)

- Text in, annotated verdicts out. One job, done honestly.
- No browser extension, no accounts, no dashboard yet — those come after the core is trustworthy.

## Status

Early scaffold. The core pipeline runs in mock mode today. Next: wire real retrieval and a
calibration set so the verdicts are measured, not asserted.
