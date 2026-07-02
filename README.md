# SwitchProof

**Prove you can move a task from an expensive frontier model to a cheap open model without
losing quality — and put a dollar figure on the savings.**

Teams know they're overpaying: token cost is now a real slice of AI-product burn, and
open-weight models (Llama, Qwen, Mistral) are 10–100× cheaper and have closed much of the
gap on common tasks. But nobody can tell whether the cheaper model is *good enough on their
actual traffic*, so they stall and keep paying. SwitchProof answers that question with
evidence.

The wedge is **neutrality**: the model hosts, fine-tuners, and routers can't credibly grade
their own homework. An independent proof-and-guard layer can.

---

## How it works (Case 1 — you already run a frontier model)

The frontier model's own output on your real queries is your **free reference**. SwitchProof:

1. Runs the cheap **open model** on the same inputs.
2. Measures **agreement** with the frontier model — "would users notice a change?" — with a
   **Wilson 95% confidence interval**, not a bare number.
3. Breaks it down **per slice** (here, per intent). Slices where the open model drifts get
   **kept on frontier**; the safe majority **switches to open**.
4. Prices all of it: real measured token counts × your price assumptions × your monthly
   volume, across three strategies — today (all frontier), naive (all open), and **hybrid**.
5. Renders a **verdict**: SAFE_ALL / SAFE_HYBRID / NOT_YET, based on the *lower* confidence
   bound, not luck.

Demo task: **Banking77** — 77-way customer-support intent classification, a real
high-volume, well-defined workload where switching actually pays.

---

## Quickstart (no keys needed)

```bash
# 1. Generate a report from the bundled demo data (mock models — offline, free)
python -m switchproof --mock

# 2. See it in the app
cd web
npm install
npm run dev            # open the printed localhost URL
```

The engine writes `web/public/report.json` (what the app reads) and `SWITCH_REPORT.md`
(a shareable text summary). The React app is the product surface: a verdict hero, a **live
savings calculator** (drag monthly volume and edit prices — the dollars recompute in real
time), a per-intent routing table with confidence intervals, a cost chart, and a browsable
sample of the actual model decisions.

## Run it for real

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # the frontier model (reference)
export GROQ_API_KEY=gsk_...              # the open model (candidate), via Groq

python -m switchproof.doctor             # 2-sec pre-flight: one live call per model
python -m switchproof --prepare 1000     # download + stratify a real Banking77 sample
python -m switchproof                     # evaluate for real; caches every call
cd web && npm run dev
```

Missing a key → that model runs in mock mode and the report says so. It never bluffs.
Every real prediction is cached by `(model, query)`, so an interrupted run resumes for free
and bumping the sample from 1,000 → 2,000 only pays for the new rows.

### Useful flags & knobs

| Flag / env | Effect |
|---|---|
| `--mock` | Force both models to mock (offline, deterministic, free) |
| `--prepare N` | Download + stratify an N-row Banking77 sample |
| `--limit N` | Evaluate only the first N rows |
| `--monthly-calls N` | Set the volume the savings are scaled to |
| `SP_FRONTIER_PRICE_IN/OUT`, `SP_OPEN_PRICE_IN/OUT` | Price assumptions ($/1M tokens) |
| `SP_FRONTIER_MODEL`, `SP_OPEN_MODEL` | Which models to compare |

Pricing and volume are **assumptions you set** — they scale the dollars, never the quality
verdict.

---

## What's here

```
switchproof/            the engine (self-contained Python, no heavy deps)
  data.py               Banking77 loader + stratified sampler (+ bundled mock fixture)
  runners.py            frontier (Anthropic) + open (Groq) classifiers, cached; mock mode
  evaluate.py           agreement, per-intent slices, Wilson CIs, cost, routing, verdict
  run.py / __main__.py  CLI: writes report.json + SWITCH_REPORT.md, prints a scorecard
  stats.py, config.py, cache.py   vendored helpers (Wilson, .env + pricing, durable cache)
web/                    the React app (Vite + Recharts) — the product surface
archive/verifier/       the earlier "Second Opinion" answer-verification project, kept for reference
```

## Why the numbers are trustworthy

- **Reference-based**, so "quality" means "matches what you ship today," not a synthetic score.
- **Confidence intervals** on every rate — a slice with too few rows is flagged `low-n`, and
  the switch verdict uses the lower bound.
- **Deterministic cost** from measured tokens; the only soft inputs (price, volume) are yours
  to set and only move the dollars.
- **Honest mode reporting** — mock vs live is stated everywhere; a missing key never silently
  degrades into a fake result.

---

_MIT licensed. The demo runs entirely offline; real mode uses your own API keys and never
transmits them anywhere but the model providers._
