# xiarchitect — Enterprise Architecture Intelligence System

**From repository to architecture flow in one click.**

xiarchitect is an enterprise-grade architecture intelligence system that transforms any code repository into a fully understood, visually navigable architecture — automatically, locally, and with complete privacy.

## 🎯 What xiarchitect Does

When you run xiarchitect on any repository, it:

1. **Scans** the entire workspace safely using ignore rules and security filters
2. **Detects** languages, frameworks, databases, queues, workers, and infrastructure
3. **Classifies** every file into meaningful architectural roles
4. **Builds** a complete architecture graph with evidence for every connection
5. **Generates** clean, human-readable diagrams at multiple abstraction levels
6. **Exports** living documentation ready for README, wikis, or AI agents

## 🚀 Quick Start

### Installation

```bash
# From the xiarchitect directory
pip install -r requirements.txt

# Or install in development mode
pip install -e .
```

### Basic Usage

```bash
# Scan current directory
python -m xiarchitect scan

# Scan specific workspace
python -m xiarchitect scan --workspace /path/to/project

# Custom output directory
python -m xiarchitect scan --output docs/architecture
```

### Output

xiarchitect generates:

- `scan-report.json` — Complete file classification report
- `stack-summary.json` — Detected technology stack with evidence

## 📊 Current Status: v0.3.0 (Week 1-7 Complete)

### ✅ Implemented

- **Scanner Engine**: Full workspace traversal with ignore rules
- **File Classification**: Automatic role detection (API, service, model, task, etc.)
- **Stack Detection**: Technology detection from requirements.txt, package.json, docker-compose, etc.
- **Import Analysis**: Python import detection and resolution
- **Dependency Graph**: File-level dependency graph with evidence
- **C4 Model Diagrams**: Context, Container, and Component diagrams
- **Mermaid Generation**: Visual architecture diagrams
- **Privacy-First**: Local-only analysis, no external calls, secrets never read
- **CLI Interface**: Simple command-line interface with multiple commands

### 🚧 Coming Soon (v0.4-v1.0)

- Interactive webview explorer
- Architecture health scoring
- Risk detection
- AI-powered explanations (optional, local-first)
- Natural language queries
- SVG/PNG export

## 🏗️ Architecture

xiarchitect follows a strict modular architecture:

```
xiarchitect/
├── core/           # Core types, config, logger, errors
├── scanner/        # Workspace scanning engine
├── classifier/     # File classification and stack detection
├── analyzers/      # Language-specific analyzers (coming soon)
├── graph/          # Architecture graph builder (coming soon)
├── diagrams/       # Diagram generators (coming soon)
├── export/         # Export engines (coming soon)
└── cli.py          # Command-line interface
```

## 🔒 Privacy & Security

xiarchitect is **local-first by default**:

- ✅ All analysis runs on your machine
- ✅ No external network calls
- ✅ No code sent anywhere
- ✅ Secrets never read (.env, .pem, .key files are skipped)
- ✅ No telemetry
- ✅ Works fully offline

## 🎯 Design Principles

1. **Truth first. Visuals second. AI last.**
   - Static analysis produces facts
   - Facts have evidence
   - Evidence has file references and line numbers

2. **Every architecture claim has evidence**
   - No claim without proof
   - Confidence scores for every connection
   - Inferred relationships are marked as such

3. **Architecture ≠ Imports**
   - Raw file imports are signals, not architecture
   - xiarchitect elevates signals into clean architecture diagrams

4. **Local-first privacy is absolute**
   - Default behavior: no external network calls
   - Code never leaves the machine unless explicitly enabled

## 📖 Integration with Graxia

xiarchitect is designed to integrate seamlessly with the Graxia Revenue OS:

```bash
# Scan Graxia project
cd /path/to/graxia
python -m xiarchitect scan

# Output will be in docs/xiarchitect/
```

The system will automatically detect:
- FastAPI backend structure
- Celery workers and tasks
- SQLAlchemy models
- Service layer architecture
- Agent implementations
- Package structure

## 🛠️ Development

### Running Tests

```bash
# Unit tests (coming soon)
pytest tests/unit/

# Integration tests (coming soon)
pytest tests/integration/
```

### Project Structure

```
xiarchitect/
├── __init__.py
├── __main__.py
├── cli.py
├── requirements.txt
├── README.md
├── core/
│   ├── __init__.py
│   ├── types.py
│   ├── config.py
│   ├── logger.py
│   └── errors.py
├── scanner/
│   ├── __init__.py
│   ├── workspace_scanner.py
│   ├── file_walker.py
│   └── ignore_rules.py
└── classifier/
    ├── __init__.py
    ├── file_classifier.py
    └── stack_detector.py
```

## 📝 Roadmap

### Week 1-3: Scanner Engine ✅ COMPLETE
- Workspace scanning
- File classification
- Stack detection

### Week 4-5: Architecture Abstraction (In Progress)
- Raw dependency graph builder
- Architecture graph builder
- Component grouping
- Evidence compilation

### Week 6-7: Diagram Generation
- C4 model engine
- Mermaid generator
- Multiple diagram types

### Week 8-9: Interactive Explorer
- React webview
- Graph visualization
- Evidence inspector

### Week 10-12: Polish & Release
- Health scoring
- Risk detection
- Export engine
- AI explanations

## 🤝 Contributing

xiarchitect follows the master plan strictly. All contributions must:

1. Follow the architecture defined in the master plan
2. Include evidence-based analysis
3. Maintain local-first privacy
4. Include tests
5. Update documentation

## 📄 License

Proprietary — Graxia Intelligence OS

## 🙏 Acknowledgments

Built following the xiarchitect Enterprise Master Plan v2.0 — a comprehensive specification for enterprise-grade architecture intelligence.

---

**xiarchitect** — Truth first. Visuals second. AI last.
