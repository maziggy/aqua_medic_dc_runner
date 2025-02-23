import logging
import asyncio
from datetime import timedelta
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Aqua Medic switch entity."""
    client: AquaMedicClient = hass.data[DOMAIN][entry.entry_id]  # Ensure client is correctly retrieved

    devices = await client.get_devices()

    if not devices:
        _LOGGER.error("No devices found in Aqua Medic integration.")
        return

    device_id = devices[0]["did"]  # ✅ Extract device ID

    # Create update coordinator for periodic state refresh
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="aqua_medic_switch_update",
        update_method=lambda: client.get_latest_device_data(device_id),
        update_interval=timedelta(seconds=5),  # 🔹 Reduce polling interval to 5 sec
    )

    await coordinator.async_config_entry_first_refresh()  # Ensure first data load

    async_add_entities([AquaMedicPowerSwitch(client, devices[0]["did"], coordinator, entry)])


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

    @property
    def is_on(self):
        """Return true if switch is on."""
        if not isinstance(self.coordinator.data, dict):  # ✅ Ensure it's a dict
            _LOGGER.error("Unexpected coordinator data type: %s", type(self.coordinator.data))
            return False  # Default to off if data is invalid

        if "attr" not in self.coordinator.data:
            _LOGGER.warning("API response did not contain expected 'attr' field.")
            return False

        device_data = self.coordinator.data["attr"]

        switch_state = device_data.get("SwitchON", device_data.get("PowerState", 0))

        _LOGGER.debug("Device %s state read from API: %s", self._device_id, switch_state)

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
        _LOGGER.info("Turning on device %s", self._device_id)
        await self._client.set_power(self._device_id, True)

        # ✅ **Wait before fetching state**
        await asyncio.sleep(1)

        _LOGGER.info("Fetching latest state after power ON")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off and refresh state."""
        _LOGGER.info("Turning off device %s", self._device_id)
        await self._client.set_power(self._device_id, False)

        # ✅ **Wait before fetching state**
        await asyncio.sleep(1)

        _LOGGER.info("Fetching latest state after power OFF")
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
