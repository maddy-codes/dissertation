# Task 4: Fix Xero Authentication - Missing 'jwt' Module

## Context
User reported: "Xero Authentication Failed: No module named 'jwt' while logging in."

### Investigation
- `routes/auth_routes.py` imports `jwt` at line 115 to decode the `id_token` from Xero.
- `pip list` shows `PyJWT` is installed in the system/anaconda environment, but it is NOT listed in `pyproject.toml` dependencies.
- `uv.lock` does not contain `pyjwt`.
- The application environment (likely managed by `uv`) is missing the `PyJWT` package.

## Plan
- [ ] Add `PyJWT` to `pyproject.toml` dependencies.
- [ ] Run `uv lock` (or let `uv` handle it) to update `uv.lock`.
- [ ] Verify the fix by checking if `import jwt` works in the project environment.
