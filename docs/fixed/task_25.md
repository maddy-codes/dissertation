# Task 25: Trial Balance Line-by-Line Interactive Analysis

## Problem

The current UI uses an "Analyse by AI" button (labeled "Run AI Intelligence Scan" in the codebase) which analyzes all accounts simultaneously, taking too long. The user wants to replace this with an asynchronous, line-by-line interactive flow on the "Scope" screen (after Trial Balance is shown).

### Requirements:

1. **Remove the old button**: Replace the bulk AI scan button.
2. **Line-by-Line UI**: Load the TB line by line in the Scope definition stage.
3. **Drill-down (Right Arrow)**: Each line should have a drill-down arrow to view identified transactions.
4. **Selective Transactions**: The drill-down should not show all transactions, but specifically:
   - Subscriptions identified.
   - Outlying payments (present last time, not this time).
5. **Red Highlighting**: Highlight nominals/transactions in red that will be mentioned in the analysis. This is based on the guidelines in `@extra/Accounts Review Page Notes.docx`:
   - Directors Remuneration, Legal Fees, Sundry, Professional Fees, Donations, Entertainment, Bad Debts, New costs this year, Missing costs this year (were present last year), Profit/Loss on Assets, Deferred Tax, Fixed Assets additions/disposals, Stock, Debtors, Prepayments, Cash at bank, Creditors, PAYE CT and VAT, DLA.
6. **Async Batches**: Processing should happen in batches of 5-10 nominals at a time asynchronously.
7. **Draft Tasks (Persistence)**: Task should be registered as a "draft" so if the user clicks off, they can return to it.
8. **Auto-select**: Automatically see/select which ones to analyse based on the firm's guidelines.

## Context

- `templates/workbench.html`: Contains the frontend logic for `stage-tb` (Trial Balance) and `stage-coa` (Scope).
- The "Run AI Intelligence Scan" button makes a POST to `/api/workbench/analyze_scope/{tenantId}`.
- Currently, when we go from `stage-tb` to `stage-coa`, we render all COA rows at once and wait for the user to hit "Run AI Intelligence Scan".
- Draft tasks concept requires a DB model update or using an existing `Task` or `Run` model.

## Plan

1. **Model Update (if needed)**: Check `setup/models.py` to see if a draft/run state exists. We need a way to save "Draft" analysis scope.
2. **Backend API for Async TB Processing**: Create or update `/api/workbench/analyze_scope_batch` to process a batch of 5-10 nominals and return identifying info for highlighted nominals (and their transactions).
3. **Backend API for Drill-down**: Create an endpoint to fetch specific transactions (subscriptions, outliers) for a given nominal.
4. **Frontend Update (`workbench.html`)**:
   - On transition to `stage-coa`, automatically start fetching analysis in batches.
   - For each nominal, render a row. If it's a target (from guidelines), highlight it in red and auto-select it.
   - Add a right arrow `>` that opens a panel/modal showing the specific transactions.
5. **Guideline Logic**: Add logic to identify target nominals based on Account Name / Code.`
