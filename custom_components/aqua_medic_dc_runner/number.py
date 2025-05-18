import logging
import asyncio
from datetime import timedelta
from homeassistant.components.number import NumberEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, DEFAULT_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Aqua Medic number entities for motor speed and update interval."""
    data = hass.data[DOMAIN][entry.entry_id]
    client = data["client"]
    coordinator = data["coordinator"]

    devices = await client.get_devices()
    if not devices:
        _LOGGER.error("❌ No devices found in Aqua Medic integration.")
        return

    device_id = devices[0]["did"]

    async_add_entities([
        AquaMedicMotorSpeed(client, device_id, coordinator, entry),
        AquaMedicUpdateInterval(entry, device_id)
    ])


class AquaMedicMotorSpeed(CoordinatorEntity, NumberEntity):
    """Number entity to control Aqua Medic motor speed."""

    def __init__(self, client, device_id, coordinator, entry):
        """Initialize the number entity."""
        super().__init__(coordinator, context=device_id)
        self._client = client
        self._device_id = device_id
        self._attr_name = "Speed"
        self._attr_unique_id = f"aqua_medic_dc_runner_{device_id}_speed"
        self._attr_native_min_value = 30
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self.entity_id = f"number.aqua_medic_dc_runner_{device_id}_speed"
        self._is_updating = False  # Track if we're currently updating

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
            return None  # Let HA handle the unknown state

        # Ensure we extract the correct JSON format from API response
        device_data = self.coordinator.data.get("attr", {})
        if not device_data:
            return None  # Let HA handle the unknown state

        motor_speed = device_data.get("Motor_Speed")

        # Only return the actual API value
        return motor_speed

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success

    async def async_set_native_value(self, value: float):
        """Set motor speed."""
        _LOGGER.info(f"Setting speed to {value} for device {self._device_id}")
        
        # Prevent concurrent updates
        if self._is_updating:
            _LOGGER.warning("Already updating, skipping")
            return
            
        self._is_updating = True
        
        try:
            result = await self._client.set_motor_speed(self._device_id, int(value))
            _LOGGER.info(f"set_motor_speed result: {result}")
            
            if result:
                # Wait a bit for the device to process
                await asyncio.sleep(2)
                
                # Force immediate coordinator refresh to get current state
                await self.coordinator.async_request_refresh()
                
                # Poll for confirmation
                for attempt in range(5):
                    await asyncio.sleep(2)
                    
                    # Force a fresh API call
                    new_data = await self._client.get_latest_device_data(self._device_id)
                    if new_data and "attr" in new_data:
                        actual_speed = new_data["attr"].get("Motor_Speed")
                        _LOGGER.info(f"Attempt {attempt + 1}: API reports speed={actual_speed}, expected={value}")
                        
                        # Update coordinator with fresh data
                        self.coordinator.data = new_data
                        
                        if actual_speed == int(value):
                            _LOGGER.info("Speed confirmed by device")
                            break
                    else:
                        _LOGGER.warning(f"Attempt {attempt + 1}: No valid data from API")
                
                # Final refresh to ensure we have the latest state
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("Failed to set motor speed")
                
        except Exception as e:
            _LOGGER.error(f"Error setting speed: {e}")
        finally:
            self._is_updating = False


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

    async def async_set_native_value(self, value: float) -> None:
        """Set the update interval value."""
        self._attr_native_value = int(value)
        self.async_write_ha_state()