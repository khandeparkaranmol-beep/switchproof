# The Trust-Failure Taxonomy

Every way an AI answer can betray the person reading it — and the experience a good solution
gives for each. "Is this fact wrong?" is only one row. A genuinely useful verifier covers the
rest, and gives people clear, prioritized data — without drifting into being a general critic.

**Design law:** every dimension must answer *"can I trust this?"* — never *"is this a good answer?"*
The moment it grades completeness or style, it stops being a trust tool and becomes a me-too reviewer.

---

## Tier 1 — objectively checkable, high harm (build first)

### Factual falsehood  ·  BUILT
A plainly wrong claim.
- **User pain:** acts on something false.
- **Ideal CX:** red flag + the correct fact + a source. *"False — the Eiffel Tower is ~330m, not 450m."*

### Fabricated citation  ·  BUILDING NOW
Cites a study, case, quote, or statistic that doesn't exist, or exists but doesn't say that.
The career-ender: fake legal precedents, invented papers, misattributed quotes.
- **User pain:** repeats a fabricated source in a brief, essay, or decision — catastrophic.
- **Ideal CX:** the loudest alarm, and *distinct from "false"* — *"I couldn't find this source; it may be
  fabricated,"* or *"This source exists but doesn't support the claim,"* with what the search found.

### Numerical / math error  ·  NEXT
Wrong arithmetic, bad unit conversion, statistics that don't add up.
- **User pain:** a wrong number in a model, quote, or report.
- **Ideal CX:** recompute and show the work. *"The math is off: 15% of 2.3M is 345K, not 3.45M."*

### Outdated / stale  ·  PARTIAL
True once, wrong now (post-cutoff events, changed facts).
- **User pain:** relies on a fact that has since changed.
- **Ideal CX:** date-aware. *"True as of 2021, but outdated — currently X."*

---

## Tier 2 — nuanced, high value, harder to label

### Contested stated as settled  ·  BUILD SOON
Genuinely debated, presented as fact. The **most common real-world trust failure.**
- **User pain:** takes one side of a live debate as established truth.
- **Ideal CX:** not "false" — *"This is actually debated; here's the range of expert views."*

### Misleading but technically true
Cherry-picked or missing the caveat that flips the meaning.
- **Ideal CX:** *"Technically true, but missing context: [caveat]."*

### High-stakes advice without a caveat
Medical, legal, financial, or safety guidance stated flatly.
- **User pain:** acts on unqualified high-stakes advice.
- **Ideal CX:** severity flag — *"High-stakes; verify with a professional. It omits [risk]."* Detect the domain.

### Overconfidence
States uncertain things as definite.
- **Ideal CX:** *"Stated with more certainty than the evidence supports."*

---

## Tier 3 — verifiable but structural

### Internal inconsistency
The answer contradicts itself, or a conclusion doesn't follow.
- **Ideal CX:** *"These two parts conflict."*

### Unsupported / unverifiable  ·  BUILT
A specific claim with no findable evidence (not necessarily false).
- **Ideal CX:** *"Couldn't verify — treat with caution."*

---

## The guardrail — do NOT build
Omission, bias, tone, "this could be better." These are general answer-critique. They dilute the
soul and multiply false positives. Keep the tool sharp: *trust*, not *quality*.

---

## Priority = harm × verifiability × demo-impact

1. **Fabricated citation** — high harm, highly checkable (does it exist?), viral demo. *(building)*
2. **Numerical error** — clean to verify (recompute), high value. *(next)*
3. **Contested-as-settled** — most common failure, high value, trickier to label. *(soon)*
4. **High-stakes-no-caveat** — high harm, detectable by domain classification.
5. Outdated, misleading-but-true, overconfidence, inconsistency.

## The data users actually want (output, not just detection)
- An at-a-glance trust read: *"1 false, 1 contested, 1 outdated."*
- The one thing to check first (ranked by consequence).
- Honest coverage: *"Verified 6 of 9 claims; 3 are opinions I can't check."*
- Severity: the dangerous claim flagged loudest.

## Architecture that makes this scale
A **claim-type router** classifies each decomposed claim (citation / numeric / temporal / factual /
contested / high-stakes) and routes it to the right specialized checker. Add a dimension = add a
checker + a labeled benchmark slice + a metric. The eval grows with the product.
