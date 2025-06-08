import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN, DEFAULT_APP_ID
from .client import AquaMedicClient

_LOGGER = logging.getLogger(__name__)

class AquaMedicConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Aqua Medic DC Runner integration."""

    async def async_step_user(self, user_input=None):
        """Handles the initial configuration step."""
        errors = {}

        if user_input is not None:
            token = user_input["token"]
            device_id = user_input["device_id"]
            app_id = DEFAULT_APP_ID

            # Create client with token directly
            client = AquaMedicClient(None, None, app_id)
            client.token = token

            # Test the connection by fetching device data
            try:
                device_data = await client.get_latest_device_data(device_id)
                if device_data:
                    return self.async_create_entry(
                        title="Aqua Medic DC Runner",
                        data={
                            "app_id": app_id,
                            "token": token,
                            "device_id": device_id
                        },
                    )
                else:
                    errors["base"] = "connection_failed"
            except Exception as e:
                _LOGGER.error(f"Connection test failed: {e}")
                errors["base"] = "connection_failed"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("token", description="User Token from extraction script"): str,
                vol.Required("device_id", description="Device ID from extraction script"): str,
            }),
            errors=errors,
        )
