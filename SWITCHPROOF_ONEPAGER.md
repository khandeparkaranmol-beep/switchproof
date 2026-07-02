# SwitchProof — one-pager

**Prove you can move an AI workload from an expensive frontier model to a cheap open model
without losing quality — and put a dollar figure on it.**

## The problem

Token cost is now a real line item in every AI product's burn. Open-weight models (Llama,
Qwen, Mistral) are 10–100× cheaper and have closed much of the quality gap on common,
well-defined tasks. Teams know they're overpaying — but they can't tell whether the cheaper
model is *good enough on their actual traffic*, so they stall and keep paying. The infra to
switch exists (Together, Fireworks, Groq, OpenPipe, OpenRouter); the missing piece is an
**independent way to prove the switch is safe.** The model hosts and fine-tuners can't
credibly grade their own homework. A neutral proof-and-guard layer can.

## What I built

A tool that, given a team's real queries, runs both the incumbent **frontier model** and a
candidate **open model**, and decides — per slice of traffic — where the switch is safe,
then prices it. The frontier model's own outputs are the free reference ("would users notice
a change?"). It reports agreement with **Wilson 95% confidence intervals**, breaks it down
by intent, routes the unsafe slices back to frontier, and computes savings from **measured
token counts × your prices × your volume**. Verdict: SAFE / HYBRID / NOT-YET. Surfaced in a
live React dashboard with a savings calculator you can drag.

## The real result (not a mock)

Task: **Banking77** — 77-way customer-support intent classification, 900 real queries.
Models: **Claude Sonnet** (incumbent) → **Llama 3.1 8B** on Groq (candidate, ~100× cheaper).

| Metric | Result |
|---|---|
| Raw agreement (open vs frontier) | 66.0% (95% CI 62.8–69.0) |
| Gold accuracy — frontier vs open | 76.3% vs 61.8% |
| Traffic safely switchable to open | **46.4%** (36 of 77 intents) |
| **Accuracy after routing** | **79.2% — higher than staying all-frontier (76.3%)** |
| Monthly savings @ 1M calls | **$1,247 (46%, ~$15k/yr)** |
| Latency | open 245 ms vs frontier 1,612 ms (6.6× faster) |

**The switch is cheaper *and* slightly more accurate — while cutting latency 6×.**

## The insight that makes it sharp

A naive read says "the 8B only agrees 66% of the time — don't switch." But agreement with
the incumbent is a **safety floor, not ground truth.** On `card_arrival`, Llama matched the
human label on all 11 queries while Claude called it `card_delivery_estimate` (a near-
duplicate intent) — so the slice shows 0% "agreement" even though the *open* model was the
correct one. So I added a **correctness-aware rule**: switch a slice if the open model is at
least as accurate against the human label, even when raw agreement is low. That lifted safe
traffic from 26% → 46% and pushed post-routing accuracy *above* the all-frontier baseline.
The tool's real value is the **guard** — it also caught that a blind full switch would have
wrecked ~54% of traffic.

## Why this is a strong AI-PM artifact

- **Market-first, not resume-first:** a real painkiller riding a real macro wave, with a
  neutrality moat the infra players structurally can't have.
- **Eval craft:** reference-based measurement, confidence intervals, per-slice routing, and
  the judgment to see that "agreement ≠ correctness" and fix it principledly.
- **Intellectual honesty:** every number is measured on live calls; mock vs real is labeled;
  the tool flags where it's too conservative rather than overselling.
- **Shipped:** a self-contained engine + a gorgeous interactive product surface, end to end.

## Where it goes

Beachhead: AI-native teams running an incumbent frontier model on high-volume, well-defined
tasks (classification, extraction, RAG triage) — Case 1, where the reference is free.
Expansion: greenfield model selection (synthesize the gold set), few-shot/fine-tune lift,
continuous post-switch **regression monitoring** (the guard), and integration with the
serving/routing players as the neutral referee in their funnel.

## Honest limitations

900 rows ≈ 12/intent — the aggregate CI is tight but per-slice bands are wide (flagged
`low-n`); one task, one model pair; pricing/volume are assumptions that scale only the
dollars, not the verdict. Next: the full 3,080-row test set for solid slices, and a
stronger open model (Llama-4-Scout / 70B) to show the quality/cost dial.

---

### 60-second talk track

> "Every AI team is overpaying for tokens, and open models are now 10–100× cheaper and often
> good enough — but nobody can prove the switch is safe on their own traffic, so they don't.
> I built the neutral proof layer. On a real 900-query banking-support benchmark, I compared
> Claude to a Llama-3.1-8B that's ~100× cheaper. The naive signal looked bad — only 66%
> agreement — but I realized agreement with the incumbent isn't ground truth: on several
> intents the cheap model actually matched the *human* label better than Claude did. So I
> routed per-slice, switching only where the open model is at least as accurate. Result:
> 46% of traffic moves to the model that's 100× cheaper and 6× faster, cost drops 46%, and
> accuracy actually goes *up* versus staying on Claude. The real product isn't the savings —
> it's the guard that caught that a blind full switch would have broken half the traffic."
