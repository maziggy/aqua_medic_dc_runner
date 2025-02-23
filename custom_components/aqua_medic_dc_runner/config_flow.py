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
            username = user_input["username"]
            password = user_input["password"]
            app_id = DEFAULT_APP_ID  # ✅ Ensuring app_id is passed correctly

            client = AquaMedicClient(username, password, app_id)  # ✅ Fix: Include app_id

            success = await client.authenticate()  # ✅ Using authenticate() instead of login()
            if success:
                return self.async_create_entry(
                    title="Aqua Medic DC Runner",
                    data={
                        "username": username,
                        "password": password,
                        "app_id": client.app_id,
                        "token": client.token,
                        "uid": client.uid
                    },
                )
            else:
                errors["base"] = "auth_failed"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("username"): str,
                vol.Required("password"): str,
            }),
            errors=errors,
        )
