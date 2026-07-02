# Second Opinion — Roadmap to World-Class

**Soul:** the one AI tool that's honest about AI — and *proves* it.

**North-star metric:** *trustworthy catch* — % of consequential errors caught, at a low
false-flag rate, with calibrated confidence. Everything below moves this number, in public.

**The bar (applies to every phase):** we are judged on the *subtle, confident, consequential*
errors — a fabricated citation, an off-by-a-decimal number, a stale fact stated with
certainty, a false causal claim in fluent prose. Catching "the Eiffel Tower is 450m" is a
toy. The hard cases are the only version anyone can't live without.

**What we will NOT build (the discipline):** no general "AI assistant," no writing help, no
research copilot, no chat. The moment Second Opinion does anything other than *tell you what
to trust*, the soul blurs and it becomes another me-too copilot. One job, undeniable.

---

## Phase 1 — Verify the verifier (THE defensible one)

> A verification tool no one can verify is worthless. This is the moat, and the artifact a
> lab hiring manager screenshots and forwards.

**Goal:** publish our own accuracy on a hard-case benchmark, with calibrated confidence.

**Milestones**
1. **Benchmark v0** — a hand-built set of hard cases across categories (numeric error,
   fabricated citation, stale fact, false causal, subtle false), plus true controls and
   opinions. *(Started — `benchmark/hard_cases.jsonl`.)*
2. **Eval harness** — runs the pipeline over the benchmark and computes catch rate,
   false-flag rate, opinion handling, per-category breakdown, and **calibration error (ECE)**.
   *(Started — `second_opinion/eval.py`.)*
3. **Real grounding** — wire real retrieval + an independent judge (Claude) so the numbers
   reflect a real verifier, not the mock. The harness already separates "what we measure"
   from "what runs," so this is a provider swap.
4. **Calibration fit** — replace the placeholder `_calibrate()` with a mapping fit against
   the benchmark, so "90% confident" means right 90% of the time. Report ECE before/after.
5. **Grow the set** — expand toward 200+ cases, sourced from real model outputs, versioned.
6. **The public scorecard** — a one-page report (and the essay: *"How I built an eval for
   whether an AI is lying"*). This is the portfolio artifact.

**Definition of done:** a published, reproducible scorecard — e.g. "*caught 88% of
consequential errors at a 4% false-flag rate; ECE 0.05*" — that anyone can re-run.

**Hiring payoff:** proves you are *the reliability/evals person*. Nobody else in this space
publishes calibrated accuracy. This is the screenshot that gets the interview.

---

## Phase 2 — Make it ambient (necessary for love)

> The CLI proves the engine. The product is where the answer already lives.

**Goal:** verification appears in place, in real time, with zero effort from the user.

**Milestones**
1. **Browser overlay** — sits on ChatGPT / Claude / Gemini; reads the answer on the page.
2. **Streaming verification** — claims light up as they resolve (the "fact-checking theater"):
   green stays quiet, the 1–2 flags draw the eye, each with its source.
3. **Frictionless capture** — no paste, no tab-switch, no account to start.
4. **Calm surface** — restraint-first UI; we acknowledge the 95% quietly and point at risk.

**Definition of done:** a person reading any AI answer sees trustworthy flags inline without
deciding to use a tool. Demo: a 20-second screen recording that needs no narration.

**Caveat (own it):** this leap is the more *copyable* one. It wins users; it doesn't win the
moat. Phase 1 is what's defensible. Don't let polish here starve the benchmark.

**Hiring payoff:** the lovable demo + real users (Show HN, AI communities) — proof you ship,
not just prototype.

---

## Phase 3 — Make it compound (what a lab would acquire)

> Every claim checked becomes a map of where AI lies.

**Goal:** a proprietary, growing dataset of model failure — a data flywheel no prompt can copy.

**Milestones**
1. **Capture loop** — log every claim, verdict, source, model-of-origin, and user correction
   (privacy-first; opt-in; no PII).
2. **The hallucination map** — aggregate into per-model, per-domain failure rates:
   *"GPT fabricates legal citations 3x more than Claude; both drift on post-2025 facts."*
3. **Living benchmark** — feed real captured failures back into Phase 1's benchmark so the
   eval set grows from the wild, not a whiteboard.
4. **Public report** — a recurring "State of AI Reliability" readout from real data.

**Definition of done:** a defensible dataset + a published map that improves the product
*and* the benchmark on a loop.

**Hiring payoff:** turns a portfolio project into an asset a company wants to *own* — and you
with it.

---

## Sequencing rule

Phase 1 before everything. It's the hardest, the most defensible, and the most *you*. Phases
2 and 3 multiply a proven core; they're worthless wrapped around an unproven one. Resist the
pull to build the shiny overlay first.
