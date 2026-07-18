from __future__ import annotations

from pathlib import Path


BYTECODE: bytes = Path(__file__).with_name("_inlinedbaml.bin").read_bytes()
