# xiarchitect Quick Start Guide

## Installation

```bash
# Navigate to xiarchitect directory
cd xiarchitect

# Install dependencies
pip install -r requirements.txt
```

## Basic Usage

### 1. Scan Your Project

```bash
# From project root
python -m xiarchitect scan --workspace ./graxia
```

This will:
- Scan all Python files in the graxia/ directory
- Classify files by architectural role
- Detect technology stack
- Generate reports in `docs/xiarchitect/`

### 2. Review Generated Reports

#### scan-report.json
```json
{
  "workspace_root": "C:\\Users\\...\\graxia",
  "total_files": 51,
  "classified_files": 51,
  "role_counts": {
    "database_model": 2,
    "api_route": 1,
    "documentation": 1,
    "unknown": 47
  }
}
```

#### stack-summary.json
```json
{
  "backend": [
    {"name": "FastAPI", "confidence": 0.95}
  ],
  "database": [
    {"name": "SQLAlchemy", "confidence": 0.90}
  ],
  "workers": [
    {"name": "Celery", "confidence": 0.95}
  ]
}
```

## Command Options

### Workspace Selection

```bash
# Scan specific directory
python -m xiarchitect scan --workspace ./graxia

# Scan current directory
python -m xiarchitect scan
```

### Output Control

```bash
# Custom output directory
python -m xiarchitect scan --output ./my-architecture-docs

# Default output: docs/xiarchitect/
```

### Performance Tuning

```bash
# Limit number of files
python -m xiarchitect scan --max-files 1000

# Adjust max file size (KB)
python -m xiarchitect scan --max-file-size 2048
```

## Understanding the Output

### File Roles

xiarchitect classifies files into these roles:

- `entrypoint` — Application entry points (main.py, app.py)
- `api_route` — API route handlers
- `api_middleware` — Middleware components
- `service` — Business logic services
- `database_model` — ORM models
- `background_task` — Celery/async tasks
- `agent` — AI agents
- `test` — Test files
- `config` — Configuration files
- `documentation` — Markdown/docs
- `unknown` — Not yet classified

### Technology Detection

Technologies are detected from:
- `requirements.txt` — Python packages
- `package.json` — Node.js packages
- `docker-compose.yml` — Infrastructure services
- `Dockerfile` — Base images
- Import statements — Framework usage
- Code patterns — Decorators, class patterns

### Confidence Scores

- `0.95-1.00` — Very high confidence (explicit declaration)
- `0.85-0.94` — High confidence (import detected)
- `0.70-0.84` — Medium confidence (dependency file)
- `0.50-0.69` — Low confidence (inferred)
- `0.00-0.49` — Very low confidence (guessed)

## Common Workflows

### 1. Initial Project Analysis

```bash
# Full scan
python -m xiarchitect scan --workspace ./graxia

# Review outputs
cat docs/xiarchitect/scan-report.json
cat docs/xiarchitect/stack-summary.json
```

### 2. Focused Analysis

```bash
# Scan only specific package
python -m xiarchitect scan --workspace ./graxia/packages/revenue_os
```

### 3. CI/CD Integration (Future)

```bash
# In CI pipeline
python -m xiarchitect scan --workspace . --output ./architecture-report
# Upload architecture-report/ as artifact
```

## Troubleshooting

### "No module named xiarchitect"

```bash
# Set PYTHONPATH
export PYTHONPATH=$PWD  # Linux/Mac
$env:PYTHONPATH="$PWD"  # Windows PowerShell

# Or install in development mode
cd xiarchitect
pip install -e .
```

### "Permission denied" errors

xiarchitect respects file permissions. If you see permission errors:
- Check file/directory permissions
- Run with appropriate user privileges
- Files are skipped if unreadable (logged as warning)

### Too many "unknown" classifications

This is expected in v0.1.0. Improvements coming in v0.2:
- Better pattern matching
- Content-based classification
- Framework-specific rules

### Missing technologies in stack summary

Check:
1. Is `requirements.txt` in the scanned directory?
2. Are imports present in scanned Python files?
3. Is `docker-compose.yml` present?

Technologies are detected from actual evidence, not guessed.

## What's Next?

### v0.2 — Architecture Graph (Coming Soon)

```bash
# Generate architecture graph
python -m xiarchitect analyze --workspace ./graxia

# Output: architecture-graph.json
```

### v0.3 — Diagram Generation (Coming Soon)

```bash
# Generate Mermaid diagrams
python -m xiarchitect diagram --workspace ./graxia --format mermaid

# Output: system-overview.mmd, container-diagram.mmd
```

### v0.4 — Interactive Explorer (Coming Soon)

```bash
# Launch interactive explorer
python -m xiarchitect explore --workspace ./graxia

# Opens web browser with interactive graph
```

## Examples

### Example 1: Graxia Revenue OS

```bash
$ python -m xiarchitect scan --workspace ./graxia

🔍 xiarchitect — Scanning workspace: /path/to/graxia

📂 Step 1/3: Scanning workspace...
   ✓ Scanned 51 files

🏷️  Step 2/3: Classifying files...
   ✓ Classified 51 files
   Top roles:
     - unknown: 47
     - database_model: 2
     - api_route: 1

🔧 Step 3/3: Detecting technology stack...
   ✓ Detected 0 languages
   ✓ Detected 1 backend technologies
   ✓ Detected 1 database technologies

📊 Technology Stack Summary:

  Backend:
    • FastAPI (95% confidence)
  Database:
    • SQLAlchemy (90% confidence)
  Workers:
    • Celery (95% confidence)

✅ Architecture intelligence generated in: docs/xiarchitect
```

### Example 2: Custom Configuration

```bash
# Scan with custom settings
python -m xiarchitect scan \
  --workspace ./graxia \
  --output ./architecture \
  --max-files 500 \
  --max-file-size 512
```

## Tips & Best Practices

1. **Run from project root** — Ensures correct relative paths
2. **Review scan-report.json first** — Understand what was scanned
3. **Check confidence scores** — Higher is better
4. **Ignore "unknown" for now** — Will improve in v0.2
5. **Keep outputs in docs/** — Standard location for documentation

## Getting Help

1. Check `xiarchitect/README.md` for full documentation
2. Review `docs/xiarchitect/INTEGRATION.md` for Graxia-specific info
3. Check generated JSON files for detailed data
4. Review xiarchitect master plan for roadmap

## Version

Current: **v0.1.0** (Week 1-3 Complete)

Next: **v0.2.0** (Architecture Graph — Week 4-5)

---

**xiarchitect** — Enterprise Architecture Intelligence System
