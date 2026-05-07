# Migration 001 — Explicit DDL Rewrite Guide

The current `001_enterprise_baseline.py` uses `Base.metadata.create_all(checkfirst=True)`
which is pragmatic but not fully reproducible from SQL alone.

To rewrite it with explicit DDL (required for compliance/audit):

## Step 1 — Capture production schema

```bash
pg_dump --schema-only \
  --no-owner \
  --no-privileges \
  --exclude-table=alembic_version \
  "${DATABASE_URL}" > /tmp/production_schema_dump.sql

wc -l /tmp/production_schema_dump.sql
```

## Step 2 — Convert to Alembic DDL

For each `CREATE TABLE` statement in the dump, convert to `op.create_table()` calls.

Example conversion:

**From pg_dump:**
```sql
CREATE TABLE public.users (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    email character varying(255) NOT NULL,
    hashed_password character varying(255) NOT NULL,
    role character varying(50) NOT NULL DEFAULT 'user',
    is_active boolean NOT NULL DEFAULT true,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now()
);
ALTER TABLE public.users ADD CONSTRAINT users_pkey PRIMARY KEY (id);
CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);
```

**To Alembic:**
```python
op.create_table(
    "users",
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
              server_default=sa.text("gen_random_uuid()")),
    sa.Column("email", sa.String(255), nullable=False),
    sa.Column("hashed_password", sa.String(255), nullable=False),
    sa.Column("role", sa.String(50), nullable=False, server_default="user"),
    sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
              server_default=sa.text("now()")),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
              server_default=sa.text("now()")),
)
op.create_index("ix_users_email", "users", ["email"], unique=True)
```

## Step 3 — Table creation order (dependency graph)

Create in this order (leaf tables first):
1. `users`
2. `contacts`
3. `opportunities`
4. `submissions` (depends on opportunities, contacts)
5. `content_drafts` (depends on opportunities, contacts)
6. `approval_requests`
7. `audit_log`
8. `knowledge_documents`
9. `knowledge_chunks` (depends on knowledge_documents)
10. `knowledge_items`
11. `job_postings`
12. `email_threads`
13. `email_messages` (depends on email_threads)
14. `network_interactions` (depends on contacts)
15. `contact_edges` (depends on contacts)
16. `assistant_tasks`
17. `automation_runs`
18. `cognitive_state`
19. `agent_tasks`
20. `agent_messages`
21. `scraper_health`
22. `scraper_runs`
23. `skill_profiles`
24. `outcome_patterns`
25. `scoring_weight_history`
26. `openclaw_usage`
27. `api_rate_limits`
28. `identity_snapshots`
29. `deploy_history`
30. `weekly_metrics`

## Step 4 — Test on blank database

```bash
createdb graxia_migration_test
DATABASE_URL="postgresql://localhost/graxia_migration_test" \
  python -m alembic upgrade head

pg_dump --schema-only --no-owner \
  "postgresql://localhost/graxia_migration_test" > /tmp/migrated.sql

diff /tmp/production_schema_dump.sql /tmp/migrated.sql
# Expected: zero diff (modulo table ordering)

dropdb graxia_migration_test
```

## Status

Current status: `create_all(checkfirst=True)` — pragmatic, works correctly.
DDL rewrite: requires access to production database for pg_dump.
