# mypy: ignore-errors
"""Support for SMHI fire readings."""

from typing import override

from homeassistant.const import CONF_LATITUDE, CONF_LOCATION, CONF_LONGITUDE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SMHIConfigEntry
from .entity import SmhiFireEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SMHIConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a weather entity from map location."""
    location = config_entry.data

    coordinator = config_entry.runtime_data[0]

    entity = SmhiFire(
        location[CONF_LOCATION][CONF_LATITUDE],
        location[CONF_LOCATION][CONF_LONGITUDE],
        coordinator=coordinator,
    )
    async_add_entities(entity, update_before_add=True)


class SmhiFire(SmhiFireEntity):
    """Class for the fire forecast."""

    _data = None

    @override
    def update_entity_data(self):
        if daily_data := self.coordinator.data.daily:
            self._data = daily_data[0]
            # print(daily_data)

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.update_entity_data()
        super()._handle_coordinator_update()

    @override
    def _async_fire_forecast_hourly(self):
        super().handle_coordinator_update()
