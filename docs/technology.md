# Underlying Technology

This document tracks the core technology choices currently intended for
ReframeWeb. It should describe the actual project direction rather than a
temporary or cut-down version of it.

## Rust

Rust is used for the systems-level parts of ReframeWeb:

- Semantic Stores.
- Native CEF and window agentic bindings.
- Data Lenses.
- Compute Modules.
- Memory-related runtime components.

Rust is the default choice when a component needs strong boundaries,
deterministic behavior, native integration, or predictable performance.

## CEF

CEF is used as the embedded rendering and native windowing foundation for Visual
Panels.

CEF is infrastructure, not the product model. ReframeWeb is not trying to expose
a conventional browser with agents layered on top. The Visual Panel uses CEF as a
way to render React-driven interfaces inside native panel windows.

## React

React is used for the content of Visual Panels.

Visual Panels are display outputs for Store-backed data, view state, and
occasional user interaction such as clicking or scrolling. Required
functionality should be exposed through the agent-driven surface rather than
depending on manual UI operation.

## Semantic Stores

Semantic Stores are Rust-defined guided API surfaces. They expose resources and
functions that agents can discover and call.

Stores are intended to be the primary way agents interact with an experience.
They should provide enough structure that agents do not need to rely on visual
guessing, DOM-style control, or manual UI paths for required functionality.

## Data Lenses

Data Lenses are optional Rust support layers that sit between a Store and a
Visual Panel.

They are not the default personalization mechanism. Most personalization should
be possible through Visual Panels and Store-backed presentation. A Data Lens is
for larger behavior changes, or for cases where the Store does not expose a
sensible API surface for React to parse directly.

## Compute Modules

Compute Modules are short Rust scripts for specialized, complex, repetitive
deterministic behavior.

They should not be used for ordinary repeated actions. Overusing modules would
slow down the agentic flow and make the system harder to use. Agents should
primarily use the Store directly, with Compute Modules reserved for work that
benefits from being made deterministic and reusable.

## Python Agent Host

Python is used for the Agent Host.

The Agent Host owns setup and the main agentic flow. It coordinates processed
audio from the user's microphone, BAML-driven agent logic, Store calls, memory
access, and TTS playback.

## BAML

BAML is used for the agentic flow logic called from the Python Agent Host.

Spoken prompts are processed through the audio pipeline, transcribed, and then
passed into the BAML-driven flow.

## Audio Pipeline

The planned audio pipeline uses:

- `sounddevice` for microphone input and audio playback control.
- `pvporcupine` for trigger word detection, including "Agent do x" and
  conversation mode toggles such as "conversation on" and "conversation off".
- `silero-vad` for voice activity detection.
- `faster-whisper` for speech transcription.
- `kokoro` for TTS playback using the `af_heart` voice.

Audio playback should be cancellable when the user starts talking, without
destroying the underlying agent task that was already in progress.

## Memory Graph

ReframeWeb will use graph database storage for memory.

Memory nodes are expected to include:

- Descriptions.
- Tags.
- Creation timestamps.
- Read timestamps.
- Modified timestamps.
- Relationships to other memories.

The memory system should support searching for recent memories relevant to the
task at hand and keeping those available to the agentic flow.

The specific graph database technology is still an implementation decision.
