# Task 19: Addressing Concurrency and Asynchronous Processing Issues

## Problem Description
The user has reported that the workbench still has concurrency issues and is not truly asynchronous. Specifically:
1.  **Concurrency Not Fixed:** Likely refers to the parallel execution of nominal analysis causing bottlenecks or race conditions.
2.  **Lack of Async:** The long-running API calls (Trial Balance fetch, AI analysis) are likely blocking the main thread or causing browser timeouts, rather than using a proper background job and polling system.

## Context Gathering
- [ ] Inspect `integrations/xero_api.py` for caching logic and potential bottlenecks in parallel calls.
- [ ] Check if `app.py` or `helpers/runners.py` has any infrastructure for background tasks (Prefect, etc.).
- [ ] Evaluate the frontend worker logic in `templates/workbench.html` for potential improvements.
- [ ] Identify which parts of the workflow should be moved to a truly async (background job) pattern.

## Proposed Plan
1.  **Backend Cache Locking:** (Completed)
    - Added `threading.Lock` to `XeroClient` in `integrations/xero_api.py`.
    - Implemented "Double-Checked Locking" pattern in `get_accounts`, `get_bank_transactions`, and `get_invoices` to prevent cache stampedes.
2.  **Parallelize Xero Fetches:** (Completed)
    - Updated `init_workbench` to fetch current and prior year Trial Balances in parallel using `ThreadPoolExecutor`.
    - Created a new `/api/workbench/prime_ledger` endpoint to broad-fetch all transactions for both years in parallel.
3.  **Frontend Workflow Refactoring:** (Completed)
    - Updated `workbench.html` to include a "Priming" step before nominal analysis.
    - Reduced nominal analysis concurrency from 10 to 5 to avoid hitting Azure OpenAI / Xero RPM limits.
    - Added status thoughts in the UI to keep the user informed during the priming phase.
