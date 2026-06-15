"""Mock device control.

This is the spine for "Sunny controls every tech product I own". Right now it's
an in-memory simulation so the end-to-end flow (Claude -> tool -> state change ->
report back) is real and testable. When you stand up Home Assistant, replace the
body of `list_devices` / `set_state` with calls to its REST API — the function
signatures are what the brain depends on, so nothing above this layer changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Device:
    id: str
    name: str
    kind: str  # "light", "switch", "media", ...
    state: str  # "on" / "off" / free-form


@dataclass
class DeviceRegistry:
    """An in-memory stand-in for a real smart-home hub."""

    devices: dict[str, Device] = field(default_factory=dict)

    @classmethod
    def with_demo_devices(cls) -> "DeviceRegistry":
        reg = cls()
        for d in [
            Device("living_room_light", "Living room light", "light", "off"),
            Device("desk_lamp", "Desk lamp", "light", "off"),
            Device("speaker", "Living room speaker", "media", "paused"),
            Device("kettle", "Kitchen kettle", "switch", "off"),
        ]:
            reg.devices[d.id] = d
        return reg

    def list_devices(self) -> list[dict]:
        return [
            {"id": d.id, "name": d.name, "kind": d.kind, "state": d.state}
            for d in self.devices.values()
        ]

    def set_state(self, device_id: str, state: str) -> dict:
        d = self.devices.get(device_id)
        if d is None:
            known = ", ".join(self.devices) or "(none)"
            raise KeyError(f"Unknown device '{device_id}'. Known devices: {known}")
        d.state = state
        return {"id": d.id, "name": d.name, "kind": d.kind, "state": d.state}


def build_devices(config):
    """Use real Home Assistant devices when configured, else the demo mock."""
    if config.has_home_assistant:
        from .home_assistant import HomeAssistantDevices

        return HomeAssistantDevices(config.ha_url, config.ha_token)
    return DeviceRegistry.with_demo_devices()
