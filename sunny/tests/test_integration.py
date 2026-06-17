"""Integration test: verify the complete Sunny system works end-to-end."""

import time
from types import SimpleNamespace

from sunny.brain import Brain
from sunny.memory import Store
from sunny.server import build_status
from sunny.tools.devices import DeviceRegistry


def test_complete_sunny_flow(tmp_path):
    """Verify the complete system: memory, reminders, activity tracking, telemetry."""
    # Initialize Sunny with a fresh database
    store = Store(tmp_path / "sunny.db")
    config = SimpleNamespace(
        has_brain=True,
        has_home_assistant=False,
        model="claude-opus-4-8",
        briefing_time="08:00",
    )
    brain = Brain(
        config,
        store,
        SimpleNamespace(push=lambda *a, **k: None),
        DeviceRegistry.with_demo_devices(),
        SimpleNamespace(),
        client=object(),
    )

    # Verify initial state
    initial_status = build_status(brain, config)
    assert initial_status["telemetry"]["memories"] == 0
    assert initial_status["telemetry"]["reminders"] == 0
    assert initial_status["telemetry"]["messages"] == 0
    assert initial_status["telemetry"]["events"] == 0

    # Add some memories and verify they're counted
    brain.store.remember("my favorite color is blue", tag="preference")
    brain.store.remember("i live in NYC", tag="location")
    status = build_status(brain, config)
    assert status["telemetry"]["memories"] == 2

    # Verify memory planet lights up when tool is used
    assert not brain.is_active("memory")
    brain._run_tool("recall", {"query": "color"})
    assert brain.is_active("memory")

    # Add reminders and verify they're counted
    now = int(time.time())
    brain.store.add_reminder("drink water", now + 3600)
    brain.store.add_reminder("call mom", now + 7200)
    status = build_status(brain, config)
    assert status["telemetry"]["reminders"] == 2
    # Verify reminders planet lights when tool is used
    brain._run_tool("list_reminders", {})
    assert brain.is_active("reminders")

    # Verify upgrade channel lights for self-improvement tools
    assert not brain.is_active("upgrade")
    brain._run_tool("list_my_files", {})
    assert brain.is_active("upgrade")

    # Verify web channel activity tracking
    assert not brain.is_active("web")
    brain.mark_active("web")
    assert brain.is_active("web")

    # Verify uptime is real (time.time() was called at init)
    status = build_status(brain, config)
    uptime_str = status["telemetry"]["uptime"]
    assert "s" in uptime_str or "m" in uptime_str or "h" in uptime_str

    # Verify all 12 planets + sun are present
    node_ids = [n["id"] for n in status["nodes"]]
    assert len(node_ids) == 13  # 12 planets + sun
    expected_planets = {
        "sun", "search", "memory", "phone", "voice", "watch",
        "upgrade", "home", "reminders", "web", "briefing", "host", "log"
    }
    assert set(node_ids) == expected_planets

    # Verify briefing node state matches configuration
    briefing_node = next(n for n in status["nodes"] if n["id"] == "briefing")
    assert briefing_node["state"] == "online"  # scheduled at 08:00
    assert "08:00" in briefing_node["info"]

    # Verify host node shows uptime
    host_node = next(n for n in status["nodes"] if n["id"] == "host")
    assert host_node["state"] == "online"
    assert "up" in host_node["info"]


def test_phone_bridge_connectivity(tmp_path):
    """Verify phone bridge state is reflected in telemetry."""
    config = SimpleNamespace(
        has_brain=True,
        has_home_assistant=False,
        model="claude-opus-4-8",
        briefing_time="",
    )
    store = Store(tmp_path / "sunny.db")
    brain = Brain(
        config,
        store,
        SimpleNamespace(push=lambda *a, **k: None),
        DeviceRegistry.with_demo_devices(),
        SimpleNamespace(),
        client=object(),
    )

    # Phone offline by default
    status = build_status(brain, config)
    phone_node = next(n for n in status["nodes"] if n["id"] == "phone")
    assert phone_node["state"] == "offline"

    # Mark phone online
    brain.phone_online = True
    status = build_status(brain, config)
    phone_node = next(n for n in status["nodes"] if n["id"] == "phone")
    assert phone_node["state"] == "online"

    # Mark phone offline again
    brain.phone_online = False
    status = build_status(brain, config)
    phone_node = next(n for n in status["nodes"] if n["id"] == "phone")
    assert phone_node["state"] == "offline"
