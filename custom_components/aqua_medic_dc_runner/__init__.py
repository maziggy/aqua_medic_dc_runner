import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .client import AquaMedicClient
from .const import DOMAIN, DEFAULT_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    _LOGGER.info("🔧 Setting up Aqua Medic integration...")

    # Check if we have new token-based configuration or old username/password
    if "token" in entry.data:
        # New token-based setup
        app_id = entry.data["app_id"]
        token = entry.data["token"]
        device_id = entry.data["device_id"]
        
        client = AquaMedicClient(None, None, app_id)
        client.token = token
        
        # Test the connection
        test_data = await client.get_latest_device_data(device_id)
        if not test_data:
            _LOGGER.error("❌ Failed to connect with provided token.")
            return False
    else:
        # Legacy username/password setup
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

        device_id = devices[0]["did"]
    
    # Create standard coordinator
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="aqua_medic_shared_coordinator",
        update_method=lambda: client.get_latest_device_data(device_id),
        update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
    )
    
    await coordinator.async_config_entry_first_refresh()
    
    # Start listening for updates
    coordinator.async_add_listener(lambda: None)
    
    # Store both client and coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator
    }

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
    data = hass.data[DOMAIN].get(entry.entry_id)
    if data and "client" in data:
        await data["client"].close()
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["number", "switch"])
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok