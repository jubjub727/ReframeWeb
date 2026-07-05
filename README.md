# ReframeWeb

ReframeWeb is an experimental agentic workflow environment for replacing the
legacy browser mental model.

It is not a conventional web browser with agents layered on top. Instead,
ReframeWeb treats interactive work as a combination of agent-readable semantic
capabilities, user-visible visual panels, persistent memory, and deterministic
compute tools.

The project starts from the user interaction loop: Python receives audio, BAML
drives the agentic flow, and the rest of the system is called from there. Native
visual panels, a transport layer, WebAssembly Stores, Data Lenses, Compute
Modules, and memory hang off that host-driven flow.

## Core Premise

The legacy browser model is built around pages, tabs, browser chrome, DOM state,
and visual interaction as the primary interface. ReframeWeb starts from a
different assumption: agents and users should share a richer interaction surface
where semantic capabilities are first-class.

In ReframeWeb, the first runtime surface is the **Agent Host**: a Python process
that receives audio, coordinates BAML, and routes work through native windows,
transport calls, Stores, Lenses, Compute Modules, and memory.

The shared substrate for those components is a transport layer spec. A
**Semantic Store** is WebAssembly code that implements that spec, exposing
resources, functions, schemas, permissions, and usage hints through the transport
rather than existing as a normal application library.

CEF is used as a rendering and native windowing foundation for Visual Panels. It
is not the product's central abstraction. The goal is to build a new agent-native
workflow layer, not to preserve the browser as the underlying concept.

## What This Is Not

- Not a browser extension.
- Not Selenium-style browser automation.
- Not a legacy browser with an assistant bolted onto it.
- Not a DOM-first control system where agents primarily click their way through
  pages.

## Main Components

- **Agent Host**: A Python manager that handles conversational flow, audio input,
  transcription, BAML-driven agent logic, routing, memory coordination, and TTS
  playback.
- **BAML Flow**: The first agentic decision layer. Audio is transcribed and
  passed into BAML so the host can decide what should happen next.
- **Transport Layer**: A protocol surface, similar in role to HTTP, that will
  define routing, calls, streaming, and component interaction between Stores,
  Lenses, Views, and Compute.
- **Semantic Store**: WebAssembly code that implements the transport layer spec
  and exposes resources and functions agents can discover and call.
- **Visual Panel**: A React display surface shown in a native CEF-backed panel
  window. Users can see state and occasionally click or scroll, but required
  functionality should be exposed for agent-driven control.
- **Data Lens**: An optional Rust support layer between a Store and a Visual
  Panel. It is for cases where behavior needs to differ substantially from the
  original site or application intent, or where the Store lacks a sensible API
  surface for React to parse directly.
- **Compute Module**: A short Rust script for specialized, complex, repetitive
  deterministic tasks. Compute Modules are not the default path for ordinary
  repeated behavior, because overusing them would slow down the agentic flow.
- **Memory Graph**: A graph-backed memory system for preferences, task context,
  user habits, and recent relevant memories.

## Underlying Technology

ReframeWeb is driven by a small set of deliberate technology choices:

More detail is tracked in [Technology](docs/technology.md).

- **Rust** for native CEF/window agentic bindings, Data Lenses, Compute Modules,
  memory-related runtime components, and likely Store implementations compiled
  to WebAssembly.
- **CEF** as the embedded rendering and native windowing foundation for Visual
  Panels. CEF is infrastructure here, not the conceptual model of the product.
- **React** for Visual Panel content, display state, Store-backed data fetching,
  and any user-visible controls.
- **Python** for the Agent Host, which owns setup, the main agentic flow, audio
  processing, transport coordination, memory coordination, and TTS playback.
- **BAML** for driving the agentic flow logic from the Python Agent Host.
- **WebAssembly** for Semantic Stores that implement the transport layer spec.
- **Graph database storage** for memory, including tagged memory nodes,
  descriptions, created/read/modified timestamps, relationships, and recency-aware
  retrieval.
- **`sounddevice`** for microphone input and audio playback control.
- **`pocketsphinx`** for local keyphrase spotting, including commands such as
  "jarvis do x" and a "conversation on" mode trigger.
- **`silero-vad`** for voice activity detection.
- **`faster-whisper`** for transcribing spoken prompts before they are passed
  into the BAML-driven agentic flow.
- **`kokoro`** for TTS playback, using the `af_heart` voice.

The audio layer should support cancelling spoken playback when the user starts
talking without destroying the underlying work the agent was already performing.

## Current Status

This repository now contains a working Agent Host prototype. The native
CEF/React Visual Panel layer, Semantic Store runtime, Data Lens runtime, and
Compute Module runtime are still future-facing architecture, but the Python
voice loop and graph-backed memory flow are active code.

Implemented pieces include:

1. A `uv`-managed Python Agent Host with CLI commands for setup, checks, voice
   turns, memory seeding, and benchmarks.
2. Local wake/phrase detection, VAD, GPU-backed Whisper transcription, and
   turn recording into the memory graph.
3. BAML stages for task choice, conversation memory-search hint generation, and
   per-domain search-depth selection.
4. A SurrealDB-backed memory graph with roots for providers, tasks, sessions,
   conversations, session memories, task-choice memories, conversation
   evaluation memories, and search-depth memories.
5. Graph-based memory retrieval that starts from existing roots and relations,
   applies search hints and timestamp breadth to candidate nodes, and hydrates
   parent wrappers needed to explain valid child matches.
6. Benchmark harnesses for task choice, conversation evaluation, and control
   flow/search-depth behavior.

## Agent Host Setup

```powershell
cd agent-host
uv sync
uv run baml check
uv run baml generate
uv run reframe-agent-host doctor
```

The Agent Host uses OpenCode Go through its OpenAI-compatible endpoint and reads
the API key from `OPENCODE_GO_API_KEY`.

Model use is a BAML choice, not user-selected global configuration and not
Python-side model routing. Each agentic task should have an explicit model
assignment through a memory Provider node that points at a BAML surface. The
current task-choice flow uses `kimi-k2.5` with high reasoning effort. The
conversation-evaluation and search-depth flows use `glm-5.1`.

Current benchmarked OpenCode Go model IDs include:

- `kimi-k2.7-code`
- `kimi-k2.6`
- `kimi-k2.5`
- `glm-5.1`
- `glm-5`
- `deepseek-v4-pro`
- `deepseek-v4-flash`
- `mimo-v2.5-pro`
- `mimo-v2.5`

## First Voice Pipeline

The first runnable microphone path is intentionally narrow and testable:

```powershell
cd agent-host
uv run reframe-agent-host gpu-check
uv run reframe-agent-host audio-devices
uv run reframe-agent-host voice-turn --device 1
```

The project config sets uv's package install link mode to `copy`, which avoids
Windows hardlink warnings when uv's cache and this repository live on different
drives.

If `uv` is not on PATH, use the local Windows runner instead:

```powershell
cd agent-host
.\reframe-agent-host.cmd gpu-check
.\reframe-agent-host.cmd audio-devices
.\reframe-agent-host.cmd voice-turn --device 1
```

`voice-turn` listens for one utterance, detects the speech boundary, transcribes
it with GPU-backed `faster-whisper`, records the current turn when session and
conversation IDs are available, sends the transcript through the BAML control
flow, retrieves graph memory context, and prints concise per-stage summaries and
latencies. When memory retrieval runs, the CLI prints the retrieved memories
directly instead of dumping the full turn result as JSON.

The current BAML control-flow path is:

1. Choose an initial task from the task catalog.
2. Generate memory search hints from the conversation and selected task.
3. Choose timestamp breadth for each search domain.
4. Retrieve memories from the graph.

Memory retrieval is relation-first rather than table-wide. The task catalog is
searched from the task root. Past conversation context is searched through
session, conversation, message, and session-memory relations. Search hints are
alternatives, so any positive tag or string hint can match a candidate. Timestamp
breadth is restrictive: candidate nodes must pass `created_at`, `updated_at`,
and, when present, `read_at` cutoffs. Parent wrappers are included when a valid
child match needs them for context. Current-session memories are always included
in the retrieved memory output for the active session.

By default, `WakeCommand` mode is wake-gated locally with a rolling PocketSphinx
phrase recognizer. It does not require an account, network call, or paid
wake-word service. Say the single-word trigger "jarvis" followed by the prompt.
The phrase "conversation on" switches the host into continuous conversation
mode. If more speech follows in the same utterance, such as "conversation on
this is a test", the trigger audio is trimmed away and the remaining command
audio is sent through VAD and GPU Whisper.

```powershell
uv run reframe-agent-host voice-turn --device 1 --no-task-choice
.\reframe-agent-host.cmd voice-turn --device 1 --no-task-choice
```

Useful tuning flags:

- `--wake-keyword jarvis` to configure local wake keyphrases.
- `--conversation-on-phrase "conversation on"` to configure the local
  conversation-mode trigger.
- `--conversation-on-confirm-window-ms 2000` to tune how much recent audio is
  replayed and how long the host waits to confirm the full phrase after hearing
  "conversation".
- `--wake-gain 1.0` to tune local phrase detector gain without changing the
  audio sent to Whisper.
- `--wake-threshold 1e-30` to tune local PocketSphinx KWS confirmation for
  wake-keyword candidates.
- `--wake-replay-pre-ms 0` starts command replay at the confirmed wake boundary
  so Whisper does not need to transcribe the wake word.
- `--debug-audio-dir .debug-audio` to opt in to saving local WAV clips and JSON
  sidecars for missed wake timeouts and detected keyphrases.
- `--debug-audio-seconds 8` to tune how much rolling microphone audio is kept
  for those debug clips.
- `--debug-audio-period-seconds 5` to opt in to saving rolling clips every few
  seconds while waiting for a wake phrase.
- `--post-activation-command-window-ms 700` to tune how briefly the host waits
  for command speech after a bare "conversation on" mode switch.
- `--vad silero` to require Silero VAD, or `--vad energy` to use the simple RMS
  fallback.
- `--vad-threshold 0.35` to tune Silero sensitivity for quieter microphone
  input.
- `--min-silence-ms 0` is the default. Increase it only if the utterance cuts off
  too early.
- `--final-silence-ms 1450` controls how long a provisional endpoint can be
  cancelled if speech resumes after Whisper starts.
- `--pre-speech-ms 320` keeps audio just before VAD start so first syllables are
  not cut off.
- `--wake-carry-ms 220` keeps audio around wake detection so commands that start
  immediately after the wake word are not clipped.
- `--energy-start-threshold 0.02` if the fallback detector starts too easily.
- `--whisper-model large-v3` to trade slower transcription for more accuracy
  than the default `turbo`.
- `--whisper-compute-type int8_float16` to test lower memory use than the
  default `float16`.
- `--whisper-model C:\path\to\model` to use a local faster-whisper model path.

Voice transcription is intentionally GPU-only. On Windows, the Agent Host checks
for CUDA 12 cuBLAS DLLs before listening, including project-local
`agent-host\.cuda\bin`, normal CUDA Toolkit installs, and NVIDIA Python wheel
locations such as `nvidia-cublas-cu12`.

Saved debug WAVs can be replayed through the local wake recognizer without
calling Whisper:

```powershell
uv run reframe-agent-host debug-wake-audio .debug-audio\*.wav
```

## Development Philosophy

ReframeWeb is being designed around a few working principles:

- Agent-native semantic interfaces should be the primary interaction layer.
- The first implementation path starts where the user interacts: audio into the
  Python Agent Host, then BAML-driven agentic flow.
- Visual Panels are React display outputs for showing useful state and controls.
  Users may click or scroll when they want to, but core functionality should be
  available to the agent rather than requiring manual UI operation.
- Compute Modules are for specialized, complex, repetitive deterministic
  behavior where a module genuinely improves reliability or clarity. Ordinary
  repeated actions should stay in the Store and agent flow.
- Personalization should usually happen through Visual Panels and Store-backed
  presentation. Data Lenses are for larger behavioral changes or for supporting
  cases where the Store does not expose a sensible API surface for React.
- Incremental development should build the actual project architecture rather
  than a substantially cut-down or throwaway version of it.
