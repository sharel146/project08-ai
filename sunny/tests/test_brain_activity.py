from types import SimpleNamespace

from sunny.brain import Brain
from sunny.memory import Store
from sunny.tools.devices import DeviceRegistry


def _brain(tmp_path):
    return Brain(
        SimpleNamespace(model="m", effort="high", anthropic_api_key="k"),
        Store(tmp_path / "t.db"),
        SimpleNamespace(push=lambda *a, **k: None),
        DeviceRegistry.with_demo_devices(),
        SimpleNamespace(),
        client=object(),  # avoid real network
    )


def test_tools_light_their_real_planet(tmp_path):
    brain = _brain(tmp_path)
    # Nothing is active before anything runs — no faking.
    assert not brain.is_active("memory")
    assert not brain.is_active("reminders")

    brain._run_tool("recall", {"query": "x"})
    assert brain.is_active("memory")

    brain._run_tool("list_reminders", {})
    assert brain.is_active("reminders")

    brain._run_tool("list_devices", {})
    assert brain.is_active("home")

    # A tool that maps to no planet does not light anything spurious.
    brain._run_tool("list_my_files", {})
    assert not brain.is_active("voice")
    assert not brain.is_active("search")
