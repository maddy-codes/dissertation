# Task 18: Audit Workbench UI/UX Enhancements and Materiality Configuration

## Problem Description
The user has requested several improvements to the audit workbench and configuration:
1.  **Trial Balance Flaggings:** Show transaction flaggings directly within the Trial Balance view to provide better context for accountants.
2.  **Section Consolidation:** Bring the "Comparatives" and "Scope Review" sections together into a single view.
3.  **Transaction Drill-down:** Enable clicking into flagged "cup" (Common Unit of Processing or similar) transactions that have been promoted to the analysis stage.
4.  **Configurable Materiality:** Allow the user to configure Global and Nominal materiality values directly.

## Context Gathering
- **Trial Balance Template:** Found in `templates/workbench.html` under `stage-tb`. Data is fetched via `/api/workbench/initialize/<tenant_id>`.
- **Flaggings:** Currently displayed in `stage-flags` (Stage 2) before the Trial Balance. AI generates these flags in `app.py`.
- **Comparatives:** The backend fetches comparison year data, but it's not prominently displayed in the workbench stages yet.
- **Scope Review:** This corresponds to `stage-coa` (Chart of Accounts Analysis) in `workbench.html`.
- **Materiality:** Defined in `experiments/types.py` and used in `experiments/context/materiality.py`. `app.py` uses a default policy.
- **CUP Transactions:** Still unclear if "cup" is a typo, but the goal is to enable drill-down into transactions that triggered flags or are being analyzed.

## Proposed Plan
1.  **Refactor Workbench Stages:** (Completed)
    - Eliminated `stage-flags` as a standalone stage.
    - Integrated "Anomaly Discovery" into `stage-tb`.
    - Integrated flag resolution logic into the Trial Balance section, with `btn-to-coa` unlocking only after resolution.
2.  **Enhance Scope Mapping with Comparatives:** (Completed)
    - Added "Prior Yr" column to Trial Balance and Chart of Accounts grids.
    - Updated backend `init_workbench` to fetch and provide prior year data.
    - Updated AI prompt to utilize comparative context for better recommendations.
3.  **Implement Materiality Configuration UI:** (Completed)
    - Created `modal-materiality` with Global and Nominal materiality inputs.
    - Passed these values to the `analyze_nominal` API.
    - Updated analysis prompt to use these thresholds for identifying outliers and critical items.
4.  **Transaction Drill-down:** (Completed)
    - Created `modal-transactions` for deep-dive into nominal ledgers.
    - Added "View Full Ledger" button to all analysis result cards.
    - Updated `analyze_nominal` to return the full list of transactions for modal population.
    - Added warning icons and highlighting to Trial Balance rows that match initial AI flags.
