# Graxia OS — CI Checklist

## Pre-Merge Gate

Every PR to `staging` or `main` must pass all checks below.

---

## 1. Backend Compile

```bash
cd backend
python -m compileall app
```

**Expected:** All Python files compile without syntax errors.

**Failure:** Fix syntax errors, missing imports, or invalid type annotations.

---

## 2. Backend Pytest (Linux)

```bash
cd backend
APP_ENV=testing python -m pytest tests -q --maxfail=5 --durations=30
```

**Expected:**
- **0 failures, 0 errors**
- Skipped tests are documented and justified
- Duration under 10 minutes

**Coverage requirement:** All new code paths must have corresponding tests.

**Known skips:**
- `test_vault_reader.py` (6 tests) — skipped on Windows only
- `test_obsidian_contracts.py` (2 tests) — skipped on Windows only

These tests **must run on Linux CI** to validate Obsidian integration.

---

## 3. Frontend Lint

```bash
cd frontend
bun run lint
```

**Expected:** 0 errors, 0 warnings.

**Failure:** Fix ESLint violations before merging.

---

## 4. Frontend Tests

```bash
cd frontend
bun run test
```

**Expected:** 47/47 tests pass (or current baseline + new tests).

**Failure:** Fix broken tests or update snapshots.

---

## 5. Frontend Build

```bash
cd frontend
bun run build
```

**Expected:** Build succeeds, output in `frontend/dist/`.

**Failure:** Fix TypeScript errors, missing imports, or bundling issues.

---

## 6. Docker Compose Validation

```bash
# Validate all compose stacks
docker compose -f docker-compose.yml config > /dev/null
docker compose -f docker-compose.yml -f config/docker-compose.dev.yml config > /dev/null
docker compose -f docker-compose.yml -f config/docker-compose.production.yml config > /dev/null
```

**Expected:** All compose files validate without errors.

**Failure:** Fix YAML syntax, missing env vars, or invalid service references.

---

## 7. Staging Smoke Tests (CI Only)

```bash
# Run after Docker stack is up
bash scripts/ops/smoke_tests.sh
```

**Expected:** All smoke tests pass (health check, API responses, DB connectivity).

---

## 8. Shell Script Validation

```bash
bash -n scripts/ops/*.sh
bash -n scripts/deployment/*.sh
```

**Expected:** All shell scripts have valid syntax.

---

## 9. Security Baseline (Optional)

```bash
# Check for known vulnerable dependencies
cd backend
pip-audit --requirement config/requirements.unified.txt
```

**Expected:** No high/critical severity vulnerabilities.

---

## CI Workflow Reference

The canonical CI workflow is defined in `.github/workflows/ci.yml`.

Current pipeline stages:
1. Backend compile + test
2. Frontend lint + test + build
3. Docker compose validation
4. Shell script validation
5. Smoke tests (post-deploy)

---

## Failure Recovery

| Failure | Action |
|---|---|
| Backend compile error | Fix syntax/imports in changed Python files |
| Backend test failure | Check test output; fix code or test expectations |
| Frontend lint error | Auto-fix with `bun run lint --fix` |
| Frontend test failure | `bun run test --reporter=verbose` for details |
| Frontend build failure | Check TypeScript errors; verify imports |
| Docker config invalid | Check YAML syntax; verify env files exist |
| Smoke test failure | Check service logs; verify database migrations applied |
