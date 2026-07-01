# Second Opinion — Report Card
*2026-07-01 · mock*

| Metric | Value | 95% CI | n |
|---|---|---|---|
| Catch rate | 18% | 10%–29% | 61 |
| Harm-weighted catch | 19% | — | 61 |
| False-flag (cry-wolf) | 0% | 0%–12% | 27 |
| Calibration (ECE) | 0.34 | — | — |
| Bluff rate (self-hallucination) | 0% | 0%–24% | 12 |

**By dimension (catch):** citation 0/15 · numeric 6/6 · standard 5/30 · temporal 0/10


## Baselines & robustness

```
Second Opinion — Baselines & Ablation
MOCK MODE — all three modes use the canned judge, so they'll match. Set ANTHROPIC_API_KEY for the real comparison.

  mode                                              catch        false-flag           overall
  self-critique (no search, naive)           12% (5%-26%)       0% (0%-24%)     19% (11%-32%)
  no-retrieval (our prompt, no search)       12% (5%-26%)       0% (0%-24%)     19% (11%-32%)
  grounded (prompt + web search)             12% (5%-26%)       0% (0%-24%)     19% (11%-32%)

Where the accuracy comes from
  value of careful prompting  (no-retrieval − self-critique):  +0 pts
  value of RETRIEVAL          (grounded − no-retrieval):       +0 pts
  total system lift           (grounded − self-critique):      +0 pts
  McNemar grounded vs self-critique: 0 gained, 0 lost, p=1.0000 — not significant (need more data).

Reading: if 'value of retrieval' is large, grounding does the work (the thesis holds). If self-critique is already high, the benchmark is too easy / memorised — make it harder.
Second Opinion — Run-to-Run Robustness (k=3)
MOCK MODE — the canned judge is deterministic, so flips are always 0. Real mode is the test.

  Flip rate: 0% (0/15)  95% CI 0–20%  [stable]
  (fraction of claims whose verdict changed across 3 runs — lower is more dependable)
```
