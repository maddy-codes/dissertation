# Task 16: Refactor Year Selection to "Current Year End" and "Comparison Year End"

## Context
User reported: "also why is there a year start and year end.... both should be year ends and then the year start should be able to calculate from that."
Currently, `client_detail.html` has a "Comparative Year Start" field which is actually sending `comparison_year_end` data, and a "Current Year End" field.

## Plan
- [ ] **Frontend (`templates/client_detail.html`):**
    - Update the label "Comparative Year Start" to "Comparison Year End".
    - Update IDs and names for clarity if needed, but ensure they match `app.py` expectations.
- [ ] **Backend (`app.py`):**
    - Verify that the application uses these dates as year-end points.
    - Ensure start dates are calculated automatically (e.g., Year End - 364 days or similar logic).
    - Update `ReviewNote` model usage if "year_start" is misleading (it likely currently stores the comparison year end).
- [ ] **Verification:**
    - Check the UI labels.
    - Verify data flow from selection to analysis.
