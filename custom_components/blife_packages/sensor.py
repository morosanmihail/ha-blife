"""Sensor platform for BLife Packages integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_PACKAGES,
    CONF_API_URL,
    DOMAIN,
    SENSOR_PACKAGES_COUNT,
)
from .coordinator import BLifePackagesCoordinator, BLifePackagesData


@dataclass(frozen=True, kw_only=True)
class BLifePackagesSensorEntityDescription(SensorEntityDescription):
    """Describe BLife Packages sensor entity."""

    value_fn: Callable[[BLifePackagesData], Any]
    extra_state_attributes_fn: Callable[[BLifePackagesData], dict[str, Any]] | None = (
        None
    )


def get_sensor_descriptions(firstname: str) -> list[BLifePackagesSensorEntityDescription]:
    """Generate sensor descriptions with dynamic naming based on firstname."""
    return [
        BLifePackagesSensorEntityDescription(
            key=SENSOR_PACKAGES_COUNT,
            translation_key="packages_ready_to_collect",
            name=f"{firstname} Packages Ready to Collect",
            icon="mdi:package-variant",
            native_unit_of_measurement="packages",
            value_fn=lambda data: data.packages_ready_to_collect,
            extra_state_attributes_fn=lambda data: {
                ATTR_PACKAGES: [
                    p.to_dict()
                    for p in data.packages
                    if p.status == "pending"
                ],
            },
        ),
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BLife Packages sensors based on a config entry."""
    coordinator: BLifePackagesCoordinator = hass.data[DOMAIN][entry.entry_id]

    firstname = entry.data.get("firstname", "User")
    async_add_entities(
        BLifePackagesSensor(
            coordinator=coordinator,
            description=description,
            entry=entry,
        )
        for description in get_sensor_descriptions(firstname)
    )


class BLifePackagesSensor(
    CoordinatorEntity[BLifePackagesCoordinator], SensorEntity
):
    """Representation of a BLife Packages sensor."""

    entity_description: BLifePackagesSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BLifePackagesCoordinator,
        description: BLifePackagesSensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        unique_key = entry.data.get(CONF_API_URL) or entry.entry_id
        self._attr_unique_id = f"{unique_key}_{description.key}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_key)},
            name=f"BLife Concierge ({entry.data.get('firstname', 'User')})",
            manufacturer="BLife",
            model="Concierge Packages",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if self.entity_description.extra_state_attributes_fn is None:
            return None
        return self.entity_description.extra_state_attributes_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.coordinator.data is not None
