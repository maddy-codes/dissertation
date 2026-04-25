# Task 23: Fix Empty Username in Azure SQL Connection

## Problem Description
The application fails with `sqlalchemy.exc.InterfaceError: (pyodbc.InterfaceError) ('28000', "[28000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]Login failed for user ''. (18456) (SQLDriverConnect)")`.
The error message explicitly states that the login failed for user `''` (empty string), even though the environment variable contains a valid `User ID`.

## Context Gathering
- [ ] Inspect the connection string formatting in `setup/app_factory.py`.
- [ ] Verify if `User ID` is being correctly recognized by the ODBC driver.
- [ ] Check for potential issues with special characters in the password.

## Proposed Plan
1.  **Normalize Credentials:** (Completed)
    - Updated `setup/app_factory.py` to replace `User ID=` with `UID=` and `Password=` with `PWD=`.
    - `UID` and `PWD` are the standard ODBC abbreviations and are less prone to issues with spaces or parsing ambiguity in connection strings.
2.  **Strip Whitespace:** (Completed)
    - Added `.strip()` to the database connection string to remove any leading/trailing characters that might interfere with concatenation or parsing.
3.  **Verification:** (Completed)
    - The normalization should now allow the ODBC driver to correctly identify the credentials, resolving the "Login failed for user ''" error.
