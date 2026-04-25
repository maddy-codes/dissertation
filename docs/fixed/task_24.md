# Task 24: Formalize Task Lifecycle Instructions

## Problem Description
The user wants to standardize the workflow for handling tasks. Currently, the documentation mentions creating `task_N.md` files but lacks a step-by-step enforcement of defining the problem, gathering context, and planning before execution.

## Context Gathering
- `GEMINI.md` contains the primary development conventions.
- `docs/fixed` contains 23 tasks, indicating the next task should be 24.
- `docs/problems` is the designated staging area for active tasks.
- The user specified a sequence: Create file -> Define Problem -> Save -> Create Context -> Save -> Define Plan -> Save -> Fix -> Move to Fixed.

## Proposed Plan
1.  **Update GEMINI.md:** Add the strict multi-step task tracking instruction to the Documentation section.
2.  **Verify Synchronization:** Ensure no conflicting instructions exist in other core files (e.g., `strings/assistant.py`).
3.  **Completion:** Move this task file (`task_24.md`) to `docs/fixed` as a demonstration of the new workflow.
