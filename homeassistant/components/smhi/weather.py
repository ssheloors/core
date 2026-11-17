"""Support for the Swedish weather institute weather service."""

from collections.abc import Mapping
from typing import Any, Final, override

from pysmhi import SMHIFireForecast, SMHIForecast

from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_CLOUDY,
    ATTR_CONDITION_EXCEPTIONAL,
    ATTR_CONDITION_FOG,
    ATTR_CONDITION_HAIL,
    ATTR_CONDITION_LIGHTNING,
    ATTR_CONDITION_LIGHTNING_RAINY,
    ATTR_CONDITION_PARTLYCLOUDY,
    ATTR_CONDITION_POURING,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_SNOWY_RAINY,
    ATTR_CONDITION_SUNNY,
    ATTR_CONDITION_WINDY,
    ATTR_CONDITION_WINDY_VARIANT,
    ATTR_FORECAST_CLOUD_COVERAGE,
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_HUMIDITY,
    ATTR_FORECAST_IS_DAYTIME,
    ATTR_FORECAST_NATIVE_PRECIPITATION,
    ATTR_FORECAST_NATIVE_PRESSURE,
    ATTR_FORECAST_NATIVE_TEMP,
    ATTR_FORECAST_NATIVE_TEMP_LOW,
    ATTR_FORECAST_NATIVE_WIND_GUST_SPEED,
    ATTR_FORECAST_NATIVE_WIND_SPEED,
    ATTR_FORECAST_TIME,
    ATTR_FORECAST_WIND_BEARING,
    Forecast,
    SingleCoordinatorWeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import sun
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import slugify

from .const import (
    ATTR_SMHI_THUNDER_PROBABILITY,
    ENTITY_ID_SENSOR_FORMAT,
    FIRE_WEATHER_INDEX_CATEGORIES,
)
from .coordinator import SMHIConfigEntry, SMHIFireDataUpdateCoordinator
from .entity import SmhiFireEntity, SmhiWeatherEntity

ATTR_FIRE_WEATHER_INDEX = "fire_weather_index"
ATTR_FIRE_WEATHER_INDEX_CATEGORY = "fire_weather_index_category"
ATTR_GRASSFIRE = "grassfire"
ATTR_FOREST_DRYNESS = "forestdry"

# Used to map condition from API results
CONDITION_CLASSES: Final[dict[str, list[int]]] = {
    ATTR_CONDITION_CLOUDY: [5, 6],
    ATTR_CONDITION_FOG: [7],
    ATTR_CONDITION_HAIL: [],
    ATTR_CONDITION_LIGHTNING: [21],
    ATTR_CONDITION_LIGHTNING_RAINY: [11],
    ATTR_CONDITION_PARTLYCLOUDY: [3, 4],
    ATTR_CONDITION_POURING: [10, 20],
    ATTR_CONDITION_RAINY: [8, 9, 18, 19],
    ATTR_CONDITION_SNOWY: [15, 16, 17, 25, 26, 27],
    ATTR_CONDITION_SNOWY_RAINY: [12, 13, 14, 22, 23, 24],
    ATTR_CONDITION_SUNNY: [1, 2],
    ATTR_CONDITION_WINDY: [],
    ATTR_CONDITION_WINDY_VARIANT: [],
    ATTR_CONDITION_EXCEPTIONAL: [],
}
CONDITION_MAP = {
    cond_code: cond_ha
    for cond_ha, cond_codes in CONDITION_CLASSES.items()
    for cond_code in cond_codes
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SMHIConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a weather entity from map location."""
    location = config_entry.data

    coordinator = config_entry.runtime_data[0]

    entity = SmhiWeather(
        location[CONF_LOCATION][CONF_LATITUDE],
        location[CONF_LOCATION][CONF_LONGITUDE],
        coordinator=coordinator,
    )
    entity.entity_id = ENTITY_ID_SENSOR_FORMAT.format(slugify(config_entry.title))

    fire_entity = SmhiFire(
        location[CONF_LOCATION][CONF_LATITUDE],
        location[CONF_LOCATION][CONF_LONGITUDE],
        coordinator=config_entry.runtime_data[1],
    )
    fire_entity.entity_id = f"weather.smhi_{slugify(config_entry.title)}_fire_risk"

    async_add_entities([entity, fire_entity])


class SmhiWeather(SmhiWeatherEntity, SingleCoordinatorWeatherEntity):
    """Representation of a weather entity."""

    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY
        | WeatherEntityFeature.FORECAST_HOURLY
        | WeatherEntityFeature.FORECAST_TWICE_DAILY
    )
    _attr_name = None

    @override
    def update_entity_data(self) -> None:
        """Refresh the entity data."""
        if daily_data := self.coordinator.data.daily:
            self._attr_native_temperature = daily_data[0]["temperature"]
            self._attr_humidity = daily_data[0]["humidity"]
            self._attr_native_wind_speed = daily_data[0]["wind_speed"]
            self._attr_wind_bearing = daily_data[0]["wind_direction"]
            self._attr_native_visibility = daily_data[0]["visibility"]
            self._attr_native_pressure = daily_data[0]["pressure"]
            self._attr_native_wind_gust_speed = daily_data[0]["wind_gust"]
            self._attr_cloud_coverage = daily_data[0]["total_cloud"]
            self._attr_condition = CONDITION_MAP.get(daily_data[0]["symbol"])
            if self._attr_condition == ATTR_CONDITION_SUNNY and not sun.is_up(
                self.coordinator.hass
            ):
                self._attr_condition = ATTR_CONDITION_CLEAR_NIGHT

    @property
    @override
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional attributes."""
        if daily_data := self.coordinator.data.daily:
            return {
                ATTR_SMHI_THUNDER_PROBABILITY: daily_data[0]["thunder"],
            }
        return None

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.update_entity_data()
        super()._handle_coordinator_update()

    def _get_forecast_data(
        self, forecast_data: list[SMHIForecast] | None, forecast_type: str
    ) -> list[Forecast] | None:
        """Get forecast data."""
        if forecast_data is None or len(forecast_data) < 3:
            return None

        # Skip the first entry for daily and twice-daily forecasts.
        forecasts = forecast_data if forecast_type == "hourly" else forecast_data[1:]

        return [
            self._create_forecast(forecast, forecast_type) for forecast in forecasts
        ]

    @override
    def _async_forecast_daily(self) -> list[Forecast] | None:
        """Service to retrieve the daily forecast."""
        return self._get_forecast_data(self.coordinator.data.daily, "daily")

    @override
    def _async_forecast_hourly(self) -> list[Forecast] | None:
        """Service to retrieve the hourly forecast."""
        return self._get_forecast_data(self.coordinator.data.hourly, "hourly")

    @override
    def _async_forecast_twice_daily(self) -> list[Forecast] | None:
        """Service to retrieve the twice daily forecast."""
        return self._get_forecast_data(self.coordinator.data.twice_daily, "twice_daily")

    def _get_forecast_condition(self, forecast: SMHIForecast) -> str | None:
        """Get the weather condition for a forecast."""
        condition = CONDITION_MAP.get(forecast["symbol"])

        if condition == ATTR_CONDITION_SUNNY and not sun.is_up(
            self.hass, forecast["valid_time"]
        ):
            return ATTR_CONDITION_CLEAR_NIGHT

        return condition

    def _create_forecast(self, forecast: SMHIForecast, forecast_type: str) -> Forecast:
        """Create a Home Assistant forecast from SMHI data."""
        new_forecast = Forecast(
            {
                ATTR_FORECAST_TIME: forecast["valid_time"].isoformat(),
                ATTR_FORECAST_NATIVE_TEMP: forecast["temperature_max"],
                ATTR_FORECAST_NATIVE_TEMP_LOW: forecast["temperature_min"],
                ATTR_FORECAST_NATIVE_PRECIPITATION: forecast.get("total_precipitation")
                or forecast["mean_precipitation"],
                ATTR_FORECAST_CONDITION: self._get_forecast_condition(forecast),
                ATTR_FORECAST_NATIVE_PRESSURE: forecast["pressure"],
                ATTR_FORECAST_WIND_BEARING: forecast["wind_direction"],
                ATTR_FORECAST_NATIVE_WIND_SPEED: forecast["wind_speed"],
                ATTR_FORECAST_HUMIDITY: forecast["humidity"],
                ATTR_FORECAST_NATIVE_WIND_GUST_SPEED: forecast["wind_gust"],
                ATTR_FORECAST_CLOUD_COVERAGE: forecast["total_cloud"],
            }
        )

        if forecast_type == "twice_daily":
            new_forecast[ATTR_FORECAST_IS_DAYTIME] = forecast["valid_time"].hour == 12

        return new_forecast


class SmhiFire(SmhiFireEntity, SingleCoordinatorWeatherEntity):
    """Class for the fire forecast."""

    _attr_condition = ATTR_CONDITION_EXCEPTIONAL
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )
    _attr_name = "Fire risk"

    def __init__(
        self,
        latitude: str,
        longitude: str,
        coordinator: SMHIFireDataUpdateCoordinator,
    ) -> None:
        """Initialize the fire risk entity."""
        super().__init__(latitude, longitude, coordinator)
        self._attr_unique_id = f"{latitude}, {longitude}-fire-risk"

    @override
    def update_entity_data(self) -> None:
        """Refresh the current fire risk data."""
        if fire_data := self.coordinator.data.fire_daily:
            current = fire_data[0]
            self._attr_native_temperature = current["fwi"]
            self._attr_humidity = current["fwiindex"]
            self._attr_native_wind_speed = current["isi"]
            self._attr_wind_bearing = current["grassfire"]
            self._attr_uv_index = current["forestdry"]

    @property
    @override
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the current fire risk metrics."""
        if not self.coordinator.data.fire_daily:
            return None

        current = self.coordinator.data.fire_daily[0]
        return {
            ATTR_FIRE_WEATHER_INDEX: current["fwi"],
            ATTR_FIRE_WEATHER_INDEX_CATEGORY: FIRE_WEATHER_INDEX_CATEGORIES.get(
                current["fwiindex"]
            ),
            ATTR_GRASSFIRE: current["grassfire"],
            ATTR_FOREST_DRYNESS: current["forestdry"],
            "fire_temperature": current["temperature"],
            "initial_spread_index": current["isi"],
            "build_up_index": current["bui"],  # codespell:ignore bui
            "fine_fuel_moisture_code": current["ffmc"],
            "duff_moisture_code": current["dmc"],
            "drought_code": current["dc"],
            "rate_of_spread": current["rn"],
        }

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()

    @override
    def _async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily fire risk forecast."""
        return self._get_fire_forecast_data(
            self.coordinator.data.fire_daily, daily=True
        )

    @override
    def _async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the hourly fire risk forecast."""
        return self._get_fire_forecast_data(
            self.coordinator.data.fire_hourly, daily=False
        )

    def _get_fire_forecast_data(
        self, forecast_data: list[SMHIFireForecast], *, daily: bool
    ) -> list[Forecast] | None:
        """Convert SMHI fire data to Home Assistant forecasts."""
        if len(forecast_data) < 3:
            return None

        forecasts = forecast_data[1:] if daily else forecast_data
        return [self._create_fire_forecast(forecast) for forecast in forecasts]

    def _create_fire_forecast(self, forecast: SMHIFireForecast) -> Forecast:
        """Create a Home Assistant forecast from SMHI fire data."""
        return Forecast(
            {
                ATTR_FORECAST_TIME: forecast["valid_time"].isoformat(),
                ATTR_FORECAST_CONDITION: ATTR_CONDITION_EXCEPTIONAL,
                ATTR_FORECAST_NATIVE_TEMP: forecast["fwi"],
                ATTR_FORECAST_NATIVE_WIND_SPEED: forecast["wind_speed"],
                ATTR_FORECAST_WIND_BEARING: forecast["wind_direction"],
                ATTR_FORECAST_HUMIDITY: forecast["humidity"],
            }
        )
