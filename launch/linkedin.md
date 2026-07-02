A language model that agreed with Claude only 66% of the time turned out to be the better choice.

Here's the counterintuitive reason.

Every AI team is quietly overpaying for tokens. Open models are now 10–100x cheaper and often good enough — but nobody can prove a switch is safe on their own traffic, so they keep paying.

So I built a tool that proves it. Feed it your real queries; it runs your current frontier model and a cheap open model side by side and decides, per slice of traffic, where you can switch without losing quality — with a dollar figure attached.

I tested it on 900 real banking-support queries (77-way intent classification): Claude Sonnet vs a Llama-3.1-8B that costs ~100x less.

The naive signal looked bad — the two models agreed only 66% of the time. Case closed, don't switch?

Not quite. Agreement with your current model isn't the same as being right. On several intents the cheap model actually matched the human label better than Claude did — Claude was the inconsistent one, splitting near-duplicate categories.

So instead of trusting raw agreement, I routed per slice: switch only where the open model is at least as accurate.

→ 46% of traffic safely moved to the model that's ~100x cheaper and 6x faster
→ Accuracy went UP — 79% after routing vs 76% staying all-Claude
→ ~$15K/year saved at 1M calls a month
→ And the real win: it flagged the other 54% where switching WOULD have hurt

The product was never really about the savings. It's the guard — the thing that stops a blind cost-cut from quietly breaking half your traffic.

Built solo, measured on live model calls. Every number here is real, with confidence intervals, not a vibe.

I put the full interactive breakdown online — the verdict, every intent, the confidence intervals, and a savings calculator you can drag:
→ [PASTE YOUR LIVE LINK HERE]

If you run LLMs in production: how are you deciding today whether a cheaper model is safe to switch to — gut feel, or something you can actually measure?

---

## POSTING NOTES

**Platform:** LinkedIn only. Skip HN until the repo is public and open-source — then a Show HN with the code lands well.

**Timing:** Tuesday–Thursday, 8–10am ET. Don't edit after posting (LinkedIn deprioritizes edited posts) — get it right first.

**Video (do this):** Attach the 20–40s screen recording of the app — verdict → drag the savings slider → filter to "keep on frontier" (the guard) → the card_arrival sample. Native upload, NOT a YouTube/Loom link (native video gets 3–5x reach and autoplays).

**Hashtags:** none in the post body. Put 2–3 in the FIRST COMMENT: #AI #MachineLearning #ProductManagement (or #LLMOps #AIProduct).

**First comment (post it yourself within 1 min):**
"Interactive results here → [YOUR LIVE LINK]. Technical detail for the curious: 'agreement' is measured against the frontier model as a live reference (Case 1 — you already run a frontier model), reported with Wilson 95% confidence intervals, then overridden per-slice by gold accuracy where labels exist. Happy to go deeper on the eval design — ask away. #AI #LLMOps #ProductManagement"

**Deploying the results site (do this before posting):** the app is a static build with no secrets in it — safe to host.
  1. On your laptop:  cd web && npm install && npm run build   (produces web/dist)
  2. Easiest + safest: go to https://app.netlify.com/drop and drag the web/dist folder in → you get a URL like https://your-name.netlify.app (rename it in site settings for a cleaner link). No repo push, no key risk.
  3. Alternatives: Vercel (`npm i -g vercel && cd web && vercel`) or GitHub Pages (only if you've pushed the repo — first confirm `git status` shows NO .env, and rotate the key).
  Put the final URL in the post body and the first comment (both currently say [PASTE YOUR LIVE LINK HERE]).
  Best media = the native demo video; the link drives the click-through. LinkedIn shows the video as the media and the link as text.

**First 60 minutes matter most** (replies in the first hour = ~2.4x reach). Reply to every comment in the first hour, then every 2–3 hours for 24h. Ask follow-up questions back to keep threads alive (comments are weighted ~2x likes).

**Likely comments + reply seeds:**
- "Isn't 66% agreement just a bad model?" → "That was my first read too — but agreement ≠ correctness. On card_arrival the 8B matched the human label 11/11 while Claude picked a near-duplicate intent. The incumbent isn't ground truth; that's the whole point."
- "Why not just use a router like OpenRouter/Not Diamond?" → "Those route; they don't prove. This is the measurement layer that tells you WHICH slices are safe to route in the first place — and it's neutral, so it's not grading its own homework."
- "What about tasks with no labels?" → "Then the frontier model's output is your reference (still works), and you add a synthesized gold set for the slices you care about. That's the Case 2 expansion."

**Subtle job-search signal (optional):** if you want it, add one line above the closing question: "This is the kind of problem I love as an AI PM — turning a fuzzy 'is it good enough?' into something measurable." Only if it feels natural; the work should carry it.

**Follow-up:** if it gets traction, post a 2-days-later deep dive on the "agreement ≠ ground truth" finding alone — that idea can stand as its own post.
