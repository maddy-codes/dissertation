# Task 7: Fix Chart of Accounts Fetching and Highlighting

## Context
User reported:
1. Chart of Accounts (COA) is not fully fetched (limited to 30 items currently).
2. Checkboxes on the COA page do not update the row highlighting (opacity) when toggled.
3. User wants "nothing more nothing less" than the COA, specifically requesting to remove the balance column.

### Investigation
- [ ] In `app.py`, the `init_workbench` function has a hard limit of 30 accounts.
- [ ] In `templates/workbench.html`, the `coa-row` uses `opacity-50` for "skip" items but doesn't toggle it on checkbox change.
- [ ] The grid layout in Stage 3 includes a "Balance" column which needs to be removed.
- [ ] The AI prompt in `app.py` limits to "exactly 5 Chart of Account items". This needs to be changed to handle the full list or a much larger subset if AI analysis is still desired for all.

## Plan
- [ ] **Backend (app.py):**
    - Remove the 30-item limit when extracting accounts from the Trial Balance.
    - Update the AI prompt to provide suggestions for *all* provided accounts rather than just 5.
- [ ] **Frontend (templates/workbench.html):**
    - Remove the "Balance" column from the header and row template.
    - Adjust the `grid-cols` definition to redistribute space.
    - Add an event listener to the COA checkboxes to toggle the `opacity-50` class on the parent `coa-row`.
- [ ] **Verification:**
    - Inspect the code to ensure the limit is gone and the listener is added.
