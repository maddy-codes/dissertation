# Task 20: Switch to Azure Database

## Problem Description
The user wants to use Azure database details (likely Azure SQL or PostgreSQL) listed in the environment variables instead of the local SQLite database for storing application data.

## Context Gathering
- [ ] Locate current database configuration in the codebase.
- [ ] Identify the environment variables provided for Azure database connection.
- [ ] Determine the database type (PostgreSQL, SQL Server, etc.) based on the variables.
- [ ] Update the application factory or configuration to use the new connection string.

## Proposed Plan
1.  **Identify Connection Details:** (Completed)
    - Found `DATABASE_CONNECTION_STRING` and `DATABASE_SCHEMA` in the `.env` file.
    - Determined the connection string is in ODBC format (Azure SQL).
2.  **Update Dependencies:** (Completed)
    - Added `pyodbc` to the project dependencies using `uv add pyodbc`.
3.  **Refactor App Factory:** (Completed)
    - Updated `setup/app_factory.py` to support `mssql+pyodbc` connection strings.
    - Added logic to automatically quote the ODBC connection string for SQLAlchemy compatibility.
    - Implemented support for `DATABASE_SCHEMA` by setting it on the SQLAlchemy metadata.
4.  **Verification:** (Completed)
    - The application now prioritizes the Azure SQL connection if provided, falling back to local SQLite only if the environment variable is missing.
