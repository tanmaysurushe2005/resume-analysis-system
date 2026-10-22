# Resume Analysis & Recommendation System

## Development status

**Development project completed.** The CLI and Streamlit dashboard are implemented
and validated with the available synthetic test data. This does not indicate
production readiness or replace the validation requirements in the operating policy.

A prompt-engineered pipeline that screens resumes for a recruitment firm: it turns a job description into testable requirements, scores each resume **with verifiable evidence**, and produces a recruiter-ready recommendation with an interview plan and candidate feedback.

**Core idea: the LLM judges evidence; code does arithmetic, verification and policy.**

```
resume --> sanitize/redact --> [1 Extract profile] --\
                                                      +--> [3 Score per requirement] --> verify quotes in code
job desc ----------------------> [2 Parse requirements] /         (evidence-grounded, 0-4 rubric)       |
                                                                                                         v
                        report <-- [4 Recommend (explains tier)] <-- deterministic score + tier policy + review flags
```

## What makes it strong
| Concern | Design |
|---|---|
| Hallucinated praise | Every score needs verbatim quotes; code checks them against the resume and caps unsupported claims |
| Consistency | Anchored rubric, reasoning-before-score field order, worked example, deterministic tier policy in code |
| Bad arithmetic / drift | Weighted score and tier thresholds computed in code, not by the model |
| Bias | Identity redaction before scoring, protected-attribute ban, career breaks neutral, biased-JD-language detector |
| Prompt injection in resumes | Delimiters neutralised, regex pre-scan, model told to report not obey, flagged resumes can never auto-advance |
| Malformed output | Pydantic schemas + automatic repair retry |
| Accountability | Human-review flags (low confidence, near threshold, integrity), versioned prompts, eval harness |

## Quick start (Windows PowerShell)
```powershell
py -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env        # add ANTHROPIC_API_KEY (optional: without it, offline mock mode runs)
$env:PYTHONPATH="src"
py -m resume_analyzer analyze --resume data\resumes\r01_strong.txt --job data\jobs\backend_engineer_payments.txt
py -m resume_analyzer rank --resumes data\resumes --job data\jobs\backend_engineer_payments.txt
py eval\run_eval.py --runs 3 --judge
py -m pytest -q
```
macOS/Linux: `export PYTHONPATH=src` instead.

> **Offline mock mode** is a keyword heuristic so everything runs without a key. It proves the plumbing, not prompt quality. Run the eval with a real key for meaningful results.

Resume and job-description files may be `.txt`, `.md`, `.pdf`, or `.docx`.
PDF and DOCX extraction uses `pypdf` and `python-docx`, installed by
`requirements.txt`. Scanned/image-only PDFs need OCR before analysis.

## Dashboard

Run the Streamlit dashboard from the project root:

```powershell
$env:PYTHONPATH="src"
python -m streamlit run app.py
```

The dashboard accepts `.txt`, `.md`, `.pdf`, `.docx`, and `.csv` resume files.
CSV uploads contain one resume per row with a required `resume_text` column and
an optional `candidate_id` column:

```csv
candidate_id,resume_text
candidate-1,"Backend engineer with Python experience..."
```

Dashboard limits:

- Scanned or image-only PDFs have no extractable text without OCR and cannot be analyzed.
- Provider free-tier quotas and the configured daily request budget limit real-model runs.
- There is no login or role-based access control.

Privacy notice: Resumes are sent to the configured AI provider. Use only synthetic
or consented data.

## Providers
- **Anthropic**: set `ANTHROPIC_API_KEY` and optionally `RA_PROVIDER=anthropic` and `RA_MODEL`.
- **Gemini**: use Google AI Studio by setting `RA_PROVIDER=gemini`, `GEMINI_API_KEY` (or `GOOGLE_API_KEY`), and `RA_GEMINI_MODEL` to a current model available to the key.
- **Offline mock**: set `RA_MOCK=1` to use the keyword heuristic without an API key.

## Running modes
### Real mode
Set the credentials and provider in `.env`. Anthropic requires API credits; API billing is separate from a claude.ai subscription. Gemini uses Google AI Studio quotas, which are separate from other Google subscriptions. Unless `RA_TEMPERATURE` is set, the SDK request does not include a temperature argument, so runs can vary slightly. This is why the code-side checks (quote verification, deterministic scoring, and tier rules) and the stability evaluation (`--runs 3`) matter.

An `analyze` run with a cold cache now makes about 2 model calls for extraction and scoring; recommendations are on demand. A warm cache makes 0 model calls for an identical resume and job. The Gemini client has a 60-second request timeout and prints progress for each request. Set `RA_API_TIMEOUT_MS` to change the timeout in milliseconds.

### Offline mock mode
Set `RA_MOCK=1` (PowerShell: `$env:RA_MOCK="1"`). This keyword heuristic proves the plumbing, not prompt quality.

## Free-tier usage
The persistent SQLite cache avoids repeating parsed-job and resume-analysis calls. Configure it with:

- `RA_CACHE_PATH`: SQLite cache location; defaults to `.cache/ra.sqlite3`.
- `RA_RPM`: maximum requests per minute pacing; defaults to `8`.
- `RA_DAILY_LIMIT`: local daily request budget; defaults to `200`.
- `RA_GEMINI_THINKING_BUDGET`: Gemini thinking-token budget; defaults to `0` when supported.

The local daily counter uses the Pacific-time date to match Gemini's quota reset. A Gemini daily quota error stops retries immediately; wait for the reset, enable billing, or use mock mode.

## Layout
- `prompts/` versioned prompts (shared system policy + 5 task prompts incl. LLM-judge)
- `src/resume_analyzer/` pipeline, sanitizer, scoring policy, models, mock
- `data/` job description + 5 test resumes (strong, career-changer, unrelated, prompt-injection, non-traditional/career-break)
- `eval/` golden expectations + harness (tier accuracy, ordering, injection, grounding, stability, judge)
- `tests/` unit tests for the deterministic parts
- `docs/PROMPT_DESIGN.md` techniques, rationale, risks, how to iterate
- [Operating policy](docs/OPERATING_POLICY.md)

## Evaluation results
Fill in this table after running `python eval\run_eval.py --runs 3 --judge`.

| Check | Mock mode | Real model |
|---|---|---|
| Tier accuracy | 5/5 | TODO |
| Ordering | 4/4 | TODO |
| Injection flagged | 1/1 | TODO |
| Evidence grounding | 0 capped claims (23 quotes) | TODO |
| Tier stability | 100% (3 runs) | TODO |
| Judge scores | Skipped (requires real model) | TODO |

Mock results are not evidence of prompt quality.

## Troubleshooting
- **`the following arguments are required: cmd`**: provide a subcommand, either `analyze` or `rank`.
- **`unexpected keyword argument 'temperature'`**: use the current `llm.py`, which only sends temperature when `RA_TEMPERATURE` is set.
- **`credit balance is too low`**: add credits in the Anthropic console, or use mock mode.
- **`model not found`**: set `RA_GEMINI_MODEL` to a current model name from AI Studio.
- **`429 RESOURCE_EXHAUSTED` or `You exceeded your current quota`**: the Gemini project has reached its available quota. Wait for the reset time reported by the API, enable billing or use a project with available quota, or run offline mock mode. Daily quota errors fail immediately instead of retrying for several minutes.
- **`IndentationError` after editing a file**: replace the whole file rather than patching a method.

## Limitations
- Only 5 synthetic resumes are included.
- Thresholds (75/60/40) are uncalibrated against recruiter-labelled data.
- PDF and DOCX text extraction is supported; scanned/image-only documents still need OCR.
- English only.
- Not validated for production hiring.

## Improvements needed

- Analysis should be made faster than the previous version. This remains a needed
  improvement and has not been marked complete.

## Future scope

- Improve analysis speed beyond the previous version.
- Add recruiter-labelled calibration.
- Run fairness validation on approved real data.
- Verify provider data-use and retention terms.
- Complete legal, privacy, security, and recruiter validation before any production use.
- Add login, role-based access, audit logging, and automatic deletion.

## Responsible use
Automated employment screening is regulated in many places (e.g. EU AI Act high-risk category, NYC Local Law 144, India's DPDP Act for personal data). Keep a human decision-maker, audit outcomes by group, disclose automation to candidates, and get legal review before production use.
