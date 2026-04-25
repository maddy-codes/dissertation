# Task 2: Authentication and Client Management Overhaul

## Problem Statement
The current application logic uses a traditional login followed by a separate Xero synchronization step. The user wants to unify this:
1. **Simplified Authentication:** Login page should offer "Sign in with Password" and "Sign in with Xero" directly.
2. **Client-Centric Dashboard:** The dashboard should display a grid of connected clients (tenants) as cards.
3. **Add Client Flow:** A dedicated "+" card to initiate new Xero connections.
4. **Client Detail View:** A dedicated page for each client showing metadata and options to view history or start a new "page-by-page" review note generation.
5. **Multi-step Generation:** The workbench flow needs to be more structured, specifically asking for Year Start and Year End in a sequence.

## Context Discovery Required
- **Models:** How are users and Xero tokens currently stored? (`setup/models.py`)
- **Routes:** Current implementation of login and Xero callback. (`routes/auth_routes.py`)
- **Dashboard Logic:** How are connections listed? (`app.py` and `templates/index.html`)
- **Workbench Flow:** Current data entry for dates. (`templates/index.html` and `templates/workbench.html`)

## Initial Plan
1. **Database:** Update `User` and potentially add `Tenant` or `ReviewNote` models to track history and persistent client info.
2. **Auth:** Refactor `auth_routes.py` to support Xero as a primary login method and update scopes.
3. **UI - Login:** Update `login.html`.
4. **UI - Dashboard:** Refactor `index.html` into a "Mandate Selector" grid.
5. **UI - Client Detail:** Create a new template/route for `client_detail`.
6. **UI - Workbench:** Structured multi-step form for date configuration.
