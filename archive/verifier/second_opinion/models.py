"""Core data types for Second Opinion.

A run flows: answer -> [Claim] -> each Claim gets [Evidence] -> a Verdict -> a Report.
The types are deliberately small. The honesty of the product lives in the Verdict:
it always carries its confidence AND the evidence it rests on, so nothing is asserted
without something to point at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Label(str, Enum):
    """The only verdicts we allow. Note what's missing: there is no bare 'FALSE'.

    We say CONTRADICTED (we found evidence against it) — not 'false' — because the
    tool reports what it found, and lets the user be the judge.
    """

    SUPPORTED = "supported"        # external evidence backs this up
    CONTRADICTED = "contradicted"  # external evidence goes against this
    UNVERIFIED = "unverified"      # we couldn't find evidence either way
    NOT_CHECKABLE = "not_checkable"  # opinion / prediction / not a factual claim

    @property
    def needs_attention(self) -> bool:
        return self in (Label.CONTRADICTED, Label.UNVERIFIED)


@dataclass
class Evidence:
    """A single piece of external evidence for or against a claim."""

    snippet: str
    source_title: str
    source_url: str
    supports: Optional[bool] = None  # True=supports, False=contradicts, None=neutral


@dataclass
class Claim:
    """One atomic, checkable statement lifted out of the answer."""

    text: str
    # Index of the sentence in the original answer it came from (for inline display).
    origin_index: int = 0


@dataclass
class Verdict:
    """What we concluded about a claim — always with its confidence and its evidence."""

    claim: Claim
    label: Label
    confidence: float  # 0.0–1.0, calibrated
    rationale: str
    evidence: List[Evidence] = field(default_factory=list)

    @property
    def primary_source(self) -> Optional[Evidence]:
        # Prefer evidence that actually decided the verdict.
        decisive = Label.SUPPORTED == self.label
        for e in self.evidence:
            if e.supports is decisive:
                return e
        return self.evidence[0] if self.evidence else None


@dataclass
class Report:
    """The full result for one answer."""

    answer: str
    verdicts: List[Verdict] = field(default_factory=list)
    mock_stages: List[str] = field(default_factory=list)  # which stages ran on mock data

    @property
    def flagged(self) -> List[Verdict]:
        """The 1–2 things that need the user's eyes — what we draw attention to."""
        return [v for v in self.verdicts if v.label.needs_attention]

    @property
    def checked_count(self) -> int:
        return sum(1 for v in self.verdicts if v.label != Label.NOT_CHECKABLE)

    @property
    def is_nothing_to_verify(self) -> bool:
        """True when there are no checkable factual claims at all — pure opinion/advice.

        This is the triage gate: when it's True, the product should stay calm and say so,
        not manufacture an empty scorecard.
        """
        return self.checked_count == 0

    def summary_line(self) -> str:
        supported = sum(1 for v in self.verdicts if v.label == Label.SUPPORTED)
        flagged = len(self.flagged)
        if self.is_nothing_to_verify:
            return "Nothing to verify — this reads as opinion or advice, not factual claims."
        if flagged == 0:
            return f"{supported} claims verified. Nothing flagged."
        verb = "needs" if flagged == 1 else "need"
        return f"{supported} verified, {flagged} {verb} your eyes."
