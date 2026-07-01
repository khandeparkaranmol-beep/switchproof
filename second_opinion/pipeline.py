"""The pipeline: answer -> Report.

decompose -> retrieve -> judge -> calibrate -> assemble. Each step is small and
swappable. Calibration is now a fitted, first-class stage (see calibration.py): it loads
a map fitted on labelled data so "90% confident" means right 90% of the time, and falls
back to a conservative shrink-toward-0.5 when no map has been fitted yet.
"""

from __future__ import annotations

from typing import List

from .calibration import apply_calibration as _calibrate
from .models import Label, Report, Verdict
from .providers import classify_route, Decomposer, Judge, Search


class Pipeline:
    def __init__(self) -> None:
        self.decomposer = Decomposer()
        self.search = Search()
        self.judge = Judge()

    def run(self, answer: str) -> Report:
        report = Report(answer=answer)

        # Record which stages are running on mock data, so the report can be honest.
        if self.decomposer.is_mock:
            report.mock_stages.append("decomposition")
        if self.search.is_mock:
            report.mock_stages.append("retrieval")
        if self.judge.is_mock:
            report.mock_stages.append("judging")

        claims = self.decomposer.decompose(answer)
        for claim in claims:
            evidence = self.search.find(claim)
            # Router: send each claim to its specialized checker. Adding a trust dimension
            # = add a route + a checker. Everything else falls through to the grounded judge.
            route = classify_route(claim.text)
            if route == "citation":
                label, raw_conf, rationale, used_evidence = self.judge.verify_citation(claim)
            elif route == "temporal":
                label, raw_conf, rationale, used_evidence = self.judge.verify_temporal(claim)
            elif route == "numeric":
                label, raw_conf, rationale, used_evidence = self.judge.verify_numeric(claim)
            else:
                label, raw_conf, rationale, used_evidence = self.judge.judge(claim, evidence)
            verdict = Verdict(
                claim=claim,
                label=label,
                confidence=_calibrate(label, raw_conf),
                rationale=rationale,
                evidence=used_evidence,
            )
            report.verdicts.append(verdict)

        return report
