import pytest

from sunny.tools.home_assistant import entity_to_device, service_call_for


def test_entity_to_device_maps_controllable():
    dev = entity_to_device(
        {
            "entity_id": "light.desk_lamp",
            "state": "off",
            "attributes": {"friendly_name": "Desk lamp"},
        }
    )
    assert dev == {"id": "light.desk_lamp", "name": "Desk lamp", "kind": "light", "state": "off"}


def test_entity_to_device_skips_non_controllable():
    assert entity_to_device({"entity_id": "sensor.temperature", "state": "21"}) is None


def test_entity_to_device_falls_back_to_entity_id_for_name():
    dev = entity_to_device({"entity_id": "switch.kettle", "state": "on", "attributes": {}})
    assert dev["name"] == "switch.kettle"


def test_service_call_on_off():
    assert service_call_for("light.desk", "on") == ("light", "turn_on", "light.desk")
    assert service_call_for("light.desk", "OFF") == ("light", "turn_off", "light.desk")


def test_service_call_media_and_unknown():
    assert service_call_for("media_player.tv", "pause") == (
        "media_player", "media_pause", "media_player.tv",
    )
    with pytest.raises(ValueError):
        service_call_for("light.desk", "disco")
