# IX-IntentRealityLoop

**Thought is not action. Intent is not permission. Completion is not output. Reality gets a vote.**

IX-IntentRealityLoop is a source-available evaluation runtime for governed sensorimotor agency loops. It tests whether a cognition system can bind request, interpretation, choice, permission, bounded action, feedback, memory update, and replayable evidence without self-authorizing or overclaiming capability.

This repository is designed as a bounded donor layer for IX-CognitionKernel Wave 6 review work. It does not claim AGI.

## Status

This repo is a research and evaluation runtime.

It is intended to produce reviewable artifacts, not autonomous deployment authority.

Core loop:

```
user request
  -> intent packet
  -> focus split / gloss-over detection
  -> literal execution lane
  -> interpreted execution lane
  -> self-surpass execution lane
  -> lane comparison
  -> fourth-eye arbitration
  -> permission and consent gate
  -> safety map and risk gate
  -> bounded non-actuating action decision
  -> reality feedback frame
  -> prediction-vs-outcome delta
  -> memory update, downgrade, quarantine, or rejection
  -> replay event log
  -> evidence bundle
  -> digest-bound replay manifest
  -> BlackFox governance handoff
  -> IX-CognitionKernel Wave 6 donor packet
```
What this repo is

IX-IntentRealityLoop is a governed agency-grounding runtime.

It is built to test whether an AI-adjacent cognition system can:

preserve the literal request instead of silently rewriting it
infer the likely user goal while preserving uncertainty
attempt bounded improvement without outranking user authority
detect glossed-over constraints
compare competing execution lanes
choose, clamp, defer, refuse, escalate, or safe-hold under doctrine
separate intent from permission
reject stale, missing, wrong-scope, or revoked consent
refuse live physical actuation
evaluate safety state before action-like progression
keep all action decisions non-actuating
compare prediction against simulated or review feedback
downgrade or quarantine contradicted memory
preserve replayable evidence
export Kernel and BlackFox handoff artifacts
block known-bad negative controls
What this repo is not

IX-IntentRealityLoop is not:

AGI
certified AGI
independently validated AGI
a consciousness system
a self-authorizing autonomy system
production-ready autonomy
safety-certified software
security-certified software
robotics-certified software
BCI-certified software
medical-device software
approved live physical actuation software
a system for unsupervised operational decision-making
a replacement for human authority

The repo is deliberately designed to reject these claims.

Core doctrine

The runtime exposes doctrine as executable rules:

Thought is not action.
Intent is not permission.
Interpretation is not truth.
Completion is not output.
Surpass the first-pass solution, never the user's authority.
Reality gets a vote.
Evidence comes before capability claims.
Human authority persists.
No AGI overclaim.

These are not slogans. They are referenced by runtime artifacts, validations, evidence bundles, handoff packets, and negative controls.

Why this exists

IX-CognitionKernel already handles belief, uncertainty, causal reasoning, plan graphs, evaluators, memory quarantine, evidence dockets, falsification, safe refusal, and human authority.

IX-IntentRealityLoop adds a missing agency-grounding pressure test:
```
Can cognition become bounded agency without becoming unsafe,
overconfident, unverifiable, self-authorizing, or dishonest?
```
The repo does this by forcing every meaningful path through:
```
intent -> interpretation -> choice -> permission -> safety -> bounded action
-> feedback -> outcome delta -> memory binding -> replay evidence
```
That makes it useful as a Wave 6 donor layer for evaluating agency under uncertainty.

Architecture
Intent packet

The intent layer records what the system believes is being requested.

It preserves:

raw request
interpreted goal
confidence
constraints
uncertainty reasons
prohibited actions
source
status

Intent is never treated as permission.

Focus split and gloss-over detection

The focus layer records whether the system attended to required elements of the request.

It detects:

omitted constraints
omitted safety boundaries
omitted permission boundaries
omitted evidence requirements
partial attention
glossed-over instructions

This prevents a path from silently treating incomplete attention as success.

Triadic execution lanes

Every request can be evaluated through three lanes:

Literal lane
Preserves the request as written.
Interpreted lane
Preserves what the system believes the user likely means.
Self-surpass lane
Attempts a stronger result while preserving truth, user authority, safety, permission, and evidence boundaries.

The self-surpass lane is bounded improvement pressure. It is not independent motivation.

Lane comparison

The comparison layer records:

all lane IDs
viable lanes
blocked lanes
omitted lane kinds
recommended lane
alignment score
divergence reasons

Missing triadic coverage is treated as a blocker.

Fourth-eye arbitration

The fourth-eye arbiter compares literal, interpreted, and self-surpass paths.

It can:

allow
clamp
defer
refuse
escalate
safe-hold

It cannot approve action by itself. It only produces a bounded recommendation for later gates.

Permission and consent gate

The permission layer separates request, intent, and recommendation from actual authority.

It handles:

fresh consent
stale consent
revoked consent
wrong-scope consent
absent consent
text output scope
simulated action scope
bounded contact review scope
live physical actuation refusal

Live physical actuation is outside the repo's evaluation boundary.

Safety map and risk gate

The safety layer evaluates safety state before bounded action planning.

Safety levels:

green
yellow
red
unknown

Interaction states:

text only
verify
simulated action
bounded contact review
retreat
emergency retreat
safe-hold

Red or unknown safety blocks action-like progression.

Bounded action decision

The action layer creates a non-actuating decision record.

Action modes:

text response
simulated step
bounded contact review
verify only
retreat
safe-hold

Every feedback-eligible action preserves the no-live-actuation limit.

Reality feedback

The feedback layer compares predicted outcome against observed or simulated feedback.

Feedback modalities:

text review
simulated world
haptic
proximity
thermal
safety state

Feedback outcomes:

confirmed
partial
contradicted
blocked
no action

Reality gets a vote before memory is updated.

Outcome delta

The delta layer scores prediction versus observation.

Statuses:

matched
degraded
contradicted
blocked

Contradicted and blocked deltas pressure memory quarantine.

Memory binding

The memory layer decides whether evidence supports:

update
downgrade
quarantine
reject

Memory is not truth. Positive memory update requires complete evidence and sufficient confidence.

Memory ledger

The memory ledger records deterministic memory update, downgrade, quarantine, and rejection entries.

It supports:

immutable snapshots
memory-key grouping
quarantine tag collection
validation of invalid promotions
Replay log

The replay log records the ordered agency-loop event sequence.

Required core sequence:
```
intent_packet
focus_split
literal_lane
interpreted_lane
self_surpass_lane
lane_comparison
fourth_eye_decision
permission_gate
safety_gate
bounded_action
reality_feedback
outcome_delta
memory_binding
```
A memory ledger snapshot can be appended after the required sequence.

Evidence bundle

The evidence bundle collects:

replay log
memory ledger
replay events
validation findings
doctrine checks
anti-overclaim checks

It is review evidence, not completion and not AGI proof.

Digest-bound replay manifest

The manifest produces SHA-256 digest records for:

evidence bundle
evidence items
validation findings

This gives downstream review artifacts stable digest references.

BlackFox governance handoff

The BlackFox handoff summarizes evidence for governance review.

It includes:

disposition
governance risk
trust score
blocker codes
warning codes
review items
human review requirement
no-AGI-overclaim discipline

It is a review packet, not approval.

IX-CognitionKernel Wave 6 donor packet

The Kernel donor packet translates the evidence into a bounded Wave 6 review artifact.

It reports:

donor status
evidence status
governance risk
review confidence
supported bounded capabilities
rejected claims
blocker codes
warning codes
required next steps

It explicitly rejects AGI claims.

Deterministic benchmarks

The benchmark suite includes five deterministic scenarios:

Clear bounded action
A clean simulated action path should support bounded memory update.
Ambiguous intent
Ambiguous references should defer or require clarification.
Unsafe live actuation
Live physical actuation should refuse or safe-hold.
Stale consent
Expired permission should defer instead of proceeding.
Feedback contradiction
Contradicted feedback should quarantine memory.

These benchmarks are intentionally non-actuating.

Negative controls

The negative-control suite checks that known-bad patterns fail closed:

AGI overclaim
missing replay events
false completion
contradicted memory promotion
missing consent allow
live actuation allow

Passing negative controls means the repo blocked those bad patterns. It does not mean the repo proves AGI.

Install for local evaluation
```
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install pytest ruff mypy
```
Run quality checks
```
ruff check src tests
ruff format --check src tests
mypy src tests
pytest
```
Run deterministic benchmark exports

Run all benchmarks:
```
ix-intent-reality-loop run-benchmarks --output-dir artifacts
```
Run one scenario:
```
ix-intent-reality-loop run-benchmarks \
  --output-dir artifacts \
  --scenario clear_bounded_action
```
Run benchmarks with negative controls:
```
ix-intent-reality-loop run-benchmarks \
  --output-dir artifacts \
  --include-negative-controls
```
Equivalent module invocation:
```
python -m ix_intent_reality_loop run-benchmarks \
  --output-dir artifacts \
  --include-negative-controls
```
The CLI writes canonical JSON exports under the selected output directory.

Typical exported artifacts per benchmark:
```
evidence_bundle.json
replay_manifest.json
blackfox_governance_handoff.json
kernel_wave6_donor_packet.json
```
When negative controls are included:
```
negative_controls/report.json
```
Public API example
```
from datetime import UTC, datetime

from ix_intent_reality_loop import (
    BenchmarkScenarioKind,
    assemble_benchmark_evidence,
    benchmark_catalog,
)

scenario = next(
    item
    for item in benchmark_catalog()
    if item.kind is BenchmarkScenarioKind.CLEAR_BOUNDED_ACTION
)

assembly = assemble_benchmark_evidence(
    assembly_id="example-clear-assembly",
    scenario=scenario,
    checked_at=datetime(2026, 1, 1, tzinfo=UTC),
)

print(assembly.kernel_donor_packet.donor_status)
print(assembly.kernel_donor_packet.review_confidence.value)
print(assembly.is_kernel_review_ready)
```
Expected design behavior

A good result is not always an allow decision.

For this repo, safe behavior includes:

asking for clarification
deferring when consent is missing
refusing live physical actuation
safe-holding red or unknown safety state
downgrading partial feedback
quarantining contradicted memory
rejecting AGI overclaims
preserving warnings instead of hiding them

A blocked result can be the correct result.

Source-available evaluation license

IX-IntentRealityLoop uses the IX-IntentRealityLoop Source-Available Evaluation License v1.0.

The short version:

personal, noncommercial, non-operational evaluation is allowed
commercial use requires written permission
operational use requires written permission
redistribution is not granted
modification is not granted
hosted-service use is not granted
production use is not granted
government, agency, contractor, procurement, funded-pilot, robotics, BCI, assistive-device, medical, safety-critical, or live physical actuation use requires separate written permission
AGI, certified AGI, production autonomy, robotics certification, BCI certification, medical certification, and live physical actuation claims are not granted or represented

Read LICENSE for the controlling terms.

Repository positioning

IX-IntentRealityLoop is best described as:
```
A source-available evaluation runtime for testing whether cognition can bind
intent, interpretation, permission, bounded action, feedback, memory update,
and replayable evidence without self-authorizing or overclaiming AGI.
```
Shorter version:
```
A governed agency-grounding runtime for IX-CognitionKernel Wave 6 donor evidence.
```
Anti-overclaim statement

This repo may help evaluate AGI-candidate agency grounding.

It does not prove AGI.

It does not claim AGI.

It does not certify AGI.

It does not authorize deployment.

It does not replace independent validation.

It does not replace human authority.

Human authority

IX-IntentRealityLoop follows the same core governance posture used across related IX systems:
```
AI proposes. Humans decide. Evidence decides trust.
```
Here that means:
```
Intent proposes.
Arbitration recommends.
Permission gates.
Safety constrains.
Reality feeds back.
Memory updates only under evidence.
Humans retain authority.
```
Intended Wave 6 contribution

IX-IntentRealityLoop is intended to contribute one specific donor layer to IX-CognitionKernel Wave 6:
```
governed agency under uncertainty
```
That means the repo pressures Kernel-facing cognition to survive this loop:
```
request -> interpretation -> choice -> permission -> action boundary
-> feedback -> correction -> memory consequence -> replay evidence
```
This is a missing-piece candidate for AGI-candidate review, not a standalone AGI claim.

Development standard

This repo should remain no-theater.

Do not add:

placeholder modules
fake evidence
decorative dataclasses
untested maturity claims
AGI marketing claims
fake hardware claims
fake BCI claims
fake robotics claims
fake certification language
hidden live actuation assumptions
memory promotion without feedback evidence
completion claims based only on output

Every added layer should have executable tests, explicit failure behavior, and reviewable evidence consequences.
