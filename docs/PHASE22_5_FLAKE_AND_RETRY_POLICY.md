# Phase 22.5 — Flake and Retry Policy

## Rules

### 1. No blind retry to hide bugs
If a test fails, retry only once to classify as infrastructure flake. Do not retry silently.

### 2. One retry allowed for infrastructure flake classification
If the first attempt fails and the second passes, the result is `FLAKY_PASS`, not `PASS`.

### 3. Functional assertion failures are real failures
If the assertion logic is correct and the test fails, it is a real failure regardless of retry.

### 4. Browser failures require trace/screenshot
Any browser E2E failure must capture trace, screenshot, or video for debugging.

### 5. Startup port conflicts are infrastructure blockers
If a port is already in use, the test is `BLOCKED`, not a product failure.

### 6. Network unavailable is a blocker
If a required service is unreachable, the test is `BLOCKED`, not a product failure.

### 7. Retry does not change the assertion
The same assertion must be used on retry. No changing assertions between attempts.

## Results After Retry

| Attempt 1 | Attempt 2 | Verdict | Evidence Quality |
|---|---|---|---|
| PASS | (no retry) | PASS | Full |
| FAIL | PASS | FLAKY_PASS | Reduced — limitation logged |
| FAIL | FAIL | FAIL | Full |
| ERROR | PASS | FLAKY_PASS | Reduced |

## Implementation for Evidence

```python
# In evidence model:
ev.complete("FLAKY_PASS")  # Not PASS
ev.add_limitation("Passed on retry — classified as infrastructure flake")
```
