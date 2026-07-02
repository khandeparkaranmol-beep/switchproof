LINKEDIN POST — copy/paste ready (plain text)
===============================================

My AI fact-checker scored 100% on my own test set.

That's exactly when I stopped trusting it.

AI assistants sound just as confident when they're wrong as when they're right — and the dangerous part is you can't tell which sentences to trust. Asking the model to check itself doesn't help; it has the same blind spots that produced the error.

So I built Second Opinion. You paste any AI answer, it breaks it into individual claims, checks each one against live web sources, and flags what's false or unverifiable — with the source. If it can't verify something, it says so. It never bluffs.

On my first benchmark it caught 100% of the errors. Suspicious of my own number, I built a "hard mode" designed to break it: surprising-but-true facts (octopuses really do have three hearts) and plausible fabrications with no tidy myth-buster page (a "Boeing 797" that doesn't exist).

It broke — in the most useful way. It stayed strong at catching real lies, but it started crying wolf on true-but-surprising claims. So I taught it to answer "unverified" when the evidence is thin, instead of guessing "false."

Where it landed, on 150 adversarial AI answers:
→ 180/180 planted errors caught (95% CI 98–100%)
→ 0 false alarms across 100 true claims
→ confidence calibrated so "90% sure" means right ~90% of the time

The part I'm proudest of isn't the accuracy. It's that the tool refuses to bluff — and that I built an eval whose whole job is to catch it bluffing.

What's the most confidently-wrong thing an AI has ever told you — and did you catch it in time?


---

POSTING NOTES
=============

DEMO ASSET (do this first — it's the highest-leverage part):
- Record a 15–30s screen capture of ONE live catch. Suggested: an answer containing the
  fake "Boeing 797" or "vaccines cause autism", run through `python -m second_opinion "..."`,
  so viewers watch it flag the false claim WITH a real source link.
- Also grab a still of the eval scorecard (180/180, 0 false-flags, the CI).
- Upload the video NATIVELY to LinkedIn (not a YouTube link) — 3–5x more reach.

LINK:
- Strongest with a GitHub link. If the repo isn't public yet, either push it public first,
  or post as build-in-public and add "Repo + write-up coming — DM me if you want early access"
  in the first comment. A post with a real artifact link outperforms one without.

TIMING:
- Tuesday–Thursday, 8–10am ET.

HASHTAGS:
- None in the post body. Put 2–3 in the FIRST COMMENT: #AI #MachineLearning #ProductManagement

FIRST COMMENT (post within 1 min of publishing):
- Re-link the demo video/repo + one line: "Happy to go deeper on how the calibration and the
  'catch the grader' eval work — ask away."

REPLY CADENCE:
- Reply to every comment in the first 60 minutes (first-hour replies ≈ 2.4x reach), then
  every few hours for 24h. Ask follow-up questions to keep threads alive (comments weigh 2x likes).

FOLLOW-UP:
- If it gets traction, post a deeper technical write-up 2 days later: "How I built an eval to
  check whether an AI is lying" — the essay is the artifact that travels furthest for hiring.

AVOID:
- "Excited to announce", superlatives ("game-changing"), or engagement bait ("comment YES") —
  all penalized and off-brand for an honesty-first project.
