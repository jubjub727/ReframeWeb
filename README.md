# ReframeWeb

ReframeWeb is an experimental agentic workflow environment for replacing the
legacy browser mental model.

It is not a conventional web browser with agents layered on top. Instead,
ReframeWeb treats interactive work as a combination of agent-readable semantic
capabilities, user-visible visual panels, persistent memory, and deterministic
compute tools.

The project combines native visual panels, React interfaces, Rust-based semantic
stores, optional support layers, specialized deterministic compute modules, and a
Python agent host for conversational flow.

## Core Premise

The legacy browser model is built around pages, tabs, browser chrome, DOM state,
and visual interaction as the primary interface. ReframeWeb starts from a
different assumption: agents and users should share a richer interaction surface
where semantic capabilities are first-class.

In ReframeWeb, an experience is built around a **Semantic Store**: a guided API
surface containing resources, functions, schemas, permissions, and usage hints.
Agents can use the Store directly, while users interact with dynamic **Visual
Panels** that render useful state and controls.

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

- **Semantic Store**: A Rust-defined API surface containing resources and
  functions that agents can discover and call.
- **Visual Panel**: A React display surface shown in a native CEF-backed panel
  window. Users can see state and occasionally click or scroll, but required
  functionality should be exposed for agent-driven control.
- **Agent Host**: A Python manager that handles conversational flow, audio input,
  transcription, BAML-driven agent logic, and TTS playback.
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

- **Rust** for Semantic Stores, native CEF/window agentic bindings, Data Lenses,
  Compute Modules, and memory-related runtime components.
- **CEF** as the embedded rendering and native windowing foundation for Visual
  Panels. CEF is infrastructure here, not the conceptual model of the product.
- **React** for Visual Panel content, display state, Store-backed data fetching,
  and any user-visible controls.
- **Python** for the Agent Host, which owns setup, the main agentic flow, audio
  processing, Store coordination, memory coordination, and TTS playback.
- **BAML** for driving the agentic flow logic from the Python Agent Host.
- **Graph database storage** for memory, including tagged memory nodes,
  descriptions, created/read/modified timestamps, relationships, and recency-aware
  retrieval.
- **`sounddevice`** for microphone input and audio playback control.
- **`pvporcupine`** for trigger word detection, including commands such as
  "Agent do x" and conversation mode toggles such as "conversation on" and
  "conversation off".
- **`silero-vad`** for voice activity detection.
- **`faster-whisper`** for transcribing spoken prompts before they are passed
  into the BAML-driven agentic flow.
- **`kokoro`** for TTS playback, using the `af_heart` voice.

The audio layer should support cancelling spoken playback when the user starts
talking without destroying the underlying work the agent was already performing.

## Current Status

This repository is at the planning and scaffolding stage. The first milestone is
to establish the project shape, shared vocabulary, and the first real
implementation slice:

1. The initial Semantic Store foundation.
2. The initial React Visual Panel foundation.
3. The first Agent Host command path.
4. The first memory lookup path.
5. A clear contract between those pieces.

## Development Philosophy

ReframeWeb is being designed around a few working principles:

- Agent-native semantic interfaces should be the primary interaction layer.
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
