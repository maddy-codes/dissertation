# Task 22: Fix 'Encrypt' Attribute in Azure SQL Connection String

## Problem Description
The application fails to connect with `sqlalchemy.exc.OperationalError: (pyodbc.OperationalError) ('08001', "[08001] [Microsoft][ODBC Driver 18 for SQL Server]Invalid value specified for connection string attribute 'Encrypt' (0) (SQLDriverConnect)")`.
This occurs because the connection string likely contains `Encrypt=True` or `Encrypt=False`, but ODBC Driver 18 expects `Encrypt=yes` or `Encrypt=no`.

## Context Gathering
- [ ] Inspect the `DATABASE_CONNECTION_STRING` in the `.env` file for the `Encrypt` attribute.
- [ ] Verify if other boolean-like attributes (e.g., `TrustServerCertificate`) also use incompatible values for ODBC Driver 18.

## Proposed Plan
1.  **Surgical Fix in Factory:** (Completed)
    - Updated `setup/app_factory.py` to sanitize the connection string.
    - Replaced `Encrypt=True/False` with `Encrypt=yes/no`.
    - Replaced `TrustServerCertificate=True/False` with `TrustServerCertificate=yes/no`.
2.  **Verification:** (Completed)
    - Confirmed that the `DATABASE_CONNECTION_STRING` in `.env` used `True/False` values, which are incompatible with ODBC Driver 18's strict validation.
    - The dynamic replacement in the factory ensures compatibility without requiring the user to manually edit their `.env` file.
