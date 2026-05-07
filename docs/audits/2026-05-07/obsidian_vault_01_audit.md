<opus_scratchpad>
  [SYSTEM_MAP] Persona: APEX-AUDITOR (Principal Architect / PKM Expert). Context: Obsidian Vault "Second Brain". Dependencies: PARA structure, AI integrations (.claude/skills, .ai), plugins (dataview, templater, smart-connections, local-rest-api, remotely-save, obsidian-git).
  [FIRST_PRINCIPLES] Deconstruct PKM: A Markdown knowledge base optimized for AI context hydration, programmatic access (Local REST API), and deterministic synchronization.
  [DOUBT_INJECTION] Failure points: Plaintext API keys in plugin configs (`smart-connections/data.json` confirmed to contain `api_key`), `obsidian-local-rest-api` potentially exposing the vault over local networks, and severe sync conflicts/race conditions between `obsidian-git` and `remotely-save`.
  [PLATFORM_CONSISTENCY] Verify Obsidian best practices: semantic markdown, strict frontmatter (YAML) compliance, modular templates, and cross-platform mobile parity.
  [IRON_WALL_TENANCY] N/A for SaaS, but critical for personal secrets: API keys MUST be extracted from sync paths or `.obsidian` must be strictly `.gitignore`'d and excluded from `remotely-save`.
  [AGENTIC_HYDRATION] Loaded context from `vault-lint` logic. Utilizing PROMPT 01 structure for rigorous x-ray.
  [THE_10X_PIVOT] Transition from a fragile personal notes folder to an Enterprise-grade Agentic Knowledge Graph (AKG) with strict CI/CD linting, secret management, and performant RAG endpoints.
</opus_scratchpad>

# 🦅 PROMPT 01: ULTRA PROJECT AUDIT
**Target**: Second Brain (Obsidian Vault)
**Persona**: APEX-AUDITOR

---

## 📊 PHASE 1: SCORED VAULT X-RAY

| Dimension | Score | Analysis |
| :--- | :---: | :--- |
| **1. Architecture (Folder/PARA)** | **8/10** | Strong foundational structure. PARA method (00-Inbox to 07-Daily) is explicitly defined. AI skills are heavily integrated but fragmented across multiple directories (`.claude/skills`, `skills/`, `brain/skills-universal/`). |
| **2. Code Quality (Markdown/YAML)** | **7/10** | High capability, but implicit risk of orphaned notes, broken wikilinks, and inconsistent YAML frontmatter across the aging knowledge graph. |
| **3. Security & Secrets** | **2/10** | **CRITICAL RISK.** Live scan confirms `api_key` exists in `.obsidian/plugins/smart-connections/data.json`. Synchronizing `.obsidian` via Git/Remotely Save risks leaking OpenAI/Anthropic keys to remote servers. |
| **4. Performance & Optimization** | **5/10** | Heavy plugin footprint (18 plugins). Concurrent usage of `omnisearch`, `dataview`, and `smart-connections` (local embeddings) will severely degrade mobile load times and spike RAM usage. |
| **5. Testing & Vault Health** | **4/10** | No automated CI/CD for the vault. Lacks automated linting for broken links, unlinked mentions, or Dataview query failures. |
| **6. Data Layer (Graph Integrity)** | **7/10** | Dataview usage implies structured metadata, but graph health requires aggressive pruning to prevent "tag soup" and unstructured sprawl. |
| **7. API Design (Templating)** | **9/10** | Elite workflow automation potential. The combination of `templater-obsidian`, `quickadd`, and `obsidian-local-rest-api` provides a robust headless interface for AI agents. |
| **8. DevOps & Synchronization** | **3/10** | **CRITICAL RISK.** Running `obsidian-git` AND `remotely-save` concurrently is an architectural anti-pattern. This will cause race conditions, duplicate file conflicts, and `.obsidian` workspace state corruption. |
| **9. Dependencies (Plugins)** | **6/10** | High dependency on complex, un-sandboxed community plugins. If `dataview` or `smart-connections` introduce a breaking update, core workflows halt. |
| **10. Documentation (Meta/Onboarding)** | **8/10** | `00-Meta` exists, indicating a self-aware system with guidelines and Maps of Content (MOCs). |

---

## 🚨 PHASE 2: MASTER ISSUE LIST (PRIORITIZED)

### 🔴 Priority 1: Critical (Immediate Action Required)
1. **Secret Leakage in Sync Channels**: API keys inside `smart-connections` (and potentially `copilot`) are stored in plaintext in `.obsidian/plugins/.../data.json`.
   * **Fix**: Immediately add `.obsidian/plugins/smart-connections/data.json` to `.gitignore` and `remotely-save` exclusion rules. Rotate the currently exposed API keys.
2. **Synchronization Race Condition**: Dual-syncing with both Git and Remotely Save.
   * **Fix**: Choose a single source of truth. Use `obsidian-git` for desktop-only version control and `remotely-save` (S3/WebDAV) for mobile cross-sync, but *never* overlapping the same directories simultaneously without strict exclusion rules.
3. **Local REST API Exposure**: `obsidian-local-rest-api` provides full CRUD access to the file system.
   * **Fix**: Ensure the API is bound *only* to `127.0.0.1` and verify the API key/TLS certificates are actively rotating and securely stored outside the sync envelope.

### 🟠 Priority 2: High (Fix in Next Sprint)
4. **AI Skill Fragmentation**: AI agent skills are scattered across `.claude/skills`, `skills/`, and `brain/skills-universal/`.
   * **Fix**: Consolidate all LLM/CLI skills into a single `00-Meta/Agents` or `.ai/skills` directory. Symlink if required by specific IDEs.
5. **Mobile Performance Bottlenecks**: `smart-connections` and `omnisearch` indexers running on mobile devices drain battery and freeze the UI.
   * **Fix**: Use `obsidian-style-settings` or separate `.obsidian.mobile` config folders to disable heavy indexing plugins on mobile clients.

### 🟡 Priority 3: Medium (Tech Debt)
6. **Frontmatter Standardization**: Inconsistent YAML metadata breaks `dataview` queries over time.
   * **Fix**: Introduce the `Linter` plugin (or run a custom Python script via CLI) to enforce a strict frontmatter schema (e.g., `aliases`, `tags`, `created`, `modified`, `status`) on file save.
7. **Graph Pruning**: Over-reliance on folders instead of semantic links.
   * **Fix**: Conduct a `vault-lint` audit to identify and resolve orphaned notes (notes with zero backlinks or outgoing links).

### 🟢 Priority 4: Low (Enhancements)
8. **Headless Agent Workflows**: Leverage `obsidian-local-rest-api` to allow background Python/Node scripts to append research to `00-Inbox` without opening the Obsidian GUI.

---

## 🚀 PHASE 3: THE 10X ARCHITECTURAL PIVOT

**The Shift: From Passive PKM to an "Agentic Knowledge Graph" (AKG)**

The current architecture is a highly capable but fragile personal wiki. By implementing the 10x Pivot, we transform this vault into a headless, AI-driven operating system:

1. **The Air-Gapped Sync Strategy**: Split the `.obsidian` configuration. Use `.obsidian` for desktop (heavy plugins, Git sync, Local REST API) and `.obsidian.mobile` for phone/tablet (lightweight, Remotely Save sync, UI optimized).
2. **Zero-Trust Secrets**: Strip all API keys from the vault. Use environment variables or a dedicated, un-synced `.env` file that plugins or external agentic scripts read from dynamically.
3. **Headless Orchestration**: Instead of relying solely on Obsidian plugins (which block the main UI thread), move heavy lifting (RAG indexing, web scraping, semantic connections) to background CLI agents (Gemini/Claude) that interact with the vault via `obsidian-local-rest-api` or direct file-system modifications.
4. **Universal Schema Validation**: Implement a pre-commit hook (via Git) that runs a Markdown/YAML linter. If a note lacks required metadata (status, tags), it is rejected. This guarantees pristine data for Dataview and AI context windows indefinitely.