# Task 8: Implement Interative Transactional Analysis Stage

## Context
User wants a new interactive stage after Chart of Accounts (COA) approval:
1. For each approved nominal code, pull 2 years of transactions.
2. Apply materiality filtering.
3. Identify Subscriptions (name, account, current vs previous).
4. Identify Outlier Payments (current vs previous).
5. Display these results "one by one" in the UI before finalization.

## Investigation
- [ ] Check `app.py` for existing transaction fetching logic.
- [ ] Check `experiments/context/` for subscription and materiality logic.
- [ ] Identify where to insert the new "Analysing Transactions" stage in `templates/workbench.html`.
- [ ] Create a new API endpoint to process transactions for a specific nominal code.

## Plan
- [ ] **Backend (app.py / helpers):**
    - Create `/api/workbench/analyze-transactions/<tenant_id>` endpoint.
    - Logic to fetch transactions for specific accounts.
    - Logic to identify recurring payments (subscriptions) and outliers.
- [ ] **Frontend (templates/workbench.html):**
    - Insert Stage 4: "Transactional Deep-Dive".
    - Update Stage 3 button to transition to Stage 4.
    - Implement JS loop to analyze selected nominals one-by-one and display progress/results.
    - Update Stage 4 button to transition to the final "Finalize" stage (now Stage 5).
- [ ] **Verification:**
    - Verify the API returns structured data for subscriptions/outliers.
    - Verify the UI transitions and renders the new stage correctly.
