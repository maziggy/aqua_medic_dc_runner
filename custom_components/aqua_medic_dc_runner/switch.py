import logging
import asyncio
from datetime import timedelta, datetime
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from .const import DOMAIN
from .client import AquaMedicClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Aqua Medic switch entity."""
    data = hass.data[DOMAIN][entry.entry_id]
    client = data["client"]
    coordinator = data["coordinator"]

    # Get device_id from configuration (token-based setup) or legacy device list
    if "device_id" in entry.data:
        device_id = entry.data["device_id"]
    else:
        # Legacy setup - get from devices list
        devices = await client.get_devices()
        if not devices:
            _LOGGER.error("No devices found in Aqua Medic integration.")
            return
        device_id = devices[0]["did"]

    async_add_entities([AquaMedicPowerSwitch(client, device_id, coordinator, entry)])


class AquaMedicPowerSwitch(CoordinatorEntity, SwitchEntity):
    """Switch entity to control Aqua Medic power."""

    def __init__(self, client, device_id, coordinator, entry):
        """Initialize the switch."""
        super().__init__(coordinator)
        self._client = client
        self._device_id = device_id
        self._attr_name = "Power"
        self._attr_unique_id = f"aqua_medic_dc_runner_{device_id}_power"
        self._entry = entry  # 🔹 Store entry for later reference
        self.entity_id = f"switch.aqua_medic_dc_runner_{device_id}_power"
        self._expected_state = None  # Track expected state during updates
        self._expected_state_until = None  # Track when to stop using expected state

    @property
    def is_on(self):
        """Return true if switch is on."""
        # If we're expecting a specific state and haven't reached the timeout
        if self._expected_state is not None and self._expected_state_until:
            if datetime.now() < self._expected_state_until:
                return self._expected_state
            else:
                # Timeout reached, clear expected state
                self._expected_state = None
                self._expected_state_until = None
            
        if not isinstance(self.coordinator.data, dict):  # Ensure it's a dict
            return None  # Let HA handle the unknown state

        if "attr" not in self.coordinator.data:
            return None  # Let HA handle the unknown state

        device_data = self.coordinator.data["attr"]

        switch_state = device_data.get("SwitchON", device_data.get("PowerState", 0))


        return switch_state == 1

    @property
    def device_info(self):
        """Return device information for Home Assistant device registry."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": "Aqua Medic DC Runner",
            "manufacturer": "Aqua Medic",
            "model": "DC Runner",
        }

    @property
    def icon(self):
        """Return the icon for the switch."""
        return "mdi:power-plug" if self.is_on else "mdi:power-plug-off"

    async def async_turn_on(self, **kwargs):
        """Turn the switch on and refresh state."""
        if await self._client.set_power(self._device_id, True):
            # Store the expected state with timeout
            self._expected_state = True
            self._expected_state_until = datetime.now() + timedelta(seconds=10)
            
            # Update coordinator data immediately for responsive UI
            if self.coordinator.data and "attr" in self.coordinator.data:
                self.coordinator.data["attr"]["SwitchON"] = 1
                # Also update PowerState if it exists
                if "PowerState" in self.coordinator.data["attr"]:
                    self.coordinator.data["attr"]["PowerState"] = 1
            else:
                # Create minimal data structure if it doesn't exist
                self.coordinator.data = {"attr": {"SwitchON": 1}}
            
            # Notify Home Assistant of the state change
            self.async_write_ha_state()
            
            # Wait a moment for the device to process
            await asyncio.sleep(2)
            
            # Request a refresh from the coordinator
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off and refresh state."""
        if await self._client.set_power(self._device_id, False):
            # Store the expected state with timeout
            self._expected_state = False
            self._expected_state_until = datetime.now() + timedelta(seconds=10)
            
            # Update coordinator data immediately for responsive UI
            if self.coordinator.data and "attr" in self.coordinator.data:
                self.coordinator.data["attr"]["SwitchON"] = 0
                # Also update PowerState if it exists
                if "PowerState" in self.coordinator.data["attr"]:
                    self.coordinator.data["attr"]["PowerState"] = 0
            else:
                # Create minimal data structure if it doesn't exist
                self.coordinator.data = {"attr": {"SwitchON": 0}}
            
            # Notify Home Assistant of the state change
            self.async_write_ha_state()
            
            # Wait a moment for the device to process
            await asyncio.sleep(2)
            
            # Request a refresh from the coordinator
            await self.coordinator.async_request_refresh()

    async def async_update(self):
        """Manually force a state update from the API when Home Assistant requests it."""
        new_state = await self._client.get_latest_device_data(self._device_id)

        if new_state and "attr" in new_state:
            self.coordinator.data = new_state
        else:
            _LOGGER.warning("⚠️ No 'attr' field found in API response.")