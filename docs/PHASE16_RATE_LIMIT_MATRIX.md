# Phase 16 Rate Limit Matrix

| Surface | Current limiter | Target rule | Key strategy | Safe error contract needed? | Test |
|---|---|---|---|---|---|
| auth login | `LOGIN_RULE = 10/60` in `backend/app/middleware/rate_limit.py` | keep route-specific auth cap | `ip:auth_login` | yes | `backend/tests/test_rate_limit.py` |
| auth register | `REGISTER_RULE = 5/60` | keep route-specific auth cap | `ip:auth_register` | yes | `backend/tests/test_rate_limit.py` |
| auth refresh | `REFRESH_RULE = 30/60` | keep route-specific auth cap | `ip_or_session:auth_refresh` | yes | `backend/tests/test_rate_limit.py` |
| generic API | `API_RULE = 600/60` | split by route class | `org+actor:route_group` | yes | `backend/tests/test_rate_limit.py` |
| health | generic/public | `120/min/ip` | `ip:health` | yes | `backend/tests/test_public_routes_rate_limit.py` |
| readiness | generic/auth | `120/min/ip` public or `actor:readiness` protected | `ip` or `org+actor` | yes | `backend/tests/test_staging_auth_readiness.py` |
| lead capture | no dedicated rule | `20/min/ip` + `100/hour/ip` | `ip+slug:lead_capture` | yes | `backend/tests/test_public_routes_rate_limit.py` |
| lead magnet deliver | no dedicated rule | `20/min/ip` + `100/hour/ip` | `ip+slug:lead_delivery` | yes | `backend/tests/test_public_routes_rate_limit.py` |
| checkout-completed webhook | no dedicated webhook rule | signed test-only + low burst | `webhook:checkout_completed:ip` | yes | `backend/tests/test_public_routes_rate_limit.py` |
| delivery token access | no dedicated fingerprint rule | `30/min/token_fingerprint` | `delivery:fingerprint` | yes | `backend/tests/test_customer_delivery_auth.py` |
| authenticated read APIs | generic API rule | `300/min/actor` | `org+actor:read_group` | yes | `backend/tests/test_rate_limit.py` |
| authenticated write APIs | generic API rule | `100/min/actor` | `org+actor:write_group` | yes | `backend/tests/test_rate_limit.py` |
| approvals resolve | generic API rule | lower write cap | `org+actor:approval_resolve` | yes | `backend/tests/test_route_protection_matrix.py` |
| MCP read | no registry-level limiter | `120/min/actor/tool` | `org+actor+mcp_tool` | yes | `backend/tests/test_mcp_rate_limit.py` |
| MCP write | no registry-level limiter | `30/min/actor/tool` | `org+actor+mcp_tool` | yes | `backend/tests/test_mcp_rate_limit.py` |
| workflow run | no workflow-specific limiter | `30/min/org/workflow` | `org+workflow_name` | yes | `backend/tests/test_workflow_rate_limit.py` |
| dangerous tools | blocked only | `0/min always blocked` | blocked | yes | `backend/tests/test_mcp_auth_enforcement.py` |

## Required implementation notes

- reuse `backend/app/middleware/rate_limit.py` as the primary local/test backend
- keep Redis support when available
- return `request_id` and `correlation_id` on 429
- never log raw customer delivery tokens

