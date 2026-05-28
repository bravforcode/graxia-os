# Beta Session — Operator Prep Checklist

## Purpose
Ensure the operator is fully prepared before conducting a beta session with a real tester. Do not proceed if any item is unchecked.

---

## 24+ Hours Before Session

### Environment Verification
- [ ] `git status --short` — only expected files modified
- [ ] Backend tests: `python -m pytest tests/test_beta_* -q` — all pass
- [ ] compileall: `python -m compileall backend/app` — clean
- [ ] Frontend build: `cd frontend && bun run build` — clean
- [ ] Alembic head: `python -m alembic heads` — `021_add_funnel_v5_models`
- [ ] Backend running: `curl http://localhost:8000/health` — 200 OK
- [ ] `/readiness/beta` — returns expected checks
- [ ] `/readiness/limited-beta-pilot` — returns expected checks
- [ ] Kill switch confirmed active: `KILL_SWITCH_ALL_EXTERNAL_BETA = True`
- [ ] No-live-payment mode confirmed: `NO_LIVE_PAYMENT_MODE = True`
- [ ] Production readiness confirmed: `PRODUCTION_READY = False`

### Tester Preparation
- [ ] Tester signed agreement received and filed
- [ ] Tester registered in BetaRegistry (in-memory)
- [ ] Tester has access URL for the staging frontend
- [ ] Tester has login credentials (manually created, no self-serve)
- [ ] Tester confirmed session time and duration
- [ ] Tester informed session will be guided (they follow operator's lead)

### Session Materials
- [ ] `BETA_SESSION_SCRIPT.md` — printed or open on second screen
- [ ] `BETA_SESSION_OBSERVATION_SHEET.md` — ready for note-taking
- [ ] Screen recording / note-taking tool ready (if permitted by tester)
- [ ] Timer ready for session duration tracking
- [ ] Feedback collection form or channel ready

---

## 1 Hour Before Session

### System Health
- [ ] Backend process is running (check terminal)
- [ ] Frontend process is running (check terminal)
- [ ] Redis is connected (if used)
- [ ] Database is accessible
- [ ] Quick smoke test: `bash scripts/beta_smoke.sh 2>&1 | head -20`

### Operator Readiness
- [ ] Operator has reviewed `BETA_OPERATOR_RUNBOOK.md` key sections
- [ ] Operator has reviewed `BETA_SESSION_SCRIPT.md` flow
- [ ] Operator knows how to use the BetaRegistry (add/pause/remove testers)
- [ ] Operator knows how to trigger kill switch (toggle env var + restart)
- [ ] Operator has `BETA_FEEDBACK_SUMMARY_TEMPLATE.md` ready for post-session

---

## 15 Minutes Before Session

- [ ] Check `/health` endpoint is responsive
- [ ] Check tester can log in (verify credentials)
- [ ] Confirm screen sharing / co-browsing tool is working
- [ ] Mute notifications not related to the session
- [ ] Have the session script ready to step through
- [ ] Confirm recording consent (if applicable)

---

## Post-Session (Immediate)

- [ ] Stop recording
- [ ] Save observation notes to `BETA_SESSION_OBSERVATION_SHEET.md`
- [ ] Collect tester feedback via the agreed channel
- [ ] Thank the tester and confirm next session (if applicable)
- [ ] Run verification: `scripts/beta_smoke.sh` — all checks pass
- [ ] Check logs for any unexpected errors during session
- [ ] Document session in `PHASE21_FIRST_BETA_SESSION_REPORT.md`

---

## If Anything Goes Wrong

| Symptom | Action |
|---|---|
| Backend down | Restart backend, verify health, resume if quick |
| Tester cannot log in | Reset credentials manually, verify in staging |
| Kill switch state changes to False | Immediately re-enable, investigate root cause, do NOT disable again |
| Tester reports seeing another user's data | **Immediately end session**, investigate, document as critical incident |
| Live provider accidentally enabled | **Immediately kill session**, revert config, investigate root cause |
| Tester wants to do something outside scope | Redirect, explain beta limits, document feature request |
