import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_state_change
from homeassistant.helpers import entity_registry as er
from datetime import timedelta

from .client import AquaMedicClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Aqua Medic integration from a config entry."""
    _LOGGER.info("🔧 Setting up Aqua Medic integration...")

    username = entry.data["username"]
    password = entry.data["password"]
    app_id = entry.data["app_id"]

    client = AquaMedicClient(username, password, app_id)
    success = await client.authenticate()

    if not success:
        _LOGGER.error("❌ Failed to authenticate Aqua Medic API.")
        return False

    devices = await client.get_devices()
    if not devices:
        _LOGGER.error("❌ No devices found. Aborting setup.")
        return False

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client

    # ✅ **Ensure the input_number entity is created automatically**
    update_interval_entity = "input_number.aqua_medic_update_interval"

    # Check if input_number exists in HA before trying to use it
    if hass.states.get(update_interval_entity) is None:
        _LOGGER.warning(
            f"⚠️ {update_interval_entity} not found in Home Assistant states. "
            f"Ensure input_number is properly defined in `configuration.yaml`"
        )
    else:
        # Set default value only if entity exists
        service_data_set = {
            "entity_id": update_interval_entity,
            "value": 30  # Default to 30 seconds
        }

        try:
            await hass.services.async_call(
                "input_number",
                "set_value",
                service_data_set,
                blocking=True,
            )
            _LOGGER.info(f"✅ Successfully set {update_interval_entity} to {service_data_set['value']} seconds")
        except Exception as e:
            _LOGGER.error(f"❌ Failed to set {update_interval_entity}: {e}")

    # ✅ **Ensure the entity exists before tracking changes**
    state = hass.states.get(update_interval_entity)
    if state is None:
        _LOGGER.warning(
            f"⚠️ {update_interval_entity} not found in Home Assistant states."
            f" Ensure input_number integration is loaded."
        )
    else:
        update_interval = int(float(state.state))

        # ✅ Track changes to the input_number
        async def update_interval_listener(entity_id, old_state, new_state):
            """Update polling interval dynamically when input_number changes."""
            if new_state and new_state.state:
                new_interval = int(float(new_state.state))
                _LOGGER.info(f"🔄 Updated polling interval to {new_interval} seconds.")

        async_track_state_change(hass, update_interval_entity, update_interval_listener)

    async def cleanup(event):
        """Cleanup tasks when Home Assistant stops."""
        _LOGGER.info("🛑 Home Assistant is stopping, closing client session...")
        await client.close()

    hass.bus.async_listen_once("homeassistant_stop", cleanup)

    # ✅ Ensure all entities register
    await hass.config_entries.async_forward_entry_setups(entry, ["number", "switch"])

    _LOGGER.info("✅ Aqua Medic integration set up successfully!")
    return True
