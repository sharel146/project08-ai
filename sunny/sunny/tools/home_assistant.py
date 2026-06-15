"""Real device control via Home Assistant's REST API.

This is the real-hardware counterpart to the mock DeviceRegistry. It's used
automatically when HA_URL and HA_TOKEN are set (see tools/devices.build_devices);
otherwise Sunny falls back to the simulated registry, so nothing breaks before
you've set up Home Assistant.

To get HA_TOKEN: in Home Assistant, click your profile (bottom-left) -> Security
-> Long-Lived Access Tokens -> Create Token. HA_URL is your HA address, e.g.
http://homeassistant.local:8123 or http://<its-ip>:8123.

The pure helpers (entity_to_device / service_call_for) hold the mapping logic so
it can be tested without a live Home Assistant.
"""

from __future__ import annotations

import requests

# Entity domains Sunny will surface and control.
CONTROLLABLE_DOMAINS = {
    "light",
    "switch",
    "fan",
    "input_boolean",
    "media_player",
    "cover",
    "lock",
}


def entity_to_device(entity: dict) -> dict | None:
    """Convert a Home Assistant state object into Sunny's device shape, or None
    if it's not something we should control."""
    entity_id = entity.get("entity_id", "")
    domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    if domain not in CONTROLLABLE_DOMAINS:
        return None
    attrs = entity.get("attributes") or {}
    return {
        "id": entity_id,
        "name": attrs.get("friendly_name") or entity_id,
        "kind": domain,
        "state": entity.get("state", "unknown"),
    }


def service_call_for(device_id: str, desired_state: str) -> tuple[str, str, str]:
    """Map (entity_id, desired_state) to the HA (domain, service, entity_id) call."""
    domain = device_id.split(".", 1)[0] if "." in device_id else device_id
    s = desired_state.strip().lower()
    if s in ("on", "true", "1", "open", "unlock", "unlocked"):
        service = "turn_on"
    elif s in ("off", "false", "0", "closed", "lock", "locked"):
        service = "turn_off"
    elif s in ("play", "resume"):
        service = "media_play"
    elif s in ("pause", "stop"):
        service = "media_pause"
    else:
        raise ValueError(f"Don't know how to set state '{desired_state}'.")
    return domain, service, device_id


class HomeAssistantDevices:
    def __init__(self, base_url: str, token: str, *, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self._session = session or requests.Session()
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def list_devices(self) -> list[dict]:
        resp = self._session.get(
            f"{self.base_url}/api/states", headers=self._headers, timeout=15
        )
        resp.raise_for_status()
        devices = []
        for entity in resp.json():
            dev = entity_to_device(entity)
            if dev is not None:
                devices.append(dev)
        return devices

    def set_state(self, device_id: str, state: str) -> dict:
        domain, service, entity_id = service_call_for(device_id, state)
        resp = self._session.post(
            f"{self.base_url}/api/services/{domain}/{service}",
            headers=self._headers,
            json={"entity_id": entity_id},
            timeout=15,
        )
        resp.raise_for_status()
        # Read back the entity's actual state for an accurate report.
        cur = self._session.get(
            f"{self.base_url}/api/states/{entity_id}",
            headers=self._headers,
            timeout=15,
        )
        if cur.ok:
            dev = entity_to_device(cur.json())
            if dev is not None:
                return dev
        return {"id": entity_id, "name": entity_id, "kind": domain, "state": state}
