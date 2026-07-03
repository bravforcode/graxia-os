# ADR-001: Record Architecture Decisions

## Status

**Accepted**

## Context

As quant_os grows in complexity, we need a lightweight, auditable mechanism to capture significant architectural decisions and their rationale. Without this, knowledge is lost to tribal memory, meeting notes, or PR descriptions that are hard to find later.

## Decision

We adopt **Architecture Decision Records (ADRs)** — short Markdown documents stored in `docs/architecture/` alongside the code they describe.

### Template

```markdown
# ADR-<NNN>: <Title>

## Status

<Proposed | Accepted | Deprecated | Superseded>

## Context

What is the issue motivating this decision? What forces are at play?

## Decision

What is the change? What are we actually doing?

## Consequences

Why is this a good idea? What trade-offs exist? What must team members be aware of?
```

### Lifecycle

| Status       | Meaning                                           |
|--------------|---------------------------------------------------|
| Proposed     | Under discussion, not yet final                   |
| Accepted     | Agreed and implemented                            |
| Deprecated   | No longer recommended but still in use            |
| Superseded   | Replaced by a newer ADR (reference it in context) |

## Consequences

- ADRs are numbered sequentially (`ADR-001`, `ADR-002`, ...)
- ADRs live in `docs/architecture/` and are committed to the main branch
- ADRs should be raised and reviewed alongside PRs that implement significant changes
- We keep ADRs concise — a few paragraphs per section, not essays
- Older ADRs are never deleted; they are marked `Deprecated` or `Superseded` if no longer relevant
