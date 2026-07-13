from __future__ import annotations

import json
import unittest
from unittest import mock

from baml_sdk import task_catalog as baml_task_catalog
from baml_sdk import task as baml_task
from baml_sdk import turn_context as baml_turn_context
from baml_sdk import memory as baml_memory
from reframe_agent_host.agent_flow import geolocation, machine_state, monitor_detection
from reframe_agent_host.agent_flow import windows_monitors
from reframe_agent_host.agent_flow.machine_state import (
    MachineGeolocation,
    MachineMonitor,
    MachineStateError,
    MachineStateProvider,
    fetch_ip_geolocation,
)


class MachineStateProviderTests(unittest.TestCase):
    def test_provider_requires_loaded_geolocation_before_context(self) -> None:
        provider = MachineStateProvider(
            fetcher=lambda: MachineGeolocation(
                source="test",
                ip_address="203.0.113.10",
                country="New Zealand",
                country_code="NZ",
                region="Wellington",
                city="Wellington",
                latitude="-41.29",
                longitude="174.78",
                timezone_name="Pacific/Auckland",
            ),
        )

        with self.assertRaisesRegex(MachineStateError, "has not loaded"):
            provider.context()

        with mock.patch.object(
            machine_state,
            "machine_os_architecture",
            return_value="Windows x86_64",
        ) as os_loader:
            provider.start()
            provider.wait_until_ready()

        monitor_snapshots = [
            [
                MachineMonitor(
                    horizontal_resolution=1920,
                    vertical_resolution=1080,
                )
            ],
            [
                MachineMonitor(
                    horizontal_resolution=2560,
                    vertical_resolution=1440,
                )
            ],
        ]
        with mock.patch.object(
            machine_state,
            "machine_monitors",
            side_effect=monitor_snapshots,
        ) as monitor_loader:
            context = provider.context()
            next_context = provider.context()

        self.assertEqual(context.geolocation_status, "available")
        self.assertEqual(context.os_architecture, "Windows x86_64")
        self.assertEqual(next_context.os_architecture, "Windows x86_64")
        self.assertEqual(context.geolocation_source, "test")
        self.assertEqual(context.country_code, "NZ")
        self.assertEqual(context.geolocation_timezone, "Pacific/Auckland")
        self.assertEqual(context.monitor_count, 1)
        self.assertEqual(context.monitors[0].horizontal_resolution, 1920)
        self.assertEqual(context.monitors[0].vertical_resolution, 1080)
        self.assertEqual(next_context.monitor_count, 1)
        self.assertEqual(next_context.monitors[0].horizontal_resolution, 2560)
        self.assertEqual(next_context.monitors[0].vertical_resolution, 1440)
        self.assertRegex(context.utc_offset, r"^[+-]\d{2}:\d{2}$")
        self.assertEqual(monitor_loader.call_count, 2)
        os_loader.assert_called_once_with()

    def test_os_architecture_is_normalized(self) -> None:
        with mock.patch.object(machine_state.platform, "system", return_value="Darwin"):
            with mock.patch.object(
                machine_state.platform,
                "machine",
                return_value="aarch64",
            ):
                self.assertEqual(machine_state.machine_os_architecture(), "macOS arm64")

        with mock.patch.object(machine_state.platform, "system", return_value="Windows"):
            with mock.patch.object(
                machine_state.platform,
                "machine",
                return_value="AMD64",
            ):
                self.assertEqual(
                    machine_state.machine_os_architecture(),
                    "Windows x86_64",
                )

    def test_monitor_geometry_uses_physical_resolution_when_available(self) -> None:
        class Rect:
            left = 1920
            top = 0
            right = 4114
            bottom = 1234

        geometry = windows_monitors.monitor_geometry_from_rect(Rect(), (3840, 2160))

        self.assertEqual(
            geometry,
            monitor_detection.MonitorGeometry(
                x=1920,
                y=0,
                width=3840,
                height=2160,
            ),
        )

    def test_monitor_detection_collapses_mirrored_duplicate_geometry(self) -> None:
        with mock.patch.object(
            monitor_detection,
            "_detect_monitor_geometries",
            return_value=[
                monitor_detection.MonitorGeometry(x=0, y=0, width=1920, height=1080),
                monitor_detection.MonitorGeometry(x=0, y=0, width=1920, height=1080),
                monitor_detection.MonitorGeometry(x=1920, y=0, width=1920, height=1080),
            ],
        ):
            monitors = machine_state.machine_monitors()

        self.assertEqual(
            monitors,
            [
                MachineMonitor(
                    horizontal_resolution=1920,
                    vertical_resolution=1080,
                ),
                MachineMonitor(
                    horizontal_resolution=1920,
                    vertical_resolution=1080,
                ),
            ],
        )

    def test_xrandr_list_monitors_parser_keeps_extended_same_resolution(self) -> None:
        output = """Monitors: 2
 0: +*eDP-1 1920/344x1080/193+0+0  eDP-1
 1: +HDMI-1 1920/527x1080/296+1920+0  HDMI-1
"""

        with mock.patch.object(monitor_detection.platform, "system", return_value="Linux"):
            with mock.patch.object(
                monitor_detection,
                "_run_monitor_command",
                return_value=output,
            ):
                geometries = monitor_detection._xrandr_list_monitor_geometries()

        self.assertEqual(
            geometries,
            [
                monitor_detection.MonitorGeometry(x=0, y=0, width=1920, height=1080),
                monitor_detection.MonitorGeometry(
                    x=1920,
                    y=0,
                    width=1920,
                    height=1080,
                ),
            ],
        )

    def test_swaymsg_parser_uses_wayland_output_rectangles(self) -> None:
        payload = json.dumps(
            [
                {
                    "active": True,
                    "rect": {"x": 0, "y": 0, "width": 2560, "height": 1440},
                },
                {
                    "active": False,
                    "rect": {"x": 2560, "y": 0, "width": 1920, "height": 1080},
                },
            ]
        )

        with mock.patch.object(monitor_detection.platform, "system", return_value="Linux"):
            with mock.patch.object(
                monitor_detection,
                "_run_monitor_command",
                return_value=payload,
            ):
                geometries = monitor_detection._swaymsg_monitor_geometries()

        self.assertEqual(
            geometries,
            [
                monitor_detection.MonitorGeometry(x=0, y=0, width=2560, height=1440),
            ],
        )

    def test_macos_system_profiler_parser_reads_display_resolutions(self) -> None:
        payload = json.dumps(
            {
                "SPDisplaysDataType": [
                    {
                        "spdisplays_ndrvs": [
                            {"_spdisplays_resolution": "2560 x 1440 Retina"},
                            {"_spdisplays_resolution": "1920 x 1080"},
                        ]
                    }
                ]
            }
        )

        with mock.patch.object(
            monitor_detection,
            "_run_monitor_command",
            return_value=payload,
        ):
            geometries = monitor_detection._macos_system_profiler_monitors()

        self.assertEqual(
            geometries,
            [
                monitor_detection.MonitorGeometry(x=0, y=0, width=2560, height=1440),
                monitor_detection.MonitorGeometry(x=0, y=0, width=1920, height=1080),
            ],
        )

    def test_ip_geolocation_retries_until_provider_succeeds(self) -> None:
        calls: list[str] = []

        def fail_ipapi(timeout_seconds: float) -> MachineGeolocation:
            calls.append(f"ipapi:{timeout_seconds}")
            raise MachineStateError("ipapi down")

        def succeed_second_ipwho(timeout_seconds: float) -> MachineGeolocation:
            calls.append(f"ipwho:{timeout_seconds}")
            if calls.count(f"ipwho:{timeout_seconds}") == 1:
                raise MachineStateError("ipwho down")
            return MachineGeolocation(
                source="ipwho.is",
                ip_address="203.0.113.20",
                country_code="NZ",
            )

        with mock.patch.object(geolocation, "_fetch_ipapi", fail_ipapi):
            with mock.patch.object(geolocation, "_fetch_ipwho", succeed_second_ipwho):
                with mock.patch.object(geolocation.time, "sleep") as sleep:
                    result = fetch_ip_geolocation(
                        max_attempts=2,
                        retry_delay_seconds=0.25,
                        timeout_seconds=3.0,
                    )

        self.assertEqual(result.source, "ipwho.is")
        self.assertEqual(result.ip_address, "203.0.113.20")
        self.assertEqual(
            calls,
            ["ipapi:3.0", "ipwho:3.0", "ipapi:3.0", "ipwho:3.0"],
        )
        sleep.assert_called_once_with(0.25)

    def test_ip_geolocation_fails_after_configured_attempts(self) -> None:
        def fail_endpoint(_timeout_seconds: float) -> MachineGeolocation:
            raise MachineStateError("offline")

        with mock.patch.object(geolocation, "_fetch_ipapi", fail_endpoint):
            with mock.patch.object(geolocation, "_fetch_ipwho", fail_endpoint):
                with mock.patch.object(geolocation.time, "sleep") as sleep:
                    with self.assertRaisesRegex(
                        MachineStateError,
                        "IP geolocation failed after 3 attempts",
                    ):
                        fetch_ip_geolocation(
                            max_attempts=3,
                            retry_delay_seconds=0.1,
                            timeout_seconds=1.0,
                        )

        self.assertEqual(sleep.call_count, 2)


class MachineStatePromptLayerTests(unittest.IsolatedAsyncioTestCase):
    async def test_machine_state_is_rendered_in_context_layers_only(self) -> None:
        machine_context = _machine_context()
        selected_task = _selected_task()
        search_hints = _search_hints()

        included_requests = [
            await baml_task.ChooseTask__build_request_async(
                current_user_request="What time is it here?",
                current_conversation=None,
                session_memories=[],
                user_preferences=[],
                available_tasks=[_available_task()],
                task_choice_memories=[],
                machine_state=machine_context,
            ),
            await baml_memory.ChooseMemorySearch__build_request_async(
                current_user_request="What time is it here?",
                current_conversation=None,
                session_memories=[],
                selected_task=selected_task,
                conversation_evaluation_memories=[],
                machine_state=machine_context,
            ),
            await baml_memory.ChooseMemorySearchDepths__build_request_async(
                current_timestamp="2026-07-08T00:00:00Z",
                current_user_request="What time is it here?",
                current_conversation=None,
                session_memories=[],
                selected_task=selected_task,
                memory_search_hints=search_hints,
                search_domains=[
                    baml_memory.SearchDepthDomain(
                        id="task_catalog",
                        description="Task records.",
                        searches="Task nodes.",
                        hydrates="Task nodes.",
                    )
                ],
                search_depth_memories=[],
                machine_state=machine_context,
            ),
            await baml_memory.SelectRelevantMemories__build_request_async(
                current_user_request="What time is it here?",
                current_conversation=None,
                session_memories=[],
                selected_task=selected_task,
                candidate_memories=[],
                relevance_memories=[],
                machine_state=machine_context,
            ),
            await baml_task.ComposeTaskInput__build_request_async(
                current_user_request="What time is it here?",
                current_conversation=None,
                session_memories=[],
                selected_task=selected_task,
                selected_memories=[],
                task_prompt_memories=[],
                machine_state=machine_context,
            ),
        ]

        for request in included_requests:
            rendered = _rendered_request(request)
            self.assertIn("Machine state:", rendered)
            self.assertIn("current_local_time: 2026-07-08T12:34:56+12:00", rendered)
            self.assertIn("os_architecture: Windows x86_64", rendered)
            self.assertIn("monitor_count: 2", rendered)
            self.assertIn("horizontal_resolution: 2560", rendered)
            self.assertIn("vertical_resolution: 1440", rendered)
            self.assertIn("country_code: NZ", rendered)

        execution = await baml_task.PerformTask__build_request_async(
            full_task_prompt="Reply directly.",
        )
        review = await baml_task.SummariseActionHistory__build_request_async(
            current_conversation=None,
            recorded_action_history="No actions.",
        )

        self.assertNotIn("Machine state:", _rendered_request(execution))
        self.assertNotIn("Machine state:", _rendered_request(review))


def _machine_context() -> baml_turn_context.MachineStateContext:
    return baml_turn_context.MachineStateContext(
        captured_at_utc="2026-07-08T00:34:56Z",
        current_local_time="2026-07-08T12:34:56+12:00",
        current_utc_time="2026-07-08T00:34:56Z",
        timezone_name="Pacific/Auckland",
        utc_offset="+12:00",
        os_architecture="Windows x86_64",
        monitor_count=2,
        monitors=[
            baml_turn_context.MachineMonitorContext(
                horizontal_resolution=1920,
                vertical_resolution=1080,
            ),
            baml_turn_context.MachineMonitorContext(
                horizontal_resolution=2560,
                vertical_resolution=1440,
            ),
        ],
        geolocation_status="available",
        geolocation_source="test",
        ip_address="203.0.113.30",
        country="New Zealand",
        country_code="NZ",
        region="Wellington",
        city="Wellington",
        postal_code="6011",
        latitude="-41.29",
        longitude="174.78",
        geolocation_timezone="Pacific/Auckland",
        organization="Example ISP",
        asn="AS64500",
        geolocation_error=None,
    )


def _available_task() -> baml_task_catalog.AvailableTask:
    return baml_task_catalog.AvailableTask(
        id="task:reply",
        name="Reply to user",
        description="Reply directly.",
        input="The user's request.",
        output="A reply.",
        prompt="Reply directly.",
        provider_id="provider:test",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        read_at="NONE",
    )


def _selected_task() -> baml_task_catalog.SelectedTaskContext:
    task = _available_task()
    return baml_task_catalog.SelectedTaskContext(**task.model_dump())


def _search_hints() -> baml_memory.ConversationMemorySearchHints:
    return baml_memory.ConversationMemorySearchHints(
        tags=baml_memory.MemoryTagSearch(any_of=[], all_of=[], none_of=[]),
        strings=baml_memory.MemoryStringSearch(contains=[], equals=[]),
        candidate_memory=None,
    )


def _rendered_request(request) -> str:
    return json.dumps(json.loads(request.body))


if __name__ == "__main__":
    unittest.main()
