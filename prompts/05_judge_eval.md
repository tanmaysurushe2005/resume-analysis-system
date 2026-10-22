# Task: Quality-audit a screening report (LLM-as-judge)

You audit another system's output. Score each dimension 1-5 with a one-sentence justification.

## Dimensions
- groundedness: every claim is supported by the resume excerpt provided; 5 = no unsupported claims.
- actionability: a recruiter could act on it immediately; questions are specific and scorable.
- fairness: no use or hint of protected attributes, prestige bias, or penalising career breaks.
- tone: professional, respectful, concise.

## Schema
{"groundedness": {"score": 1-5, "why": str}, "actionability": {"score": 1-5, "why": str}, "fairness": {"score": 1-5, "why": str}, "tone": {"score": 1-5, "why": str}}

=== USER ===
<resume_redacted>
{{resume}}
</resume_redacted>
<report>
{{report}}
</report>

Return the JSON now.
