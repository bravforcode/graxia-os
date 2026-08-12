# Beta Kill Switch — Operator Standby Check

## Purpose
Before every beta session, the operator MUST verify the kill switch is active, tested, and the operator knows how to trigger it. This is a **non-negotiable safety gate**.

---

## Pre-Session Verification

Run these checks BEFORE every beta session:

### Config Check
```bash
# Check kill switch is locked
python -c "from app.config import Settings; s=Settings(); print('KILL_SWITCH_ALL_EXTERNAL_BETA =', s.KILL_SWITCH_ALL_EXTERNAL_BETA)"
# Expected: True
```

### Readiness Endpoint Check
```bash
curl -s http://localhost:8000/readiness/limited-beta-pilot | python -m json.tool
# Verify: kill_switch_ready = true in the output
```

### Smoke Test
```bash
bash scripts/beta_smoke.sh
# Verify: Kill switch tests pass
```

---

## Kill Switch Behavior

| State | Effect |
|---|---|
| `KILL_SWITCH_ALL_EXTERNAL_BETA = True` | All beta APIs return safe disabled response. No beta workflows start. MCP beta tools blocked. Operator UI shows beta disabled. |
| `KILL_SWITCH_ALL_EXTERNAL_BETA = False` | Beta features can be enabled per flag. Must be explicitly set by operator in controlled environments. |

**During Phase 21, kill switch MUST remain `True` (locked).**

---

## How to Toggle Kill Switch (Emergency Only)

### Step 1 — Identify the trigger event
Only toggle kill switch if one of these occurs:
- Cross-tester data leak detected
- Live provider accidentally called
- Payment system accidentally invoked
- Security vulnerability exploited
- Unauthorized data access

### Step 2 — Toggle
**Option A — Environment variable override (restart required):**
```bash
export KILL_SWITCH_ALL_EXTERNAL_BETA=true
# Restart backend
```

**Option B — Config file change (restart required):**
Edit `backend/app/config.py`:
```python
KILL_SWITCH_ALL_EXTERNAL_BETA: bool = True  # Must remain True
```

### Step 3 — Verify
```bash
curl -s http://localhost:8000/readiness/beta | python -c "import sys,json; d=json.load(sys.stdin); print('kill_switch_ready:', d.get('checks',{}).get('kill_switch_ready','NOT FOUND'))"
# Expected: kill_switch_ready: True
```

### Step 4 — Investigate
After kill switch is confirmed active, investigate the trigger event. Do NOT disable kill switch until root cause is fully understood and remediated.

---

## Kill Switch Drill (Operator Practice)

Run this drill at least once before the first beta session:

### Drill Steps
1. [ ] Verify kill switch is `True` by config check
2. [ ] Verify `/readiness/limited-beta-pilot` returns `kill_switch_ready: true`
3. [ ] Simulate a blocked beta API call (e.g., POST to a beta endpoint)
4. [ ] Verify the blocked response is safe (no stack trace, no secrets)
5. [ ] Practice the toggle procedure (mentally — do NOT actually toggle)
6. [ ] Document that the drill was completed

### Drill Record
```json
{
  "drill_date": "2026-05-29",
  "operator": "operator-name",
  "pre_session": true,
  "kill_switch_verified": true,
  "blocked_response_verified": true,
  "toggle_procedure_practiced": true,
  "notes": ""
}
```

---

## Emergency Contacts

| Role | Contact |
|---|---|
| Operator | [operator contact] |
| Backend engineer | [engineer contact] |
| Security contact | [security contact] |

---

## Post-Incident Checklist

After any kill-switch-related incident:
- [ ] Document the trigger event
- [ ] Document when kill switch was verified active
- [ ] Document any data exposure (even potential)
- [ ] Root cause analysis completed
- [ ] Remediation applied
- [ ] Kill switch re-verified active
- [ ] Incident reported to operator log
- [ ] Beta tester notified (if applicable)
