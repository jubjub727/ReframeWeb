# Voice Request Completion and Memory Writeback

**Status:** Implemented

This note describes the final stages of the routed voice-request loop. It is
intentionally implementation-light. BAML should continue to own the agentic
control flow, while the Python Agent Host provides typed data and persistence
boundaries.

## Request Loop Completion

The existing selected-task completion check remains the inner gate. A task may
retry until it satisfies its own output contract, or leave the inner loop so a
different task can be selected.

After a selected task passes its task-level check, a second prompt layer should
compare the original voice request with the current conversation and the
successful task results accumulated during the wider request loop. Its return
type should use the same simple `PASS` or `FAIL` completion result as the
existing task-level checker.

- `FAIL` continues the outer loop and allows the existing task-choice layer to
  select another task.
- `PASS` breaks out of the outer loop and moves to candidate-memory review.

The request-completion prompt should judge whether the user has received an
accurate and appropriate response, rather than treating every request as an
outcome that must be forced to happen. Completion may include performing the
work, providing a truthful answer, asking for information required to continue,
or clearly explaining a limitation. An attempted action without supporting
evidence is not completion, and impossible work should not cause artificial
progress loops.

## Do Nothing Escape

`Do nothing` is a loop restart rather than an immediate terminal result. It
should still pass through the original-request completion stage.

Track consecutive `Do nothing` selections across the outer loop. A real task
selection resets the count. On the third consecutive selection, consider the
request complete without another completion-model call, break out of the outer
loop, and proceed directly to candidate-memory review when candidates exist.
Task-choice candidate memories produced while selecting `Do nothing` remain
ordinary task-choice candidates.

## Candidate Accumulation

Candidate memories should remain associated with the prompt layer that produced
them and accumulate for the lifetime of the complete voice request, including
across task retries and reselection. The current candidate groups are:

- Task choice.
- Conversation evaluation and memory-search planning.
- Search-depth selection.
- Retrieved-memory relevance selection.
- Task-prompt composition.

No candidate review or graph write should occur while the request may still
select another task.

## Parallel Candidate Review

Once the original request passes, group all accumulated candidates by their
originating prompt layer. Run one focused review for each non-empty group in
parallel. Each review receives all new candidates of that type together with
all previously stored context memories for the same prompt layer, including
their timestamps.

The review should select which candidate ids are worth keeping. It should avoid
adding duplicates of existing memories, avoid redundant candidates within the
new batch, and reject observations that are temporary, speculative, or not
useful as future guidance for that specific prompt layer.

This stage is append-only. It may accept or reject new candidates, but it must
not update, delete, replace, or supersede existing memories. A separate future
system can manage stale or conflicting stored memories.

After every parallel review completes, save the kept candidates under the
matching prompt-layer memory roots so they are available as context on the next
voice request. If no candidates were accumulated, skip review and writeback.

## Ownership and Verification

BAML should own both loop exits, the consecutive no-op count, candidate
accumulation, grouping, parallel review, and the decision to finish. The Agent
Host should only execute typed boundary operations such as loading context and
writing the already-selected memories.

Verification should cover the inner and outer loop exits, request `PASS` and
`FAIL`, three consecutive no-op selections, counter reset after a real task,
candidate accumulation across task cycles, parallel per-type review, duplicate
rejection, append-only persistence, and the empty-candidate fast path.
