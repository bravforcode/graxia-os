<opus_scratchpad>
  [SYSTEM_MAP] Persona: MASTER-PLANNER. Map context: Obsidian Vault PKM.
  [FIRST_PRINCIPLES] Deconstruct audit findings into executable tasks for a single user/AI agent.
  [DOUBT_INJECTION] How does the plan fail? Overly complex sync rules? Broken skills paths?
  [PLATFORM_CONSISTENCY] Verify Obsidian best practices.
  [IRON_WALL_TENANCY] N/A, but strict secret isolation is critical.
  [AGENTIC_HYDRATION] Loading PKM planning skills.
  [THE_10X_PIVOT] Synthesize a flawless roadmap for creating an Agentic Knowledge Graph.
</opus_scratchpad>

# Comprehensive Implementation Plan: Second Brain (Obsidian Vault)

## Stakeholder Summary
This implementation plan addresses critical security and synchronization vulnerabilities within the Second Brain (Obsidian Vault) project. It outlines a structured, phased approach to fortify the local API, standardize synchronization channels, optimize mobile performance, and unify scattered AI skills. Total effort is estimated at 24 dev-hours, structured to be completed efficiently by a solo engineer and AI agents over a 1-week sprint.

---

## Phase 0: Emergency & Security (Immediate Action)
**Goal:** Seal secret leakage, resolve synchronization conflicts, and secure local API exposure.
**Estimated Time:** 6 hours

### Task 0.1: Remediate Secret Leakage in Sync Channels
- **Ref:** [C-01]
- **Description:** Remove API keys and sensitive credentials from plugin `data.json` files.
- **Action Items:**
  - Audit all `data.json` configurations in the `.obsidian/plugins` directory for hardcoded secrets.
  - Extract keys to an isolated `.env` equivalent or use Obsidian's secure local key storage mechanisms if available.
  - Add `.obsidian/plugins/*/data.json` containing secrets to `.gitignore`.
- **Acceptance Criteria:** No API keys exist in plain text within synced vault configuration files.

### Task 0.2: Resolve Synchronization Race Conditions
- **Ref:** [C-02]
- **Description:** Fix the race conditions between Obsidian Git and Remotely Save plugins.
- **Action Items:**
  - Decide on a primary sync mechanism (either Git OR Remotely Save) for the master graph.
  - If both are required, configure Remotely Save to only sync mobile-specific folders and configure Obsidian Git to handle core desktop commits.
  - Implement a cron or delayed startup script to prevent simultaneous sync triggers on application load.
- **Acceptance Criteria:** Vault can be launched and synced on mobile and desktop without generating duplicate conflict files.

### Task 0.3: Secure Local REST API Exposure
- **Ref:** [C-03]
- **Description:** Restrict network binding and implement key rotation for Local REST API.
- **Action Items:**
  - Reconfigure Local REST API to bind exclusively to `127.0.0.1` instead of `0.0.0.0`.
  - Rotate the current API key and implement a script for easy key regeneration.
  - Verify TLS/SSL certificates if the API is exposed over the local network.
- **Acceptance Criteria:** The local REST API is inaccessible from external network devices and uses a freshly rotated authentication key.

---

## Phase 1: Architecture & Foundation
**Goal:** Consolidate AI skill files and standardize metadata structures.
**Estimated Time:** 9 hours

### Task 1.1: Unify AI Skill Fragmentation
- **Ref:** [H-01]
- **Description:** Consolidate fragmented AI skills from `.claude/skills`, `skills/`, and `.gemini/` into a unified directory structure.
- **Action Items:**
  - Create a central `System/AI/Skills` directory in the vault.
  - Migrate all existing skills to this folder, ensuring path references in CLI configurations are updated globally.
  - Add a master `index.md` (MOC) mapping all available agentic skills and their triggers.
- **Acceptance Criteria:** All AI skills are centrally located, properly referenced by agent profiles, and documented.

### Task 1.2: Standardize Frontmatter (YAML)
- **Ref:** [M-01]
- **Description:** Normalize frontmatter across the vault to fix inconsistent YAML schemas.
- **Action Items:**
  - Define a strict YAML schema (e.g., `aliases`, `tags`, `created`, `updated`, `status`).
  - Write a python script or use the Linter plugin to batch update all existing notes to conform to the new schema.
  - Integrate a Dataview query to flag notes that violate the schema.
- **Acceptance Criteria:** 100% of primary knowledge notes contain standardized, valid YAML frontmatter.

---

## Phase 2: Quality & Performance
**Goal:** Improve mobile load times and clean up graph architecture.
**Estimated Time:** 5 hours

### Task 2.1: Optimize Mobile Performance Bottlenecks
- **Ref:** [H-02]
- **Description:** Reduce the burden of heavy indexers (e.g., Dataview, Smart Connections) on mobile devices.
- **Action Items:**
  - Create a separate `.obsidian-mobile` configuration folder.
  - Disable heavy indexing plugins (Smart Connections, Omnisearch) in the mobile profile.
  - Limit Dataview auto-refresh rates for mobile views.
- **Acceptance Criteria:** Obsidian application loads in under 3 seconds on the primary mobile device without battery drain warnings.

### Task 2.2: Execute Graph Pruning
- **Ref:** [M-02]
- **Description:** Remove or integrate orphaned notes within the vault.
- **Action Items:**
  - Use the built-in Graph View or an Orphaned Notes plugin to identify unlinked files.
  - Categorize orphans: delete obsolete files, or link valuable files to appropriate Maps of Content (MOCs).
- **Acceptance Criteria:** The graph has zero unintentional orphaned nodes.

---

## Phase 3: Developer Experience & Innovation
**Goal:** Seamlessly integrate headless AI workflows.
**Estimated Time:** 4 hours

### Task 3.1: Implement Headless Agent Workflows
- **Ref:** [L-01]
- **Description:** Establish native REST API integration for background AI agents to read/write without opening the Obsidian UI.
- **Action Items:**
  - Create standardized bash/python wrapper scripts to interact with the Obsidian Local REST API.
  - Build endpoints to trigger daily note creation and append agent findings automatically.
- **Acceptance Criteria:** AI Agents can successfully query note contents and append markdown text via the REST API while the UI is closed.