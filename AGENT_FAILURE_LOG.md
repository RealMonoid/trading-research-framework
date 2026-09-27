# Agent failure log

This repository-wide log records concrete agent failures, errors, and avoidable workflow interruptions. Every agent that observes or causes a material failure must append an English entry before handoff.

Each entry must include the full agent/model name and version, an ISO 8601 date and time, the exact failure description, the exact location (file, workflow step, tool operation, or user-facing turn), the impact, the recovery or unresolved status, and an evidence link.

The complete case chronology belongs in the case-specific failure file under
`private_research/`, including all case-related errors and micro-stops. This
repository file defines the maintenance rule and provides safe index entries;
it must not duplicate private strategy, market-data, credential, chain-of-
thought, or identifying user material. A normal prerequisite blocker is not an
agent failure unless its handling failed or caused avoidable friction.

## Entries

### 2026-09-06T15:37:33+02:00 — ChatGPT 5 (Codex)

- **Failure description**: The data-preparation communication presented an optional provider investigation as though the supplied TradingView CSV had become generally insufficient. This conflated preliminary inspection with later requirements for contract-specific executable claims and caused an unnecessary access checkpoint.
- **Location**: User-facing continuation turns and the private NQ provider-feasibility record.
- **Impact**: The owner reasonably questioned why the supplied CSV was first treated as usable and then appeared rejected. No market test or purchase occurred.
- **Recovery**: Clarified that the CSV remains the available preparation dataset; provider acquisition is optional and must be tied to a concrete unresolved rule or claim.
- **Evidence**: `private_research/expander-strategy-v1/FAILURES_AND_FRICTION.md`.

### 2026-09-06T15:37:33+02:00 — ChatGPT 5 (Codex)

- **Failure description**: The workflow introduced repeated continuation handoffs for independently authorized preparation steps, creating avoidable micro-stops in the user interaction.
- **Location**: User-facing turns during audit restoration and provider-feasibility preparation.
- **Impact**: The owner had to repeat a short continuation instruction instead of receiving one continuous bounded preparation pass.
- **Recovery**: Added the incident to the private case log and made this repository-wide log mandatory for future agents.
- **Evidence**: `private_research/expander-strategy-v1/FAILURES_AND_FRICTION.md`.

### 2026-09-08T18:47:31.398133+02:00 — ChatGPT 6 Astra

- **Failure description**: Attempted PR #68 merge before reconciling a branch whose predecessor commit had already been squash-merged as PR #67. GitHub rejected the merge. The initial progress message incorrectly attributed the conflict to newly changed main.
- **Location**: PR #68 merge command and AGENT_CHANGELOG.md history reconciliation.
- **Impact**: One rejected merge and another CI cycle; no content loss or direct main write.
- **Recovery**: Merged origin/main into the task branch. The only conflict was the changelog append against an empty counterpart; retained the entire existing changelog exactly.
- **Evidence**: https://github.com/RealMonoid/trading-research-framework/pull/68 and the task branch merge commit.

### 2026-09-27T21:55:27.7699213+02:00 — ChatGPT 6 Astra

- **Failure description**: An incomplete patch appended a stray list marker instead of the intended changelog entry.
- **Location**: `AGENT_CHANGELOG.md`, end of file, during the TimesFM roadmap edit.
- **Impact**: Temporary local documentation defect; no commit or upload contained it.
- **Recovery**: Inspected the diff immediately and replaced the marker with the complete entry before validation and commit.
- **Evidence**: The local diff showed a single added `-` after the 2026-09-09 entry; the corrected 2026-09-27 entry in `AGENT_CHANGELOG.md` records the completed scope.
