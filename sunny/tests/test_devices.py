import pytest

from sunny.tools.devices import DeviceRegistry


def test_demo_registry_lists_devices():
    reg = DeviceRegistry.with_demo_devices()
    ids = {d["id"] for d in reg.list_devices()}
    assert "living_room_light" in ids


def test_set_state_changes_device():
    reg = DeviceRegistry.with_demo_devices()
    result = reg.set_state("desk_lamp", "on")
    assert result["state"] == "on"
    assert reg.devices["desk_lamp"].state == "on"


def test_unknown_device_raises():
    reg = DeviceRegistry.with_demo_devices()
    with pytest.raises(KeyError):
        reg.set_state("teleporter", "on")
