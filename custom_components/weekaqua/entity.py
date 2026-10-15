"""Base entity for Week Aqua."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .device import WeekAquaDevice


class WeekAquaEntity(Entity):
    """Common device info."""

    _attr_has_entity_name = True

    def __init__(self, device: WeekAquaDevice, key: str) -> None:
        self._device = device
        self._attr_unique_id = f"{device.address}_{key}"
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, device.address)},
            name=device.name,
            manufacturer="Week Aqua",
            model="Bluetooth light (model code 5746)",
        )
