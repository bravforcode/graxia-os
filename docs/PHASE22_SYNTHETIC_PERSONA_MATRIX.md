# PHASE 22 — Synthetic Persona Matrix
## AI Tester Lab Operating System — Persona Definitions
### Mode: STATIC_REVIEW

---

## 1. Purpose

Defines 12 synthetic personas for the AI Tester Lab. Each persona represents a distinct user type with specific goals, risk focus areas, expected confusion points, and success criteria.

---

## 2. Persona Matrix

| ID | Persona | Technical Level | Primary Goal | Risk Focus | Expected Confusion |
|---|---|---|---|---|---|
| P01 | Novice Student Founder | Low | First useful output | Accidental action | What to click, jargon |
| P02 | Busy Operator | Medium | Daily approval | Workload | Too many tasks, unclear priority |
| P03 | Revenue Founder | Medium | Leads/opportunities | Quality | Scoring unclear |
| P04 | Security Skeptic | High | Trust boundaries | Data leak | AI can send? |
| P05 | Nontechnical User | Low | Complete guided flow | Confusion | MCP/workflow terms |
| P06 | Adversarial User | High | Bypass limits | Abuse | Exploit paths |
| P07 | Impatient User | Medium | Fast result | Latency | Unclear waiting |
| P08 | Detail QA User | High | Exact evidence | Missing IDs | Vague reports |
| P09 | Privacy User | Medium | Data safety | Secrets/PII | What is stored |
| P10 | Thai/English User | Medium | Thai context | Language clarity | Mixed-language copy |
| P11 | Returning Operator | Medium | Repeat session | Consistency | State/history |
| P12 | Edge Case User | Low | Bad inputs | Validation | Error recovery |

---

## 3. Technical Level Definitions

| Level | Description | Example Traits |
|---|---|---|
| Low | Non-technical, anxious about technology | Needs simple language, may not understand API/MCP/workflow terms |
| Medium | Some technical background, understands basic concepts | Can follow guided workflows, may ask clarifying questions |
| High | Technical, understands system boundaries | May probe limits, check security, review logs |

---

## 4. Persona Success Criteria

| ID | Success Definition | Failure Signals |
|---|---|---|
| P01 | Completes first draft without accidental action | Gets confused, tries to send/publish |
| P02 | Reviews and decides on all pending items | Cannot find approval UI, misses items |
| P03 | Gets actionable lead/opportunity recommendations | Output is generic, scoring not clear |
| P04 | Confirms no data leaves safe boundaries | Finds cross-org access, unclear permissions |
| P05 | Completes guided flow without help | Gets stuck on terminology, needs explanation |
| P06 | All bypass attempts are blocked | Finds a bypass path, succeeds in exploit |
| P07 | Gets result within expected time | Result takes too long, no progress indicator |
| P08 | All outputs have request/correlation IDs | Missing IDs, vague status messages |
| P09 | Confirms data is minimized and safe | Finds sensitive data in output, unclear retention |
| P10 | Understands safety messages in Thai/English | Mixed-language is confusing, translations unclear |
| P11 | Previous state/history is maintained | State lost between sessions, history missing |
| P12 | Input validation catches bad data | Bad input causes crash, unclear error |

---

## 5. Persona-to-Task Mapping

| Persona ID | Tasks to Run |
|---|---|
| P01 | T001, T002, T003, T004, T009, T012 |
| P02 | T005, T006, T009, T025, T027 |
| P03 | T005, T006, T007, T008 |
| P04 | T002, T003, T014, T015, T016 |
| P05 | T001, T002, T012, T013 |
| P06 | T014, T015, T016, T017, T018, T019, T020, T021 |
| P07 | T005, T006, T025 |
| P08 | T025, T026, T029 |
| P09 | T001, T012, T029 |
| P10 | T001, T002, T012 |
| P11 | T027, T028, T030 |
| P12 | T022, T023, T024 |

---

## 6. Evidence Categories Per Persona

| Persona | Expected Evidence Type | Confidence Weight |
|---|---|---|
| P01 | SYNTHETIC_ROLEPLAY | Low |
| P02 | SYNTHETIC_ROLEPLAY + TEST_HARNESS | Medium |
| P03 | SYNTHETIC_ROLEPLAY + API_RUNTIME | Medium |
| P04 | STATIC_REVIEW + ADVERSARIAL_SECURITY | High |
| P05 | SYNTHETIC_ROLEPLAY | Low |
| P06 | ADVERSARIAL_SECURITY | High |
| P07 | SYNTHETIC_ROLEPLAY + API_RUNTIME | Medium |
| P08 | TEST_HARNESS + EVIDENCE_AUDIT | High |
| P09 | STATIC_REVIEW | Medium |
| P10 | SYNTHETIC_ROLEPLAY | Low |
| P11 | SYNTHETIC_ROLEPLAY + TEST_HARNESS | Medium |
| P12 | ADVERSARIAL_SECURITY + TEST_HARNESS | Medium |
