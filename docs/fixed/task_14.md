# Task 14: Implement Concurrent Transactional Analysis

## Context
User reported: "why is the data being fetched and fed to AI one by one.. I want concurrency atleast 15 at once... if that makes sense.."

### Investigation
- The current implementation in `templates/workbench.html` uses a `for` loop with `await fetch(...)` which processes each nominal sequentially.
- To improve speed, we need to process these requests concurrently with a limit (e.g., 15).

## Plan
- [ ] **Frontend (`templates/workbench.html`):**
    - Rewrite `runTransactionalAnalysis` to use a concurrency control mechanism (e.g., a simple queue or `Promise.all` with chunking).
    - Ensure the UI still updates correctly as each request finishes (appending cards, updating the current count).
- [ ] **Verification:**
    - Check the JS syntax and logic.
