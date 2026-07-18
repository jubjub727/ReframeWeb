from __future__ import annotations

import struct
from pathlib import Path
from tempfile import TemporaryDirectory
import tomllib
import unittest

from reframe_agent_host.baml_artifacts import (
    normalize_borsh_source_paths,
    normalize_generated_text_files,
)
from reframe_agent_host.baml_generation import _project_root


class BamlGenerationTests(unittest.TestCase):
    def test_absolute_borsh_paths_become_checkout_independent(self) -> None:
        source = (
            rb"\\?\D:\different\checkout\agent-host\baml_src\ns_workspace\types.baml"
        )
        symbol = ".<lambda($init_____D__different_checkout_agent_host_baml_src_x)>"
        encoded_symbol = symbol.encode()
        bytecode = b"".join(
            (
                b"prefix",
                struct.pack("<I", len(source)),
                source,
                struct.pack("<I", len(encoded_symbol)),
                encoded_symbol,
                b"suffix",
            )
        )

        normalized = normalize_borsh_source_paths(bytecode)
        expected_path = b"baml_src/ns_workspace/types.baml"
        expected_symbol = b".<lambda($init_____baml_src_x)>"

        self.assertEqual(
            normalized,
            b"".join(
                (
                    b"prefix",
                    struct.pack("<I", len(expected_path)),
                    expected_path,
                    struct.pack("<I", len(expected_symbol)),
                    expected_symbol,
                    b"suffix",
                )
            ),
        )
        self.assertEqual(normalize_borsh_source_paths(normalized), normalized)
        self.assertNotIn(b"different", normalized)

    def test_unrelated_length_prefixed_strings_are_unchanged(self) -> None:
        source = b"docs/design.baml"
        bytecode = struct.pack("<I", len(source)) + source

        self.assertEqual(normalize_borsh_source_paths(bytecode), bytecode)

    def test_generated_python_has_lf_and_no_trailing_whitespace(self) -> None:
        with TemporaryDirectory() as temporary:
            generated = Path(temporary)
            module = generated / "client.py"
            stub = generated / "client.pyi"
            other = generated / "notes.txt"
            module.write_bytes(b"value = 1  \r\nnext_value = 2\t\r\n")
            stub.write_bytes(b"def call() -> None:   \n")
            other.write_bytes(b"unchanged  \r\n")

            normalize_generated_text_files(generated)

            self.assertEqual(module.read_bytes(), b"value = 1\nnext_value = 2\n")
            self.assertEqual(stub.read_bytes(), b"def call() -> None:\n")
            self.assertEqual(other.read_bytes(), b"unchanged  \r\n")

    def test_generation_resolves_a_developer_checkout_from_a_child(self) -> None:
        with TemporaryDirectory() as temporary:
            project = Path(temporary) / "agent-host"
            child = project / "tools" / "nested"
            child.mkdir(parents=True)
            (project / "baml.toml").write_text("[package]\nname='test'\n")
            (project / "baml_src").mkdir()
            (project / "src" / "baml_sdk").mkdir(parents=True)

            self.assertEqual(_project_root(child), project.resolve())

    def test_generation_rejects_a_runtime_only_install(self) -> None:
        with TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(RuntimeError, "developer checkout"):
                _project_root(Path(temporary))

    def test_committed_bytecode_has_no_checkout_path(self) -> None:
        artifact = (
            Path(__file__).parents[1] / "src" / "baml_sdk" / "_inlinedbaml.bin"
        )
        bytecode = artifact.read_bytes()

        self.assertNotIn(b"ReframeWeb", bytecode)
        self.assertNotIn(b"D__ReframeWeb", bytecode)
        self.assertNotIn(rb"\\?\D:\ReframeWeb", bytecode)
        self.assertEqual(normalize_borsh_source_paths(bytecode), bytecode)

    def test_distribution_declares_every_runtime_module(self) -> None:
        project = Path(__file__).parents[1]
        configuration = tomllib.loads(
            (project / "pyproject.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(
            configuration["tool"]["uv"]["build-backend"]["module-name"],
            ["reframe_agent_host", "reframe_memory", "baml_sdk"],
        )

    def test_distribution_keeps_reproducible_runtime_dependencies(self) -> None:
        project = Path(__file__).parents[1]
        configuration = tomllib.loads(
            (project / "pyproject.toml").read_text(encoding="utf-8")
        )
        daemon_configuration = tomllib.loads(
            (project.parent / "workspace-fs" / "pyproject.toml").read_text(
                encoding="utf-8"
            )
        )

        self.assertIn(
            "baml-bridge @ git+https://github.com/jubjub727/baml.git"
            "@bbb99a793d707175663c4e9236400a9bcd830f57"
            "#subdirectory=baml_language/sdks/python",
            configuration["project"]["dependencies"],
        )
        self.assertIn(
            "reframe-workspace-daemon=="
            + daemon_configuration["project"]["version"],
            configuration["project"]["dependencies"],
        )
        self.assertNotIn("baml-bridge", configuration["tool"]["uv"]["sources"])
        self.assertEqual(
            configuration["tool"]["uv"]["sources"]["reframe-workspace-daemon"],
            {"path": "../workspace-fs"},
        )
        self.assertEqual(
            configuration["project"]["scripts"],
            {
                "reframe-agent-host": "reframe_agent_host.cli:main",
                "reframe-generate-baml": (
                    "reframe_agent_host.baml_generation:generate"
                ),
                "reframe-check-baml": "reframe_agent_host.baml_generation:check",
            },
        )


if __name__ == "__main__":
    unittest.main()
