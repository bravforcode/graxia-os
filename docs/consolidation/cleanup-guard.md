# Consolidation safety guard

The consolidation helpers are read-only. They produce evidence for a later
operator-approved GitHub archive/delete action; they do not call GitHub and do
not remove, move, or overwrite repositories.

## Secret scan

The scanner records only rule IDs, paths, line numbers, and (for reachable
history blobs) opaque Git object references. It never writes matched values.
The default working-tree scope is tracked files; add `--include-untracked` for
untracked files and `--include-ignored-sensitive` only when the ignored tree is
small enough to inspect. History is explicitly capped and the cap is included
in the JSON report.

```powershell
python scripts/secret_scan.py `
  --history `
  --max-history-commits 10 `
  --max-history-entries 100 `
  --repo "C:\Users\menum\graxia os" `
  --repo "C:\revenue_os" `
  --repo "C:\auto-post" `
  --repo "C:\Users\menum\ai-factory" `
  --output docs/consolidation/secret-scan-2026-09-17.json
```

`findings` are candidate matches, not proof that a value is live. Confirmed
or uncertain credentials must be rotated/revoked before live payment or
production release.

## Bundle verification

Before an archive/delete operation, create a local restore bundle through the
approved backup process, then verify it without publishing or deleting it:

```powershell
python scripts/repository_bundle_guard.py `
  --repo-name auto-post `
  --action merge-then-archive `
  --bundle C:\approved-backups\auto-post.bundle `
  --expected-head <40-lowercase-hex> `
  --output docs/consolidation/auto-post-bundle-verification.json
```

The guard rejects action mismatches and always rejects cleanup actions for
`krisphy` and `adminmate-ai`. The inventory must be re-fetched from GitHub
immediately before any external archive/delete request; this local guard is
not that approval.
