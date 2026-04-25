# Task 17: Fix UnboundLocalError and Improve Batch Processing

## Context
User reported: `local variable 'target_account' referenced before assignment` for many nominals during analysis.
Also asked: "Why can't all of these be processed together...."

### Investigation
- In `app.py`, `analyze_nominal` skips the block that defines `target_account` if `account_id` is provided by the frontend.
- However, the code subsequently tries to use `target_account.get("Code")` to filter transactions.
- This causes an `UnboundLocalError`.

## Plan
- [ ] **Backend (`app.py`):**
    - Fix the logic in `analyze_nominal` to ensure `target_account` (specifically the `Code`) is always resolved, even if `account_id` is provided.
    - Leverage the `_GLOBAL_ACCOUNTS_CACHE` in `xero_api.py` to make this lookup instant and 429-free.
- [ ] **Batching Consideration:**
    - The user wants them processed "together".
    - Currently, each nominal is a separate HTTP request from frontend to backend.
    - I will optimize the backend to handle the lookup more efficiently.
    - I will check if I can group nominals, but for now, fixing the bug is priority.
