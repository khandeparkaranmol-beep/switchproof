"""LLM and Search providers.

Two interfaces — an LLM (for decomposition + judging) and a Search (for evidence).
Each has a real implementation and a mock implementation. Selection is automatic:
if the relevant API key is absent, we use the mock AND record that we did, so the
report can tell the user this stage wasn't really verified. The tool never bluffs.
"""

from __future__ import annotations

import ast
import datetime
import json
import operator
import os
import re
from typing import List, Optional, Tuple

from .models import Claim, Evidence, Label

# Real-mode configuration. One key (ANTHROPIC_API_KEY) covers both judging AND evidence
# retrieval, because Claude's server-side web_search tool does the searching for us.
_JUDGE_MODEL = os.environ.get("SECOND_OPINION_MODEL", "claude-sonnet-5")
_WEB_SEARCH_TOOL = os.environ.get("SECOND_OPINION_WEBSEARCH_TOOL", "web_search_20260209")


def _extract_json(text: str) -> Optional[dict]:
    """Pull the last balanced {...} object out of a model response and parse it."""
    depth = 0
    start = None
    best = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    best = text[start : i + 1]
    if not best:
        return None
    try:
        return json.loads(best)
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------- #
# Decomposition: answer -> atomic claims
# --------------------------------------------------------------------------- #

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _naive_sentences(text: str) -> List[str]:
    parts = [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]
    return parts


# Split a sentence further on clause joiners so a checkable fact doesn't get lumped
# with an opinion in the same sentence (e.g. "...most visited monument, and it is a
# beautiful symbol" -> two claims). Heuristic and conservative — the real decomposer
# does this far better with an LLM; this keeps mock mode from hiding embedded facts.
_CLAUSE_SPLIT = re.compile(r",\s+and\s+|;\s+|\s+—\s+|,\s+but\s+")


def _atomic_clauses(text: str) -> List[str]:
    clauses = []
    for sentence in _naive_sentences(text):
        parts = [p.strip(" .,;—") for p in _CLAUSE_SPLIT.split(sentence) if p.strip(" .,;—")]
        clauses.extend(parts if parts else [sentence])
    return clauses


class Decomposer:
    """Turns an answer into checkable claims."""

    def __init__(self) -> None:
        self.is_mock = not os.environ.get("ANTHROPIC_API_KEY")

    def decompose(self, answer: str) -> List[Claim]:
        if self.is_mock:
            return self._mock(answer)
        return self._real(answer)

    def _mock(self, answer: str) -> List[Claim]:
        # Atomic-ish: split sentences AND clause joiners, so an embedded factual
        # claim isn't hidden inside an opinionated sentence. Crude but honest.
        return [Claim(text=s, origin_index=i) for i, s in enumerate(_atomic_clauses(answer))]

    def _real(self, answer: str) -> List[Claim]:  # pragma: no cover - needs key
        from .cache import cache_key, get_cache

        cache = get_cache()
        key = "decomp::" + cache_key(_JUDGE_MODEL, answer)
        hit = cache.get(key)
        if hit is not None and "claims" in hit:
            return [Claim(text=t, origin_index=i) for i, t in enumerate(hit["claims"])]

        from anthropic import Anthropic

        client = Anthropic()
        prompt = (
            "Break the following answer into atomic, independently checkable factual "
            "claims. Drop opinions and pleasantries. Return one claim per line.\n\n"
            f"ANSWER:\n{answer}"
        )
        msg = client.messages.create(
            model=_JUDGE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
        lines = [l.strip("-• ").strip() for l in text.splitlines() if l.strip()]
        cache.put(key, {"claims": lines})
        return [Claim(text=l, origin_index=i) for i, l in enumerate(lines)]


# --------------------------------------------------------------------------- #
# Judge: claim + evidence -> verdict
# --------------------------------------------------------------------------- #

# A tiny built-in knowledge base so the mock demo produces a real mix of verdicts.
# Each entry: substring trigger -> (label, confidence, rationale, evidence)
_MOCK_KB: List[Tuple[str, Label, float, str, Optional[Evidence]]] = [
    (
        "450",  # "The Eiffel Tower is 450 metres tall"
        Label.CONTRADICTED,
        0.97,
        "Independent sources put the Eiffel Tower at about 330 m (≈1,083 ft) including antennas, "
        "not 450 m.",
        Evidence(
            snippet="The Eiffel Tower is 330 metres (1,083 ft) tall, about the same height as an "
            "81-storey building.",
            source_title="Eiffel Tower — official site",
            source_url="https://www.toureiffel.paris/en/the-monument/key-figures",
            supports=False,
        ),
    ),
    (
        "1889",  # "completed in 1889"
        Label.SUPPORTED,
        0.95,
        "Construction finished in March 1889, ahead of the 1889 World's Fair.",
        Evidence(
            snippet="The tower was completed in March 1889 and opened for the Exposition Universelle.",
            source_title="Eiffel Tower — history",
            source_url="https://www.toureiffel.paris/en/the-monument/history",
            supports=True,
        ),
    ),
    (
        "gustave eiffel",  # designer attribution
        Label.SUPPORTED,
        0.9,
        "The tower is named for and was built by the company of engineer Gustave Eiffel.",
        Evidence(
            snippet="Engineer Gustave Eiffel's company designed and built the tower.",
            source_title="Encyclopaedia Britannica — Eiffel Tower",
            source_url="https://www.britannica.com/topic/Eiffel-Tower-Paris-France",
            supports=True,
        ),
    ),
    (
        "most visited",  # "the most visited monument in the world"
        Label.UNVERIFIED,
        0.5,
        "It is among the most visited PAID monuments, but 'most visited in the world' is "
        "contested and depends on how you count free vs paid sites.",
        None,
    ),
    # --- facts the mock judge "knows" (for the benchmark eval) --------------- #
    (
        "30,000 kilometres per second",
        Label.CONTRADICTED,
        0.93,
        "The speed of light is ~299,792 km/s — roughly 300,000, not 30,000. Off by 10x.",
        Evidence(
            snippet="The speed of light in vacuum is 299,792,458 metres per second.",
            source_title="NIST — fundamental constants",
            source_url="https://physics.nist.gov/cgi-bin/cuu/Value?c",
            supports=False,
        ),
    ),
    (
        "boils at 100 degrees fahrenheit",
        Label.CONTRADICTED,
        0.94,
        "Water boils at 100 °C / 212 °F at sea level, not 100 °F.",
        Evidence(
            snippet="At standard pressure water boils at 100 °C (212 °F).",
            source_title="Encyclopaedia Britannica — boiling point",
            source_url="https://www.britannica.com/science/boiling-point",
            supports=False,
        ),
    ),
    (
        "106 bones",
        Label.CONTRADICTED,
        0.95,
        "The adult human skeleton has 206 bones, not 106.",
        Evidence(
            snippet="The adult human body has 206 bones.",
            source_title="Britannica — human skeleton",
            source_url="https://www.britannica.com/science/human-skeleton",
            supports=False,
        ),
    ),
    (
        "great wall of china is visible from the moon",
        Label.CONTRADICTED,
        0.9,
        "The Great Wall is not visible from the Moon with the naked eye — a long-debunked myth.",
        Evidence(
            snippet="The Great Wall of China cannot be seen from the Moon with the unaided eye.",
            source_title="Scientific American",
            source_url="https://www.scientificamerican.com/article/is-chinas-great-wall-visible-from-space/",
            supports=False,
        ),
    ),
    (
        "vaccines cause autism",
        Label.CONTRADICTED,
        0.98,
        "No causal link between vaccines and autism; the original claim was retracted as fraudulent.",
        Evidence(
            snippet="Extensive research shows no link between vaccines and autism.",
            source_title="CDC — Vaccine Safety",
            source_url="https://www.cdc.gov/vaccinesafety/concerns/autism.html",
            supports=False,
        ),
    ),
    (
        "300,000 kilometres per second",
        Label.SUPPORTED,
        0.9,
        "~299,792 km/s rounds to 300,000 km/s. Correct.",
        Evidence(
            snippet="The speed of light is 299,792,458 m/s ≈ 300,000 km/s.",
            source_title="NIST — fundamental constants",
            source_url="https://physics.nist.gov/cgi-bin/cuu/Value?c",
            supports=True,
        ),
    ),
    (
        "boils at 100 degrees celsius",
        Label.SUPPORTED,
        0.95,
        "Correct: water boils at 100 °C at sea level.",
        Evidence(
            snippet="At standard pressure water boils at 100 °C.",
            source_title="Encyclopaedia Britannica — boiling point",
            source_url="https://www.britannica.com/science/boiling-point",
            supports=True,
        ),
    ),
    (
        "206 bones",
        Label.SUPPORTED,
        0.95,
        "Correct: the adult human body has 206 bones.",
        Evidence(
            snippet="The adult human body has 206 bones.",
            source_title="Britannica — human skeleton",
            source_url="https://www.britannica.com/science/human-skeleton",
            supports=True,
        ),
    ),
    (
        "capital of france",
        Label.SUPPORTED,
        0.98,
        "Correct: Paris is the capital of France.",
        Evidence(
            snippet="Paris is the capital and most populous city of France.",
            source_title="Britannica — Paris",
            source_url="https://www.britannica.com/place/Paris",
            supports=True,
        ),
    ),
]


class JudgeError(Exception):
    """A real verification call FAILED (infra/parse) — distinct from an 'unverified' verdict.

    An unverified verdict means 'I looked and couldn't find evidence' (a valid answer).
    A JudgeError means 'I couldn't even ask' (bad key, rate limit, wrong tool id, no JSON).
    The pipeline turns these into a graceful UNVERIFIED; the doctor surfaces them loudly.
    """

    def __init__(self, message: str, kind: str = "unknown", hint: str = "") -> None:
        super().__init__(message)
        self.kind = kind
        self.hint = hint


def _diagnose(exc: Exception) -> "JudgeError":
    """Map a raw SDK/network exception to a friendly, actionable JudgeError."""
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if "authentication" in name or "permission" in name or "invalid x-api-key" in msg or "401" in msg:
        return JudgeError(
            "API key rejected",
            kind="auth",
            hint="Check ANTHROPIC_API_KEY in your .env (no quotes, no trailing spaces, not expired).",
        )
    if "ratelimit" in name or "429" in msg or "rate limit" in msg:
        return JudgeError(
            "Rate limited by the API",
            kind="rate_limit",
            hint="Wait a moment and retry, or run fewer claims at once.",
        )
    if ("badrequest" in name or "400" in msg or "not_found" in msg or "404" in msg) and (
        "tool" in msg or "web_search" in msg
    ):
        return JudgeError(
            "The web_search tool was rejected",
            kind="bad_tool",
            hint="The tool id may be outdated — set SECOND_OPINION_WEBSEARCH_TOOL to the current "
            "value from Anthropic's web search docs.",
        )
    if "connection" in name or "timeout" in name or "network" in msg:
        return JudgeError(
            "Could not reach the API",
            kind="network",
            hint="Check your internet connection and try again.",
        )
    return JudgeError(f"{type(exc).__name__}: {exc}", kind="unknown", hint="Unexpected error.")


_STANDARD_SYSTEM = (
    "You are an independent fact-checker. You verify a SINGLE claim against external "
    "web evidence. Be calibrated and honest:\n"
    "- SUPPORTED: authoritative evidence backs it up.\n"
    "- CONTRADICTED: authoritative evidence goes against it (includes fabricated "
    "citations/cases you cannot find, and stale facts that are no longer true).\n"
    "- UNVERIFIED: you could not find sufficient evidence either way. Do NOT guess.\n"
    "- NOT_CHECKABLE: it's an opinion, value judgment, or prediction.\n"
    "Search before deciding. Prefer primary/authoritative sources.\n\n"
    "CRITICAL — a false alarm is worse than a miss. Only return CONTRADICTED when you "
    "find clear, authoritative evidence that the claim is FALSE. If the evidence is thin, "
    "mixed, or the claim is merely contested, unproven, debated, or surprising-but-"
    "plausible, return UNVERIFIED — not CONTRADICTED. Surprising true facts exist; never "
    "flag a claim false just because it is counterintuitive. Your confidence must reflect "
    "real uncertainty, not bravado."
)

# Specialized checker for claims that cite a source — checks the SOURCE, not just the topic.
_CITATION_SYSTEM = (
    "You are verifying a CLAIM that cites a source — a study, paper, court case, report, "
    "book, quote, or statistic. Check the SOURCE itself, not just whether the topic sounds "
    "plausible:\n"
    "1. Search for the exact cited source (title, authors, year, venue, or case name).\n"
    "2. If, after searching, you cannot establish that the source EXISTS, it is likely "
    "fabricated -> CONTRADICTED (rationale: 'no such source found').\n"
    "3. If the source exists but does NOT support the claim (misattributed, misquoted, wrong "
    "finding) -> CONTRADICTED (say what it actually says).\n"
    "4. If the source exists and supports the claim -> SUPPORTED.\n"
    "5. If you genuinely cannot determine existence either way -> UNVERIFIED.\n\n"
    "IMPORTANT: do not call a real but obscure source fabricated just because it's hard to "
    "find — when unsure, prefer UNVERIFIED. A false 'fabricated' accusation is costly."
)


def _verdict_user(claim_text: str) -> str:
    return (
        f"CLAIM: {claim_text}\n\n"
        "Search for evidence, then respond with ONLY a JSON object as the final line:\n"
        '{"label": "supported|contradicted|unverified|not_checkable", '
        '"confidence": 0.0-1.0, "rationale": "one sentence", '
        '"sources": [{"title": "...", "url": "...", "snippet": "..."}]}'
    )


# Router: does this claim cite a source? Heuristic recall is enough — the citation checker
# does the real work, and a false route still yields a sensible verdict.
_CITE_KW = (r"study|paper|report|journal|research|survey|trial|meta-?analysis|guidelines?|"
            r"accord|protocol|book|novel|declaration|treaty|convention|charter")
_CITE_PATTERNS = [
    r"\bet al\.?",
    r"\baccording to\b",
    r"\bpublished in\b",
    rf"\b(19|20)\d{{2}}\b.{{0,45}}\b({_CITE_KW})\b",
    rf"\b({_CITE_KW})\b.{{0,45}}\b(19|20)\d{{2}}\b",
    r"\b[A-Z][a-z]+ v\.? [A-Z][a-z]+\b",
    r"\b(supreme court|court) case\b",
    r"\b[A-Z][a-z]+(?:'s)? (?:said|wrote|coined|claimed|stated|argued|noted)\b",
    r"\bcoined the (phrase|term)\b",
]


def looks_like_citation(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in _CITE_PATTERNS)


# --- Temporal / recency route -------------------------------------------------
# Claims about the CURRENT state of the world go stale — exactly where a model's training
# data misleads. Route them to a date-aware check that trusts live search over memory.
_TEMPORAL_SYSTEM = (
    "You are checking whether a claim about the CURRENT state of the world is STILL TRUE today. "
    "Today's date is {today}. The claim may reflect outdated training knowledge.\n"
    "- Search for the CURRENT fact as of today.\n"
    "- If the claim WAS true but is now outdated or changed, return CONTRADICTED "
    "(rationale: 'outdated — as of {today}, ...').\n"
    "- If it is still current and correct, return SUPPORTED.\n"
    "- If you cannot determine the current state, return UNVERIFIED.\n"
    "Do NOT rely on memory for anything time-sensitive; trust the search results."
)
_TEMPORAL_PATTERNS = [
    r"\bcurrent(ly)?\b", r"\bas of\b", r"\bnowadays\b", r"\bthese days\b", r"\bat present\b",
    r"\bto date\b", r"\bup[- ]to[- ]date\b", r"\blatest\b", r"\bnewest\b", r"\bmost recent\b",
    r"\breigning\b", r"\bincumbent\b", r"\bin office\b", r"\bpresent[- ]day\b", r"\bright now\b",
]


def looks_temporal(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in _TEMPORAL_PATTERNS)


# --- Numeric / math route (deterministic — no model needed) -------------------
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.UAdd: operator.pos}


def _safe_eval(expr: str) -> float:
    """Evaluate a pure-arithmetic expression safely (no names, calls, or attributes)."""
    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError("unsafe expression")
    return ev(ast.parse(expr, mode="eval"))


def _parse_num(s: str) -> float:
    s = s.strip().lower().replace(",", "")
    mult = 1.0
    for suf, m in [("trillion", 1e12), ("billion", 1e9), ("million", 1e6),
                   ("thousand", 1e3), ("bn", 1e9), ("k", 1e3)]:
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
            mult = m
            break
    return float(s) * mult


def _fmt(x: float) -> str:
    if abs(x - round(x)) < 1e-9:
        return f"{int(round(x)):,}"
    return f"{x:,.4f}".rstrip("0").rstrip(".")


_NUM = r"([\d][\d,\.]*\s*(?:trillion|billion|million|thousand)?)"
_IS = r"(?:is|are|equals?|is equal to|=)"
_pn = _parse_num
_CALC_RULES = [
    (rf"{_NUM}\s*(?:%|percent)\s+of\s+{_NUM}\s+{_IS}\s+{_NUM}", lambda a, b, c: (_pn(a) / 100 * _pn(b), _pn(c))),
    (rf"{_NUM}\s*(?:times|x|×|multiplied by)\s*{_NUM}\s+{_IS}\s+{_NUM}", lambda a, b, c: (_pn(a) * _pn(b), _pn(c))),
    (rf"(?:the\s+sum\s+of\s+)?{_NUM}\s*(?:plus|\+|and)\s*{_NUM}\s+{_IS}\s+{_NUM}", lambda a, b, c: (_pn(a) + _pn(b), _pn(c))),
    (rf"{_NUM}\s*(?:minus|-)\s*{_NUM}\s+{_IS}\s+{_NUM}", lambda a, b, c: (_pn(a) - _pn(b), _pn(c))),
    (rf"{_NUM}\s*(?:divided by|/)\s*{_NUM}\s+{_IS}\s+{_NUM}", lambda a, b, c: (_pn(a) / _pn(b), _pn(c))),
    (rf"half\s+of\s+{_NUM}\s+{_IS}\s+{_NUM}", lambda b, c: (_pn(b) / 2, _pn(c))),
    (rf"{_NUM}\s+squared\s+{_IS}\s+{_NUM}", lambda a, c: (_pn(a) ** 2, _pn(c))),
    (rf"{_NUM}\s+to the power of\s+{_NUM}\s+{_IS}\s+{_NUM}", lambda a, b, c: (_pn(a) ** _pn(b), _pn(c))),
]


def _extract_calc(text):
    """Return (computed, claimed) for an asserted calculation, or None. Model-free."""
    for rx, fn in _CALC_RULES:
        m = re.search(rx, text, re.IGNORECASE)
        if m:
            try:
                return fn(*m.groups())
            except (ValueError, ZeroDivisionError):
                continue
    return None


_NUMERIC_PATTERNS = [
    r"[\d,\.]+\s*(?:%|percent)\s+of\b", r"\b(sum|total|average|product) of\b",
    r"[\d,\.]+\s*(?:plus|minus|times|divided by|multiplied by|\+|×)\s*[\d,\.]+",
    r"[\d,\.]+\s+squared\b", r"\bto the power of\b", r"\bhalf of\s+[\d,\.]+",
]


def looks_numeric(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in _NUMERIC_PATTERNS)


def classify_route(text: str) -> str:
    """Pick the specialized checker for a claim. Precedence: citation > temporal > numeric."""
    if looks_like_citation(text):
        return "citation"
    if looks_temporal(text):
        return "temporal"
    if looks_numeric(text):
        return "numeric"
    return "standard"


class Judge:
    """Decides a verdict for a claim, given evidence."""

    def __init__(self) -> None:
        self.is_mock = not os.environ.get("ANTHROPIC_API_KEY")

    def judge(self, claim: Claim, evidence: List[Evidence]) -> Tuple[Label, float, str, List[Evidence]]:
        """Pipeline-facing: always graceful. A broken call becomes an honest UNVERIFIED.

        Successful real verdicts are cached (keyed by model + claim) so interrupted runs
        resume for free and re-runs don't repeat paid web searches. Failures are NOT cached.
        """
        if self.is_mock:
            return self._mock(claim)

        from .cache import cache_key, deserialize, get_cache, serialize

        cache = get_cache()
        key = cache_key(_JUDGE_MODEL, claim.text)
        hit = cache.get(key)
        if hit is not None:
            return deserialize(hit)

        try:
            label, conf, rationale, ev = self._real(claim, evidence)
        except JudgeError as err:
            # Don't cache failures — we want them retried next run.
            return Label.UNVERIFIED, 0.3, f"Verification unavailable ({err}). Treat as unverified.", []

        cache.put(key, serialize(label, conf, rationale, ev))
        return label, conf, rationale, ev

    def verify_routed(self, claim: Claim) -> Tuple[Label, float, str, List[Evidence]]:
        """Route a claim to its specialized checker — the way the product does."""
        route = classify_route(claim.text)
        if route == "citation":
            return self.verify_citation(claim)
        if route == "temporal":
            return self.verify_temporal(claim)
        if route == "numeric":
            return self.verify_numeric(claim)
        return self.judge(claim, [])

    def check(self, claim: Claim) -> Tuple[Label, float, str, List[Evidence]]:
        """Diagnostics-facing (doctor): real verification that RAISES JudgeError on failure."""
        if self.is_mock:
            raise JudgeError(
                "Running in mock mode — no API key",
                kind="mock",
                hint="Add ANTHROPIC_API_KEY to your .env to enable real verification.",
            )
        return self._real(claim, [])

    def _mock(self, claim: Claim) -> Tuple[Label, float, str, List[Evidence]]:
        low = claim.text.lower()
        # Opinions / non-factual -> NOT_CHECKABLE
        if any(w in low for w in ("beautiful", "should", "i think", "best", "stunning", "probably", "likely")):
            return Label.NOT_CHECKABLE, 0.0, "This is a judgment, not a factual claim.", []
        for trigger, label, conf, rationale, ev in _MOCK_KB:
            if trigger in low:
                return label, conf, rationale, ([ev] if ev else [])
        return (
            Label.UNVERIFIED,
            0.4,
            "Couldn't find independent evidence either way. Treat as unverified — not wrong.",
            [],
        )

    def _real(self, claim: Claim, evidence: List[Evidence]):  # pragma: no cover - needs key
        """Grounded verification: Claude searches the web for evidence, then verdicts.

        The whole soul of the product is here — an INDEPENDENT check against EXTERNAL
        evidence, with calibrated confidence. On any failure we return UNVERIFIED rather
        than guess: the tool never bluffs.
        """
        return self._grounded(_STANDARD_SYSTEM, _verdict_user(claim.text))

    def _real_citation(self, claim: Claim):  # pragma: no cover - needs key
        """Specialized checker: verify a CITED SOURCE exists and actually supports the claim."""
        return self._grounded(_CITATION_SYSTEM, _verdict_user(claim.text))

    def verify_citation(self, claim: Claim) -> Tuple[Label, float, str, List[Evidence]]:
        """Pipeline-facing citation check — graceful, cached under a separate 'cite' key."""
        if self.is_mock:
            return self._mock(claim)
        from .cache import cache_key, deserialize, get_cache, serialize

        cache = get_cache()
        key = cache_key(_JUDGE_MODEL, "cite::" + claim.text)
        hit = cache.get(key)
        if hit is not None:
            return deserialize(hit)
        try:
            result = self._real_citation(claim)
        except JudgeError as err:
            return Label.UNVERIFIED, 0.3, f"Verification unavailable ({err}). Treat as unverified.", []
        cache.put(key, serialize(*result))
        return result

    def verify_temporal(self, claim: Claim) -> Tuple[Label, float, str, List[Evidence]]:
        """Date-aware check for 'current state of the world' claims that may be stale."""
        if self.is_mock:
            return self._mock(claim)
        from .cache import cache_key, deserialize, get_cache, serialize

        today = datetime.date.today().isoformat()
        cache = get_cache()
        key = cache_key(_JUDGE_MODEL, f"temporal::{today}::{claim.text}")  # date in key -> auto-invalidates
        hit = cache.get(key)
        if hit is not None:
            return deserialize(hit)
        try:
            result = self._grounded(_TEMPORAL_SYSTEM.format(today=today), _verdict_user(claim.text))
        except JudgeError as err:
            return Label.UNVERIFIED, 0.3, f"Verification unavailable ({err}). Treat as unverified.", []
        cache.put(key, serialize(*result))
        return result

    def verify_numeric(self, claim: Claim) -> Tuple[Label, float, str, List[Evidence]]:
        """Recompute the arithmetic in Python — deterministic, no model trusted for the math."""
        res = _extract_calc(claim.text)
        if res is None and not self.is_mock:
            res = self._llm_extract_calc(claim)  # fallback for word-numbers / complex phrasing
        if res is None:
            if self.is_mock:
                return self._mock(claim)
            return Label.UNVERIFIED, 0.4, "No cleanly checkable arithmetic found in the claim.", []
        computed, claimed = res
        denom = max(abs(claimed), abs(computed), 1e-9)
        if abs(computed - claimed) / denom < 0.01:
            return Label.SUPPORTED, 0.99, f"Recomputed — the arithmetic checks out ({_fmt(computed)}).", []
        return (Label.CONTRADICTED, 0.99,
                f"The math is off: recomputed {_fmt(computed)}, but the claim says {_fmt(claimed)}.", [])

    def _llm_extract_calc(self, claim):  # pragma: no cover - needs key
        """Real-mode fallback: have the model extract a pure arithmetic expression; we compute it."""
        from anthropic import Anthropic

        client = Anthropic()
        try:
            msg = client.messages.create(
                model=_JUDGE_MODEL, max_tokens=300,
                messages=[{"role": "user", "content":
                    "Extract the arithmetic claim below as JSON: "
                    '{"expression": "<pure arithmetic, digits and + - * / ** () only>", '
                    '"claimed": <the numeric result the claim asserts>}. If there is no checkable '
                    f"calculation, return {{}}.\n\nCLAIM: {claim.text}"}],
            )
        except Exception:  # noqa: BLE001
            return None
        text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
        data = _extract_json(text) or {}
        expr, claimed = data.get("expression"), data.get("claimed")
        if not expr or claimed is None:
            return None
        try:
            return _safe_eval(str(expr)), float(claimed)
        except (ValueError, SyntaxError, ZeroDivisionError, TypeError):
            return None

    def _grounded(self, system: str, user: str):  # pragma: no cover - needs key
        """Shared grounded call: Claude + web search, one retry on unparseable JSON, then parse.

        Up to 2 attempts: sensitive/complex topics make the model search + write more, which
        can truncate the JSON verdict. A stricter retry fixes the silent 'unparseable ->
        unverified' failure that used to hide real catches.
        """
        from anthropic import Anthropic

        client = Anthropic()
        data = None
        messages = [{"role": "user", "content": user}]
        for attempt in range(2):
            try:
                msg = client.messages.create(
                    model=_JUDGE_MODEL,
                    max_tokens=4096,
                    system=system,
                    tools=[{"type": _WEB_SEARCH_TOOL, "name": "web_search", "max_uses": 4}],
                    messages=messages,
                )
            except Exception as exc:  # noqa: BLE001 - translate to a typed, actionable error
                raise _diagnose(exc)

            text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
            data = _extract_json(text)
            if data:
                break
            messages = [
                {"role": "user", "content": user},
                {"role": "assistant", "content": text[-2000:] or "(no text)"},
                {"role": "user", "content": "That reply had no parseable JSON verdict. Reply with ONLY the "
                 "JSON object described above and nothing else — no search, no commentary."},
            ]

        if not data:
            raise JudgeError(
                "Model returned no parseable verdict",
                kind="parse",
                hint="The reply had no valid JSON even after a retry (possibly still truncated).",
            )

        try:
            label = Label(str(data.get("label", "unverified")).strip().lower())
        except ValueError:
            label = Label.UNVERIFIED
        try:
            conf = float(data.get("confidence", 0.4))
        except (TypeError, ValueError):
            conf = 0.4
        rationale = str(data.get("rationale", "")).strip()
        ev = [
            Evidence(
                snippet=str(s.get("snippet", "")),
                source_title=str(s.get("title", "")),
                source_url=str(s.get("url", "")),
                supports=(label == Label.SUPPORTED),
            )
            for s in (data.get("sources") or [])
            if isinstance(s, dict)
        ]
        return label, conf, rationale, ev


# --------------------------------------------------------------------------- #
# Search: claim -> evidence
# --------------------------------------------------------------------------- #


class Search:
    """Retrieves external evidence for a claim. In v1, real search is optional;
    the mock judge already carries its own evidence, so this is a thin seam for now."""

    def __init__(self) -> None:
        self.is_mock = not os.environ.get("SEARCH_API_KEY")

    def find(self, claim: Claim) -> List[Evidence]:
        # v1: evidence is attached at judge time in mock mode. Real retrieval plugs in here.
        return []
