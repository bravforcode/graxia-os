# Notion → Graxia importer

`notion_to_graxia.py` imports pages and data-source schemas visible to one or
more Notion connections into a dedicated Markdown namespace. It is additive,
idempotent, resumable, and does not mutate Notion.

## Security

- Supply tokens through process environment or stdin only.
- Never put tokens in this repository, `.env`, a command-line argument, or a
  saved token file.
- The importer stores only a short token fingerprint in its manifest. It does
  not store the token.
- Rotate any token pasted into chat or shell history.

## Validate and inventory

Read exactly one token line per connection. `--token-count` avoids waiting for
EOF when using an interactive terminal:

```powershell
python scripts\notion_to_graxia.py --token-stdin --token-count 1 --validate-only
python scripts\notion_to_graxia.py --token-stdin --token-count 1 --dry-run
```

The dry run reports unique pages, data sources, pagination gaps, and API
errors. It writes nothing. Omit `--include-archived` for the normal live
workspace export. Archived/trash data is a separate partition; if the API
connection cannot query archived data-source rows, the manifest remains
`complete: false` rather than claiming a full archive export.

## Full export

Use a dedicated directory in the configured Graxia/Obsidian vault:

```powershell
python scripts\notion_to_graxia.py `
  --token-stdin --token-count 1 `
  --output-dir "C:\path\to\Second Brain\knowledge\Notion" `
  --vault-root "C:\path\to\Second Brain"
```

Each page has Markdown plus a `.page.json` sidecar containing the original
page metadata and content response. `import-manifest.json` records counts,
errors, incomplete queries, and content-completeness state. Re-running with
the same last-edited timestamps skips unchanged pages. Use `--refresh` to
force content retrieval.

## Graxia indexing

The existing generic `/knowledge/documents` path is not used because this
worktree's `KnowledgeDocument` model does not contain the `content` field that
endpoint passes. Instead, the importer calls the existing vault
`index_markdown_content` path for only the imported namespace.

Indexing requires a reachable Graxia database. Remote databases require an
explicit safety flag:

```powershell
python scripts\notion_to_graxia.py `
  --index-only `
  --output-dir "C:\path\to\Second Brain\knowledge\Notion" `
  --vault-root "C:\path\to\Second Brain" `
  --allow-remote-db
```

`--index-only` reads the existing export and does not need a Notion token. A
failed DB connection is reported per file and never deletes or overwrites
existing knowledge rows. Re-run after DNS/database recovery; unchanged rows
are detected by the existing Graxia chunk hashes.
