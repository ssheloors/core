"""Test for the smhi weather entity."""

from datetime import timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from pysmhi import SMHIFireForecast, SmhiFireForecastException, SMHIFirePointForecast
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.smhi.sensor import (
    get_percentage_values,
    get_precipitation_category,
)
from homeassistant.const import STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import EntityRegistry

from tests.common import MockConfigEntry, async_fire_time_changed, snapshot_platform


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize(
    "load_platforms",
    [[Platform.SENSOR]],
)
async def test_sensor_setup(
    hass: HomeAssistant,
    entity_registry: EntityRegistry,
    load_int: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test for successfully setting up the smhi sensors."""

    await snapshot_platform(hass, entity_registry, snapshot, load_int.entry_id)


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_fire_sensor_coordinator_update(
    hass: HomeAssistant,
    mock_fire_client: SMHIFirePointForecast,
    load_int: MockConfigEntry,
    get_fire_data: tuple[list[SMHIFireForecast], list[SMHIFireForecast]],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that fire sensors update when the fire coordinator refreshes."""
    state = hass.states.get("sensor.test_fire_weather_index")
    assert state
    assert state.state == "6.6"

    fire_daily, _fire_hourly = get_fire_data
    # Shift the daily list forward one entry so a different fwi value is current
    mock_fire_client.async_get_daily_forecast.return_value = fire_daily[1:]

    freezer.tick(timedelta(minutes=35))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    new_state = hass.states.get("sensor.test_fire_weather_index")
    assert new_state
    assert new_state.state != state.state
    assert new_state.state == "0.2"


def test_get_percentage_values_out_of_range() -> None:
    """Test get_percentage_values turns out-of-range values to 0."""
    entity = MagicMock()
    entity.coordinator.current = {"thunder": 150}

    assert get_percentage_values(entity, "thunder") == 0


def test_get_percentage_values_none() -> None:
    """Test get_percentage_values returns None when the key is missing."""
    entity = MagicMock()
    entity.coordinator.current = {}

    assert get_percentage_values(entity, "thunder") is None


def test_get_precipitation_category_unknown() -> None:
    """Test get_precipitation_category returns None for an unmapped value."""
    entity = MagicMock()
    entity.coordinator.current = {"precipitation_category": 99}

    assert get_precipitation_category(entity) is None


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_refresh_fire_forecast_retry(
    hass: HomeAssistant,
    load_int: MockConfigEntry,
    mock_fire_client: SMHIFirePointForecast,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the fire coordinator handles SmhiFireForecastException."""
    mock_fire_client.async_get_daily_forecast.side_effect = SmhiFireForecastException()

    freezer.tick(timedelta(minutes=35))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.test_fire_weather_index")

    assert state
    assert state.state == STATE_UNAVAILABLE
    assert mock_fire_client.async_get_daily_forecast.call_count == 2
