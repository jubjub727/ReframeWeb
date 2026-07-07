from __future__ import annotations

import unittest
from unittest import mock

from reframe_agent_host import cli


class CliInterruptTests(unittest.TestCase):
    def test_voice_turn_keyboard_interrupt_exits_quietly(self) -> None:
        def interrupt(coro):
            coro.close()
            raise KeyboardInterrupt

        with mock.patch(
            "reframe_agent_host.cli.asyncio.run",
            side_effect=interrupt,
        ):
            exit_code = cli._run_voice_turn(object())

        self.assertEqual(exit_code, 130)


if __name__ == "__main__":
    unittest.main()
