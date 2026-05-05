# Dissertation Viva Script

This script is designed for a recorded viva of about 16 to 18 minutes, leaving a little slack for the live system demo while staying under the 20-minute guidance.

## Slide 1 - Title and thesis (1 minute)

"Hello, my name is Jatin Arora, and this dissertation is titled *Automating Year-End Accounting Notes: An AI System to Generate Audit-Ready Financial Statement Notes from Xero Data*. My supervisor is Dr. Mu. Mu.

The problem I set out to solve is that year-end review-note drafting takes a meaningful amount of accountant time, but it is still too sensitive to hand over entirely to a language model. So the project is not about autonomous filing. It is about building a reviewer-facing AI assistant that can produce a useful first draft while keeping the numeric layer deterministic and auditable.

The three threads running through the project are deterministic accounting control, multi-agent orchestration, and evidence-based evaluation. I will explain the system, show how I evaluated it, and then demonstrate the application itself."

## Slide 2 - Why this matters (1.5 minutes)

"The motivation came from real accounting workflow friction. In the baseline survey, the midpoint average time per review note was about 2.35 hours. Eight out of 10 respondents reported spending at least one hour per note, and half of them reported two hours or more.

What makes this interesting is that the workload is not just repetitive text entry. The hard notes involve judgement-heavy areas such as fixed assets, accruals and prepayments, related parties, and directors' loan accounts. So an AI system here has to do two things at once: save time, but also remain reviewable and professionally defensible.

That is why I framed the output as a draft for a human accountant, not a finished answer that bypasses review."

## Slide 3 - Aim, objectives, and questions (1.5 minutes)

"The overall aim was to design, build, and evaluate an AI-assisted system that drafts UK year-end accounting review notes from Xero-derived data.

There were three core objectives. First, I needed a deterministic processing layer so that material numbers came from code rather than language-model arithmetic. I refer to that throughout the dissertation as the Decimal Mandate. Second, I built a multi-agent orchestration layer to separate extraction, drafting, and review roles. Third, I compared prompt engineering and fine-tuning using real outputs, real timings, and human evaluation.

That led to three central research questions: whether drafting can be accelerated without losing numeric fidelity, whether the multi-agent structure improves accounting-style output, and which model strategy makes most sense in practice."

## Slide 4 - Architecture (1.5 minutes)

"This slide shows the high-level system architecture. The important design choice is the separation between deterministic accounting logic and narrative synthesis.

The left side of the pipeline deals with data intake and structured processing. Xero and supporting records are parsed and normalised. The deterministic layer calculates the numeric backbone, material variances, and structured evidence. Only after that does the multi-agent layer produce the narrative draft.

That means the model is not being asked to invent calculations. It is being asked to turn controlled, prepared evidence into an accountant-style note. This is a more defensible use of a language model in a finance setting because it narrows the surface area where hallucination can do damage."

## Slide 5 - Data pipeline, restrictions, and privacy (1.5 minutes)

"The next important part is the data pipeline and control environment. I wanted the codebase and the dissertation to show clearly where data comes from, how training and validation files are constructed, and where privacy controls sit.

The data-pipeline side prepares JSONL datasets from storage and Xero-enriched working-paper material. Alongside that, the privacy and restrictions flow shows the professional boundaries: no autonomous filing, masking or redaction before model-facing dataset use, and company-specific restrictions that identify mandatory review triggers.

This matters for GDPR and confidentiality. Even if the model output looks useful, the workflow still has to minimise client data exposure and keep professional accountability with the reviewer.

This is also why Azure matters in the project. Azure was chosen not just because it was technically convenient, but because the system needed an enterprise platform with stronger protection boundaries for confidential company data. For the same reason, I am not submitting live .env files or active credentials with the repository. The code is included, and the connected system demo is available on request under supervised conditions."

## Slide 6 - Application workflow and planned demo (1.5 minutes)

"This slide shows the user-facing application flow I will demonstrate in the recorded viva. The journey is simple on purpose: secure login, client selection, period selection, note generation, and then report inspection.

In the demo I will focus on four things. First, how the user initiates the review flow. Second, how the system shows progress during the multi-agent pipeline. Third, what the generated report looks like. And fourth, where the accountant is expected to intervene, edit, or escalate.

That is important because the dissertation is not just a model experiment. It is a working system with an intended professional workflow."

## Slide 7 - Fine-tuning runs (1.5 minutes)

"This slide brings together the three main fine-tuning runs. I added all of them because a dissertation should not imply that one neat result tells the whole story.

The summary chart shows the final run metrics. Two runs converged to materially stronger profiles than the weaker third run. FT1 ended at a loss of 1.27 with mean token accuracy of 0.69, FT2 ended at 1.36 and 0.67, and the third run was weaker at 1.88 and 0.60.

These training metrics help narrow the candidate set, but they are not the only basis for choosing a model. The more important decision came from live benchmark behaviour, where GPT-4.1 Fine-Tuned 2 proved to be the strongest reviewer-facing option."

## Slide 8 - Representative output comparison (1.5 minutes)

"This slide focuses on output character rather than speed. I compared a real accountant reference note with prompt-engineered GPT-5.4 output and the selected fine-tuned model output.

The accountant reference is query-led and professionally specific. The prompt-engineered baseline often produced a broader checklist style. GPT-4.1 Fine-Tuned 2 was more concise and structurally stable, but it still needed reviewer judgement for difficult edge cases.

This matters because latency alone is not enough. The better deployment is the one that produces a usable draft without creating new review risk."

## Slide 9 - Live benchmark timings (1.5 minutes)

"This slide focuses only on timing. I ran a live benchmark across all seven tested methods on representative validation cases, and the point here is that the timings are real measured values from the dissertation workflow rather than invented examples.

The GPT-5.4 prompt-engineering baselines averaged around 64 to 72 seconds depending on the prompt condition. GPT-4.1 Fine-Tuned 2 averaged 12.4 seconds, and Fine-Tuned 1 averaged about 15 seconds. So the strongest fine-tuned deployments clearly improved responsiveness.

However, the timings are only useful because they are presented alongside behavioural stability. One of the fine-tuned deployments became unstable and expanded to the output ceiling. So my conclusion is not simply that fine-tuning is faster. It is that fine-tuning is useful when the deployment remains controlled and structurally stable."

## Slide 10 - Human evaluation (2 minutes)

"The human evaluation stage used GPT-4.1 Fine-Tuned 2 as the reviewer-facing model. I chose that model because it had the best combination of stable output length, usable structure, and low latency in the live benchmark.

The evaluation included 10 professional respondents. The mean scores were strong for professional tone, flow, variance coverage, and mandatory-point inclusion. The trust score was lower, at 3.3 out of 5, which is actually a sensible result for this domain.

The interpretation is not that the model is ready to replace the accountant. The interpretation is that it is useful as a first-draft accelerator. Reviewers still expect to edit for specificity, style, and final judgement, but the system appears to reduce the amount of blank-page drafting work."

## Slide 11 - Limitations, GDPR, and future work (1.5 minutes)

"I also tried to be explicit about the limitations. The live benchmark was based on a three-case subset, so the timing results are informative rather than exhaustive. The human study involved a real professional context, but it is still a small sample.

From a governance perspective, GDPR and confidentiality remain central. Model-facing data needs to be minimised and controlled, and the workflow must keep human responsibility with the accountant. That is why the system produces drafts and escalation prompts rather than final statutory outputs.

The obvious future work is to expand the benchmark set, deepen firm-specific restriction logic, and test whether retrieval-based evidence packaging can improve reviewer trust without making the system too slow. It also remains important to preserve the current security posture: enterprise-hosted infrastructure for company data, no public release of live credentials, and controlled access to the connected demo."

## Slide 12 - Conclusion and recommendation (1 minute)

"To conclude, the dissertation supports the use of AI as a reviewer-facing drafting assistant for year-end accounting notes, but only inside a controlled human review workflow.

The main technical contribution is the combination of deterministic accounting logic, multi-agent orchestration, and evidence-based benchmarking. The main practical contribution is a working system and codebase that line up with the written report.

If I were to recommend one deployment from this project for continued use, it would be GPT-4.1 Fine-Tuned 2. It is the best overall trade-off between speed, output stability, and professional usefulness. I will now move into the short system demonstration and show how that looks in the application itself."

## Demo walkthrough (3 to 4 minutes)

1. Open the login page and briefly state that the application is intended for authenticated professional use.
2. Show the client-selection screen and explain that the workflow is client and period specific.
3. Open the date or setup screen and describe how the note request is defined.
4. Trigger or show the report-generation stage and mention the multi-agent progress updates.
5. Open the report view and point out:
   - the narrative draft,
   - the accountant review points,
   - where professional judgement still sits.
6. Close by linking the demo back to the dissertation claim: faster first drafts, but still human-reviewed and evidence-led.
