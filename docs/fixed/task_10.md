# Task 10: Fix Xero Rate Limiting (429) during Transaction Analysis

## Context
User reported a 429 Too Many Requests error from Xero during the Transactional Analysis stage:
`Could not extract deep data for Share of profit... Xero accounts failed: 429`

### Investigation
- The `analyze_nominal` endpoint in `app.py` calls `xero_client.get_accounts(tenant_id)` to resolve the `AccountID` from the `nominal` name.
- Since the frontend loops over selected nominals and calls this endpoint in rapid succession, it makes N requests to the `/Accounts` endpoint, rapidly hitting Xero's rate limit (60 calls/minute).
- [ ] Check `init_workbench` to see if we can fetch `/Accounts` once and map the `AccountID`s to the COA items sent to the frontend.

## Plan
- [ ] **Backend (`app.py`):**
    - Modify `init_workbench` to fetch `get_accounts()` ONCE and create a mapping of `Name`/`Code` to `AccountID`.
    - Include `account_id` in the `aiData.coa` payload sent to the frontend.
    - Update `analyze_nominal` to accept `account_id` directly, completely removing the `get_accounts` call from that endpoint.
- [ ] **Frontend (`templates/workbench.html`):**
    - Update the checkboxes to store BOTH the nominal name and the `account_id` (e.g., in a data attribute).
    - Update `runTransactionalAnalysis` to extract the `account_id` and pass it to `/api/workbench/analyze_nominal`.
