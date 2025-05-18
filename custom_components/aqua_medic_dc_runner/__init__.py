import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_state_change
from homeassistant.helpers import entity_registry as er
from .client import AquaMedicClient
from .const import DOMAIN, DEFAULT_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
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

    async def cleanup(event):
        """Cleanup tasks when Home Assistant stops."""
        _LOGGER.info("🛑 Home Assistant is stopping, closing client session...")
        await client.close()

    hass.bus.async_listen_once("homeassistant_stop", cleanup)

    # Ensure all entities register
    await hass.config_entries.async_forward_entry_setups(entry, ["number", "switch"])

    _LOGGER.info("✅ Aqua Medic integration set up successfully!")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.info("🗑️ Unloading Aqua Medic integration...")
    
    # Clean up the client
    client = hass.data[DOMAIN].get(entry.entry_id)
    if client:
        await client.close()
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["number", "switch"])
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok