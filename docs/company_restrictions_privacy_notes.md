# Company Restrictions, Privacy Notes, and Real Example References

This submission note summarises the firm-specific controls and privacy concerns that shaped the dissertation system and its supporting code.

## Company-specific restrictions and review triggers

- `10% materiality threshold`: the system should explain meaningful movements but avoid clutter from immaterial noise.
- `Mandatory comment accounts`: directors' remuneration, legal and professional fees, donations, entertaining, and bad debts must still be discussed even when the variance is small.
- `Directors' loan accounts`: overdrawn balances, repayments, and private expenditure need explicit review comments because they create tax and disclosure risk.
- `Related-party movements`: unusual balances involving directors, shareholders, or connected entities should be surfaced, not silently normalised.
- `Share issue / investment events`: the system should request paperwork and reconciliation support rather than guessing the final equity position.
- `Mileage, P11D, and benefits in kind`: unusual director or staff travel costs should be treated as review prompts.
- `R&D and specialist adjustments`: if a number depends on a later specialist report, the generated note should preserve that uncertainty.

## GDPR and privacy concerns

- `Purpose limitation`: prompts and outputs should be used only for year-end accounting review.
- `Data minimisation`: remove unnecessary names, addresses, and free-text identifiers before model calls.
- `Storage limitation`: temporary exports, validation CSVs, and prompt logs should follow retention rules and not be kept indefinitely.
- `Integrity and confidentiality`: use authenticated Xero/Azure channels and environment-managed secrets.
- `Human accountability`: generated notes remain drafts until reviewed by a qualified accountant.

Official sources checked on 4 May 2026:

- ICO guide to the data protection principles: <https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-protection-principles/a-guide-to-the-data-protection-principles/>
- Microsoft Azure OpenAI data, privacy, and security: <https://learn.microsoft.com/en-us/legal/cognitive-services/openai/data-privacy>

## Real generated example references

The dissertation appendix uses lightly redacted excerpts derived from real records in:

- `dissertation_material/exceptional_validation_data.jsonl`

Examples selected for the report include:

- unresolved share issue / investment paperwork
- GDPR-related compliance spend in operating expenses
- directors' loan account commentary

These are intentionally redacted in the dissertation so the report remains realistic without exposing unnecessary personal or commercial detail.

## Code examples referenced in the report

- GPT-5.4 validation harness: `experiments/prompt_engineering_gpt54.py`
- Data pipeline transformation logic: `experiments/data_pipeline.py`
- Dissertation-facing wrapper: `dissertation_material/datapipeline_code.py`
