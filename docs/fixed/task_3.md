# Task 3: Xero Authentication Flow Refinement

## Problem Statement
The "Sign in with Xero" button on the login page currently requests accounting scopes immediately, which forces users to select an organization during the initial authentication phase. The user expects a pure SSO experience (Name/Email only) for login, with organization selection occurring only when explicitly "Adding a Client."

## Context Discovery
- `routes/auth_routes.py`: Currently uses a single `SCOPE` variable containing both identity (`openid`, `profile`, `email`) and accounting scopes.
- `xero_login` route in `routes/auth_routes.py` is used for both initial login and adding clients.
- Xero's OAuth2 implementation triggers the organization selector whenever any `accounting.*` scope is requested.

## Implementation Plan
1. **Scope Segmentation:**
   - Define `IDENTITY_SCOPES`: `["openid", "profile", "email"]` for the login page.
   - Define `ACCOUNTING_SCOPES`: `["openid", "profile", "email", "accounting.settings.read", "accounting.reports.profitandloss.read", "accounting.reports.trialbalance.read", "accounting.banktransactions.read", "offline_access"]` for adding clients.
2. **Route Separation:**
   - Keep `xero_login` for the "Sign In" flow (Identity only).
   - Create `xero_connect` for the "Add Client" flow (Full scopes).
3. **Template Updates:**
   - `login.html`: Ensure it points to the identity-only flow.
   - `index.html`: Ensure the "Add More Clients" card points to the full-scope flow.
4. **Callback Handling:**
   - Update `xero_callback` to gracefully handle tokens with or without accounting access.
