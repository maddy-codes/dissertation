# Task 13: Fix 500 Error in Transactional Analysis

## Context
User reported a 500 Internal Server Error on `/api/workbench/analyze_nominal/...`.
The likely cause is the `get_detailed_transaction_report` method in `xero_api.py` calling an endpoint that might not exist in the Xero API (`/Reports/DetailedTransactionReport`), causing a 404 which is raised as a RuntimeError and caught by the `analyze_nominal` try/except, resulting in a 500 error.

## Plan
- [ ] Check if `DetailedTransactionReport` exists in Xero API.
- [ ] If not, we might need to fallback to a different approach or see what the exact error is.
- [ ] Write the exact exception to a file to be 100% sure what the 500 error is.