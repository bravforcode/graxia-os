# Change Control

## Experiment Immutability

- Never overwrite an experiment
- Corrected work creates a new experiment ID linked to the superseded one

## Change Request Required For

- Strategy parameter changes
- Strategy logic changes
- Dataset changes
- Execution model changes
- Risk policy changes
- Any change that affects a locked experiment

## Change Request Template

```
CR-ID: <unique-id>
DATE: <YYYY-MM-DD>
REQUESTOR: <name or agent>
TYPE: [strategy-param | strategy-logic | dataset | execution-model | risk-policy | experiment-locked]
PHASE: <current phase>
DESCRIPTION: <what changes>
JUSTIFICATION: <why>
RISK_IMPACT: <low | medium | high>
INVARIANTS_AFFECTED: <INV-XXX, ...>
EVIDENCE: <test results or analysis supporting the change>
APPROVED_BY: <name or agent>
```
