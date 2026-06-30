from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from reframe_agent_host.keyphrases import PocketSphinxPhraseSpotter
from reframe_agent_host.keyphrases.audio_file import chunk_samples, read_mono_wav


def run_debug_wake_audio(args: argparse.Namespace) -> int:
    results = [
        _analyze_file(
            path,
            args.wake_keyword,
            args.conversation_on_phrase,
            args.wake_gain,
            args.window_ms,
            args.chunk_ms,
            args.check_ms,
        )
        for path in args.wav
    ]
    print(json.dumps(results, indent=2))
    return 0 if any(result["detections"] for result in results) else 1


def _analyze_file(
    path: str,
    wake_keywords: list[str],
    conversation_phrases: list[str],
    gain: float,
    window_ms: int,
    chunk_ms: int,
    check_ms: int,
) -> dict[str, object]:
    samples, sample_rate = read_mono_wav(path)
    if sample_rate != 16_000:
        raise ValueError(f"{path} must be 16000 Hz; got {sample_rate}.")

    spotter = PocketSphinxPhraseSpotter(
        phrase_kinds=_phrase_kinds(wake_keywords, conversation_phrases),
        check_interval_frames=max(1, round(check_ms / chunk_ms)),
        gain=gain,
        max_buffer_ms=window_ms,
    )
    detections = []
    hypotheses = []
    for index, frame in enumerate(chunk_samples(samples, sample_rate, chunk_ms)):
        spotter.append(frame)
        detection = spotter.detect()
        offset_ms = int((index + 1) * chunk_ms)
        if spotter.last_hypstr:
            hypotheses.append({"offset_ms": offset_ms, "hypstr": spotter.last_hypstr})
        if detection is not None:
            detections.append(
                {
                    "offset_ms": offset_ms,
                    "kind": detection.kind,
                    "phrase": detection.phrase,
                    "hypstr": detection.hypstr,
                    "phrase_end_sample": detection.phrase_end_sample,
                }
            )

    return {
        "path": str(Path(path)),
        "duration_seconds": len(samples) / sample_rate,
        "peak": float(np.max(np.abs(samples))) if len(samples) else 0.0,
        "rms": float(np.sqrt(np.mean(np.square(samples)))) if len(samples) else 0.0,
        "detections": detections,
        "hypotheses": _dedupe_hypotheses(hypotheses),
    }


def _phrase_kinds(
    wake_keywords: list[str],
    conversation_phrases: list[str],
) -> dict[str, str]:
    return {
        **{phrase: "wake_command" for phrase in wake_keywords},
        **{phrase: "conversation_on" for phrase in conversation_phrases},
    }


def _dedupe_hypotheses(hypotheses: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped = []
    previous = None
    for hypothesis in hypotheses:
        if hypothesis["hypstr"] == previous:
            continue
        deduped.append(hypothesis)
        previous = hypothesis["hypstr"]
    return deduped
