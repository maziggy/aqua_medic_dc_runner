import logging
import asyncio
from datetime import timedelta
from homeassistant.components.number import NumberEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from .const import DOMAIN, DEFAULT_UPDATE_INTERVAL
from .client import AquaMedicClient  # ✅ Ensure client is imported

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Aqua Medic number entities for motor speed and update interval."""
    client: AquaMedicClient = hass.data[DOMAIN][entry.entry_id]

    devices = await client.get_devices()
    if not devices:
        _LOGGER.error("❌ No devices found in Aqua Medic integration.")
        return

    device_id = devices[0]["did"]

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="aqua_medic_motor_speed_update",
        update_method=lambda: client.get_latest_device_data(device_id),
        update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    async_add_entities([
        AquaMedicMotorSpeed(client, device_id, coordinator, entry),
        AquaMedicUpdateInterval(entry, device_id)  # ✅ Pass `device_id` correctly
    ])

    _LOGGER.info("✅ Registered Motor Speed and Update Interval entities for device: %s", device_id)


class AquaMedicMotorSpeed(CoordinatorEntity, NumberEntity):
    """Number entity to control Aqua Medic motor speed."""

    def __init__(self, client, device_id, coordinator, entry):
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._client = client
        self._device_id = device_id
        self._attr_name = "Speed"
        self._attr_unique_id = f"aqua_medic_dc_runner_{device_id}_speed"
        self._attr_native_min_value = 30
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self.entity_id = f"number.aqua_medic_dc_runner_{device_id}_speed"

        # Ensure device_info correctly associates the entity with the device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_id)},
            "name": "Aqua Medic DC Runner",
            "manufacturer": "Aqua Medic",
            "model": "DC Runner Pump",
            "via_device": entry.entry_id,  # Link to parent device
        }

    @property
    def icon(self):
        return "mdi:fan-chevron-up"

    @property
    def native_value(self):
        """Return the current motor speed."""
        if not self.coordinator.data:
            _LOGGER.warning("⚠️ Coordinator data is None, returning last known speed.")
            return self._attr_native_value

        # Ensure we extract the correct JSON format from API response
        device_data = self.coordinator.data.get("attr", {})
        if not device_data:
            _LOGGER.warning("⚠️ API response is missing 'attr' field: %s", self.coordinator.data)
            return self._attr_native_value  # Return last known value

        motor_speed = device_data.get("Motor_Speed")

        _LOGGER.debug("📡 Motor Speed from API: %s", motor_speed)

        return motor_speed if motor_speed is not None else self._attr_native_value

    async def async_set_native_value(self, value: float):
        """Set motor speed."""
        _LOGGER.info("⚙️ Setting motor speed to %s for device %s", value, self._device_id)
        if await self._client.set_motor_speed(self._device_id, int(value)) is True:
            await self.async_update()

        # Force refresh from API after setting speed**
        await asyncio.sleep(2)
        _LOGGER.info("🔄 Fetching latest state after speed change")
        await self.coordinator.async_request_refresh()

    async def async_update(self):
        """Manually force a state update from the API when Home Assistant requests it."""
        _LOGGER.info("🔄 Manually fetching latest device data for %s", self._device_id)
        new_state = await self._client.get_latest_device_data(self._device_id)

        if new_state and "attr" in new_state:
            _LOGGER.info("✅ Successfully updated state: %s", new_state["attr"])
            self.coordinator.data = new_state
        else:
            _LOGGER.warning("⚠️ No 'attr' field found in API response.")

class AquaMedicUpdateInterval(NumberEntity):
    """Custom NumberEntity for controlling update interval."""

    def __init__(self, entry, device_id):
        """Initialize the entity"""
        self._attr_name = "Update Interval"
        self._attr_unique_id = f"aqua_medic_dc_runner_{device_id}_update_interval"
        self._attr_native_min_value = 5
        self._attr_native_max_value = 300
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = "seconds"
        self._attr_native_value = DEFAULT_UPDATE_INTERVAL
        self._attr_mode = "box"  # Ensures slider is used in UI
        self.entity_id = f"number.aqua_medic_dc_runner_{device_id}_update_interval"

        # Fix `via_device` issue by referencing `device_id` correctly
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_id)},  # Ensure correct device ID is used
            "name": "Aqua Medic DC Runner",
            "manufacturer": "Aqua Medic",
            "model": "DC Runner Pump",
            "via_device": device_id,  # Fix the incorrect via_device reference
        }

    @property
    def icon(self):
        return "mdi:camera-timer"

    def set_native_value(self, value: float) -> None:
        """Set the update interval value"""
        self._attr_native_value = int(value)
        self.schedule_update_ha_state()
        _LOGGER.info(f"🔄 Update interval changed to {int(value)} seconds")
