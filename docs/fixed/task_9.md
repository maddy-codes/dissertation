# Task 9: Implement Trial Balance Overview Stage

## Context
User reported: "before the nominals, I need to see the trail balance table, it's very very necessary!"
Previously, the user asked to remove balances from the COA selection list. Now they want a dedicated Trial Balance view before that selection happens.

## Investigation
- [ ] Current stages: Init -> Review (Flags) -> Scope (COA) -> Analysis -> Finalize.
- [ ] Need to insert "Trial Balance Review" as a new stage.
- [ ] The Trial Balance data is already fetched in `/api/workbench/initialize/<tenant_id>`.
- [ ] Need to expose the raw Trial Balance rows in the API response or ensure the frontend can render them.

## Plan
- [ ] **Backend (app.py):**
    - Ensure `init_workbench` returns the full Trial Balance data (including balances) in the JSON response, perhaps in a separate `tb_raw` field.
- [ ] **Frontend (templates/workbench.html):**
    - Add a 6th step to the indicators.
    - Insert Stage 3: "Institutional Trial Balance".
    - Update logic to transition: Review (Flags) -> Trial Balance -> Scope (COA).
    - Render a professional table showing Account, Code, Debit, Credit, and Net Balance.
- [ ] **Verification:**
    - Verify the TB table renders correctly with live data.
    - Verify stage transitions are smooth.
