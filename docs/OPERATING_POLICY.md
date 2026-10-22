# Resume Analysis System Operating Policy

> Development project. Not validated on real hiring data. Not approved for production hiring. Use only synthetic or consented data. The jurisdiction, retention and owner entries below are project defaults, not legal advice.

## Minimum safety policy

- The system is advisory only and cannot automatically reject or advance candidates.
- A qualified human reviewer approves every hiring decision and can override any recommendation.
- Every recommendation shows its evidence and reasoning.
- Resumes with prompt-injection or integrity flags are never automatically advanced.
- Low-confidence, missing-evidence, near-threshold or inconsistent results are escalated for human review.
- Protected attributes are not used to score or rank candidates and are never inferred.
- Career breaks, nontraditional education and alternative career paths are not penalized unless directly relevant to a documented job requirement.
- Resume data is not used to train external models. Provider retention and data-use terms must be verified for the tier in use before any real resumes are processed. TODO: verify the provider's current terms.
- Retention follows the deletion policy below. Access is limited to authorized users. Analysis, overrides, final decisions and deletions are auditable.
- No production use until legal, privacy, security, fairness and recruiter validation are complete.

## Operating answers

| # | Question | Answer |
|---:|---|---|
| 1 | Jurisdictions | India. No production use yet. Any real deployment requires a legal review against applicable Indian data-protection law (including the Digital Personal Data Protection Act, 2023) and the rules of any other region where candidates are located. This document does not claim compliance with any law. |
| 2 | Users | Recruiters, hiring managers, an admin, a read-only auditor. |
| 3 | Authority | Advisory only. |
| 4 | Human approval | Required for every recommendation. |
| 5 | Retention | Project default of 90 days for real data unless a legal hold applies; the compliance owner may change it. Development uses synthetic data only. |
| 6 | Auto-deletion | Yes after 90 days, plus manual deletion on request; deletions are logged. (Not yet implemented.) |
| 7 | Access | Recruiters see only their own jobs; admins manage users and settings, not candidate content by default; auditors see logs, not resume text. (Not yet implemented; no login exists today.) |
| 8 | Candidate explanations | Drafts only; a human edits and approves; no scores, internal reasoning or flags shown to candidates. |
| 9 | Audit log events | Resume upload, analysis request, provider/model/prompt version, scores and recommendation, flags raised, human overrides with reason, final decision, export, deletion. |
| 10 | Escalation | Injection/integrity flags, low confidence, missing must-have evidence, near-threshold scores, conflicting reviewer decisions. |
| 11 | ATS | None now; CSV/Excel export only. |
| 12 | Volume | Development scale; free-tier ceiling is a few hundred resumes/day at about 2 model calls each. |
| 13 | Performance | Best-effort batch, no SLA. |
| 14 | Deployment/auth | Local machine now; planned login and role-based access on an internal server or cloud. |
| 15 | Compliance owner | Project supervisor / faculty guide (name to be added before this document is shared). No legal, privacy or security owner is assigned for a real deployment yet. |

## Implementation status

| Item | Status |
|---|---|
| Advisory wording | Implemented |
| Evidence display | Implemented |
| Injection flagging | Implemented |
| Audit log | Planned |
| Escalation margin | Planned |
| Login | Not implemented |
| Roles | Not implemented |
| Auto-deletion | Not implemented |
| ATS | Not implemented |

## Validation status

- Recruiter-labelled calibration not done.
- Fairness audit on real data not done.
- Synthetic paired fairness tests planned.
- Tier stability measured on 5 synthetic resumes only.
- Provider data-use terms not yet verified.
