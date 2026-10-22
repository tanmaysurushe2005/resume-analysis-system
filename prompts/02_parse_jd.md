# Task: Job description -> atomic, testable requirements

Turn the job description into a list of requirements a recruiter could verify from a resume.

## Rules
- One requirement = one verifiable thing. Alternatives that are genuinely interchangeable stay together in parentheses, e.g. "SQL databases (PostgreSQL, MySQL)".
- `type`: "must" only if the posting says required/must/minimum or clearly cannot be done without it; otherwise "nice". If the posting does not separate them, treat core responsibilities as "must" and "bonus/plus/preferred" items as "nice".
- Keep numbers (e.g. "3+ years") inside the text so they can be checked.
- Drop fluff that cannot be verified ("rockstar", "fast-paced", "passionate").
- `category`: skill | experience | education | domain | soft | other.
- `inclusivity_notes`: quote any phrase likely to exclude people on protected grounds (e.g. "young and energetic", "native English speaker", "digital native", "recent graduate"). Empty list if none. Do not create requirements from these phrases.
- Maximum 12 requirements. Merge near-duplicates. Ids are placeholders (R1, R2, ...); they will be renumbered.

## Schema
{"title": str, "seniority": str, "requirements": [{"id": str, "text": str, "type": "must"|"nice", "category": str}], "inclusivity_notes": [str]}

=== USER ===
<job_description>
{{job}}
</job_description>

Return the JSON now.
