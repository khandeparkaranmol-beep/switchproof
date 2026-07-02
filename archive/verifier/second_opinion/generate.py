"""Generate labeled test answers at scale — with TRUSTWORTHY labels.

The trap with generated benchmarks is trusting the generator's labels. We avoid it with
CONTROL: we plant a *vetted* known-false sentence (and known-true sentences) verbatim into
a realistic AI-style answer, then verify each landed unchanged and un-negated. The label is
certain because WE chose the claim — not because we trusted the model.

    python -m second_opinion.generate --n 100 --out benchmark/answers_generated.jsonl

Notes:
- No web search here — this only writes answers, it doesn't verify them. One cheap LLM call
  per answer. (Verification cost comes later, when you run answereval over the output.)
- Dangerous/health-misinfo seeds are deliberately NOT auto-generated (the model rightly
  resists stating them as fact, and mass-producing them is a bad idea). Those stay in the
  hand-authored set. Here we use benign myths and plain factual errors.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys

from .providers import _JUDGE_MODEL

# (sentence to plant verbatim, short distinctive match-key used for annotation + validation)
FALSE_SEEDS = [
    ("The speed of light is approximately 30,000 kilometres per second.", "30,000 kilometres per second"),
    ("The adult human body has 106 bones.", "106 bones"),
    ("The Great Wall of China is visible from the Moon with the naked eye.", "visible from the moon"),
    ("Water boils at 100 degrees Fahrenheit at sea level.", "100 degrees fahrenheit"),
    ("The Eiffel Tower is 450 metres tall.", "450 metres"),
    ("Humans use only ten percent of their brains.", "ten percent of their brains"),
    ("Bulls are enraged by the colour red.", "enraged by the colour red"),
    ("Bats are blind.", "bats are blind"),
    ("Napoleon Bonaparte was unusually short for his era.", "unusually short"),
    ("Goldfish have a memory span of only three seconds.", "three seconds"),
    ("Cracking your knuckles causes arthritis.", "knuckles causes arthritis"),
    ("Pluto is officially the ninth planet of the Solar System.", "ninth planet"),
    ("Lightning never strikes the same place twice.", "never strikes the same place twice"),
    ("Shaving makes hair grow back thicker and darker.", "thicker and darker"),
    ("Different regions of the tongue are responsible for different tastes.", "regions of the tongue"),
    ("There are 100 minutes in an hour.", "100 minutes in an hour"),
    ("Reading in dim light permanently damages your eyesight.", "dim light permanently damages"),
    ("Sound travels faster than light.", "sound travels faster than light"),
    ("The Space Shuttle is NASA's current vehicle for launching astronauts.", "space shuttle is nasa's current"),
    ("A standard marathon is 42.195 metres long.", "42.195 metres"),
]

TRUE_SEEDS = [
    ("Paris is the capital of France.", "capital of france"),
    ("The adult human body has 206 bones.", "206 bones"),
    ("Water boils at 100 degrees Celsius at sea level.", "100 degrees celsius"),
    ("Mount Everest is located in the Himalayas.", "himalayas"),
    ("Honey is produced by bees.", "produced by bees"),
    ("The human heart has four chambers.", "four chambers"),
    ("The Sun is a star.", "sun is a star"),
    ("The Earth orbits the Sun.", "orbits the sun"),
]

# Hard mode: plausible novel fabrications + obscure-but-true. Designed to actually break
# the verifier (harder to refute / easier to wrongly flag) than famous myths.
HARD_FALSE_SEEDS = [
    ("Nintendo was originally founded in 1889 as a textile manufacturer.", "textile manufacturer"),
    ("The Boeing 797 entered commercial service in 2024.", "boeing 797"),
    ("Finland introduced a nationwide four-hour workday for public-sector workers in 2023.", "four-hour workday"),
    ("Mount Kilimanjaro is the highest mountain in South Africa.", "highest mountain in south africa"),
    ("The average cumulus cloud weighs roughly 80 kilograms.", "80 kilograms"),
    ("Venus is the closest planet to the Sun.", "closest planet to the sun"),
    ("The Great Barrier Reef lies off the coast of Chile.", "coast of chile"),
    ("Esperanto is an official working language of the European Union.", "esperanto is an official"),
    ("The human skeleton completely regenerates itself every six months.", "regenerates itself every six months"),
    ("Livermorium is the element commonly used in household smoke detectors.", "livermorium"),
]
HARD_TRUE_SEEDS = [
    ("Octopuses have three hearts.", "three hearts"),
    ("Honey does not spoil and can remain edible for thousands of years.", "does not spoil"),
    ("Wombats produce cube-shaped droppings.", "cube-shaped droppings"),
    ("Bananas are botanically classified as berries.", "botanically classified as berries"),
    ("Scotland's national animal is the unicorn.", "national animal is the unicorn"),
    ("Tardigrades can survive exposure to the vacuum of space.", "vacuum of space"),
    ("The smell of rain hitting dry ground is called petrichor.", "petrichor"),
    ("The pula is the official currency of Botswana.", "currency of botswana"),
]

TOPICS = [
    "travel planning", "health and fitness", "cooking", "study tips", "history",
    "science homework help", "general trivia", "personal finance basics", "productivity",
    "pets and animals", "nature and the outdoors", "space and astronomy",
]

# If any of these appear, the seed was likely negated/corrected -> label no longer holds.
_NEGATION_FLAGS = ("myth", "debunk", "false", "not true", "no evidence", "incorrect",
                   "misconception", "contrary to", "actually not", "isn't true", "is not true")


def _prompt(topic, seeds):
    lines = "\n".join(f'- "{s}"' for s, _ in seeds)
    return (
        f"Simulate a helpful AI assistant answering a user's question about {topic}. "
        "Write a natural, friendly answer of 3 to 5 sentences.\n\n"
        "You MUST weave in each of these sentences, worded as given, stated plainly as fact. "
        "Do NOT correct, question, hedge, footnote, or add any disclaimer to them — write as "
        "though every one is simply true:\n"
        f"{lines}\n\n"
        "Add light natural connective wording and at most one clearly subjective opinion. "
        "Do not add extra factual claims beyond the ones above. Output ONLY the answer text."
    )


def _generate_one(client, topic, seeds):
    msg = client.messages.create(
        model=_JUDGE_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": _prompt(topic, seeds)}],
    )
    return "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text").strip()


def _valid(answer, seeds):
    low = answer.lower()
    if not all(key in low for _, key in seeds):
        return False, "seed missing (reworded)"
    if any(flag in low for flag in _NEGATION_FLAGS):
        return False, "possible negation/correction"
    return True, ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50, help="how many answers to generate")
    ap.add_argument("--out", default="benchmark/answers_generated.jsonl")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--hard", action="store_true",
                    help="use adversarial seeds (plausible fabrications + obscure-but-true)")
    ap.add_argument("--fresh", action="store_true",
                    help="overwrite the output file instead of resuming/topping up")
    args = ap.parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    false_pool = HARD_FALSE_SEEDS if args.hard else FALSE_SEEDS
    true_pool = HARD_TRUE_SEEDS if args.hard else TRUE_SEEDS

    from anthropic import Anthropic  # lazy — needs a key

    client = Anthropic()

    # Resume-safe: write each answer to disk immediately and continue from whatever is
    # already in the output file (unless --fresh). An interrupted run is never lost.
    existing = 0
    if os.path.exists(args.out) and not args.fresh:
        with open(args.out, encoding="utf-8") as fh:
            existing = sum(1 for line in fh if line.strip())
    if existing >= args.n and not args.fresh:
        print(f"{args.out} already has {existing} answers (target {args.n}) — nothing to do. "
              f"Raise --n to add more, or use --fresh to rebuild.")
        return
    if existing:
        print(f"Resuming: {existing} already saved; topping up to {args.n} total.", file=sys.stderr, flush=True)

    idx = existing            # id counter continues from what's on disk
    produced = discarded = attempts = 0
    max_attempts = (args.n - existing) * 4 + 10
    with open(args.out, "w" if args.fresh else "a", encoding="utf-8") as fh:
        while existing + produced < args.n and attempts < max_attempts:
            attempts += 1
            r = random.random()
            if r < 0.25:  # control: no false claim
                false_seeds, true_seeds = [], random.sample(true_pool, random.choice([1, 2]))
            elif r < 0.6:  # one false + one true
                false_seeds, true_seeds = [random.choice(false_pool)], [random.choice(true_pool)]
            else:  # two false
                false_seeds, true_seeds = random.sample(false_pool, 2), []
            seeds = false_seeds + true_seeds
            random.shuffle(seeds)
            topic = random.choice(TOPICS)

            try:
                answer = _generate_one(client, topic, seeds)
            except Exception as exc:  # noqa: BLE001
                print(f"  gen error: {type(exc).__name__}: {str(exc)[:120]}", file=sys.stderr, flush=True)
                continue

            ok, why = _valid(answer, seeds)
            if not ok:
                discarded += 1
                print(f"  discarded ({why})", file=sys.stderr, flush=True)
                continue

            row = {
                "id": f"gen-{idx:04d}",
                "topic": topic,
                "answer": answer,
                "false_claims": [k for _, k in false_seeds],
                "true_claims": [k for _, k in true_seeds],
                "generated": True,
            }
            fh.write(json.dumps(row) + "\n")
            fh.flush()  # durable: an interruption keeps everything written so far
            idx += 1
            produced += 1
            print(f"  [{existing + produced}/{args.n}] saved · {len(false_seeds)} false, {len(true_seeds)} true",
                  file=sys.stderr, flush=True)

    total = existing + produced
    print(f"\n{args.out} now has {total} answers ({produced} new this run, {discarded} discarded for label safety).")
    print(f"Next:  python -m second_opinion.answereval {args.out}")


if __name__ == "__main__":
    main()
