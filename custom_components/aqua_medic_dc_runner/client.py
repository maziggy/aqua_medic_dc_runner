import json
import logging
import aiohttp
import uuid
from .const import API_BASE_URL

_LOGGER = logging.getLogger(__name__)


class AquaMedicClient:
    def __init__(self, username, password, app_id):
        self.username = username
        self.password = password
        self.app_id = app_id
        self.token = None
        self.uid = None
        self.session = None

    async def ensure_session(self):
        """Ensure session is open before making requests."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """Close the aiohttp session properly."""
        if self.session and not self.session.closed:
            await self.session.close()
            _LOGGER.info("✅ aiohttp ClientSession closed successfully.")

    async def provision(self):
        """Provision device/phone with Gizwits API - required before login."""
        await self.ensure_session()
        
        # Generate a unique phone_id for this Home Assistant instance
        phone_id = str(uuid.uuid4()).upper()
        
        _LOGGER.info(f"🔧 Provisioning device with App ID: {self.app_id}")
        
        url = f"{API_BASE_URL}/app/provision"
        payload = {
            "phone_id": phone_id,
            "os": "Linux",
            "os_ver": "5.4", 
            "sdk_version": "2.23.23.01613",
            "phone_model": "Home Assistant"
        }
        headers = {
            "Content-Type": "application/json",
            "X-Gizwits-Application-Id": self.app_id,
            "User-Agent": "gizwitssuperapprn/154300000 CFNetwork/3826.500.131 Darwin/24.5.0"
        }
        
        async with self.session.post(url, json=payload, headers=headers) as resp:
            raw_text = await resp.text()
            try:
                data = json.loads(raw_text)
                if resp.status == 200:
                    _LOGGER.info(f"✅ Device provisioning successful: {data}")
                    return True
                else:
                    _LOGGER.error(f"❌ Device provisioning failed. Status: {resp.status}, Response: {data}")
                    return False
            except json.JSONDecodeError:
                _LOGGER.error(f"❌ Invalid JSON during provisioning. Response: {raw_text[:500]}")
                return False

    async def authenticate(self):
        """Authenticate with Gizwits API and retrieve user token."""
        await self.ensure_session()  # Ensure session is open before request

        # If we already have a token, skip authentication
        if self.token and self.uid:
            _LOGGER.info("✅ Using existing token, skipping authentication")
            return True

        # Check if we have credentials to authenticate with
        if not self.username or not self.password:
            _LOGGER.error("❌ No username/password provided and no existing token")
            return False

        # First, provision the device if needed
        _LOGGER.info("🔧 Starting authentication process with provision step...")
        provision_success = await self.provision()
        if not provision_success:
            _LOGGER.warning("⚠️ Provisioning failed, but continuing with login attempt...")
        else:
            _LOGGER.info("✅ Provisioning completed successfully")

        _LOGGER.info(f"🔐 Attempting login with username: {self.username} and App ID: {self.app_id}")

        url = f"{API_BASE_URL}/app/login"
        payload = {"username": self.username, "password": self.password}
        headers = {
            "Content-Type": "application/json", 
            "X-Gizwits-Application-Id": self.app_id,
            "User-Agent": "gizwitssuperapprn/154300000 CFNetwork/3826.500.131 Darwin/24.5.0"
        }

        async with self.session.post(url, json=payload, headers=headers) as resp:
            raw_text = await resp.text()
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                _LOGGER.error(f"❌ Invalid JSON during authentication. Response: {raw_text[:500]}")
                return False

            if "token" in data:
                self.token = data["token"]
                self.uid = data["uid"]
                _LOGGER.info(f"✅ Authentication successful! Token: {self.token}, UID: {self.uid}")
                return True
            else:
                _LOGGER.error(f"❌ Authentication failed. Response: {data}")
                return False

    async def get_devices(self):
        """Fetch list of devices associated with the user."""
        await self.ensure_session()  # Ensure session is open before request

        if not self.token:
            _LOGGER.error("❌ Cannot fetch devices: No token. Authentication required.")
            return None

        url = f"http://euapi.gizwits.com/app/bindings?limit=10"
        headers = {
            "X-Gizwits-Application-Id": self.app_id,
            "X-Gizwits-User-token": self.token
        }

        async with self.session.get(url, headers=headers) as resp:
            if resp.status == 200:
                raw_text = await resp.text()
                try:
                    data = json.loads(raw_text)
                    if "devices" in data:
                        _LOGGER.info(f"✅ Successfully retrieved {len(data['devices'])} devices.")
                        return data["devices"]
                    else:
                        _LOGGER.error(f"❌ Unexpected response format! Response: {data}")
                        return None
                except json.JSONDecodeError:
                    _LOGGER.error(f"❌ Invalid JSON in device response. Response: {raw_text[:500]}")
                    return None
            else:
                _LOGGER.error(f"❌ Failed to fetch devices: {await resp.text()}")
                return None

    async def get_latest_device_data(self, device_id):
        """Fetch the latest state of the device."""
        await self.ensure_session()  # ✅ Ensure session is open before request

        url = f"http://euapi.gizwits.com/app/devdata/{device_id}/latest"
        headers = {
            "X-Gizwits-Application-Id": self.app_id,
            "X-Gizwits-User-token": self.token,
        }

        async with self.session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                _LOGGER.debug("📡 Full API Response: %s", data)  # Debug full response
                return data
            else:
                _LOGGER.error("❌ Failed to fetch latest device data: %s", resp.status)
                return None

    async def set_power(self, device_id: str, state: bool):
        """Send power command to the Aqua Medic device."""
        payload = {
            "attrs": {
                "SwitchON": 1 if state else 0
            }
        }

        url = f"http://euapi.gizwits.com/app/control/{device_id}"
        headers = {
            "X-Gizwits-Application-Id": self.app_id,
            "X-Gizwits-User-token": self.token,
            "Content-Type": "application/json"
        }

        async with self.session.post(url, headers=headers, json=payload) as resp:
            if resp.status == 200:
                _LOGGER.info(f"Power state set to {state} for device {device_id}")
                return True
            else:
                _LOGGER.error(f"Failed to set power state: {await resp.text()}")
                return False

    async def set_motor_speed(self, device_id: str, speed: int):
        """Send motor speed command to the Aqua Medic device."""
        payload = {
            "attrs": {
                "Motor_Speed": speed
            }
        }

        url = f"http://euapi.gizwits.com/app/control/{device_id}"
        headers = {
            "X-Gizwits-Application-Id": self.app_id,
            "X-Gizwits-User-token": self.token,
            "Content-Type": "application/json"
        }

        _LOGGER.info(f"Sending speed {speed} to API: {url}")
        _LOGGER.debug(f"Payload: {payload}")
        
        async with self.session.post(url, headers=headers, json=payload) as resp:
            response_text = await resp.text()
            _LOGGER.info(f"API response status: {resp.status}, body: {response_text}")
            
            if resp.status == 200:
                _LOGGER.info(f"Motor speed set to {speed} for device {device_id}")
                return True
            else:
                _LOGGER.error(f"Failed to set motor speed: {response_text}")
                return False

    async def get_power_state(self, device_id):
        """Fetch the current power state from API."""
        url = f"http://euapi.gizwits.com/app/devdata/{device_id}/latest"
        headers = {"X-Gizwits-User-token": self.token, "Content-Type": "application/json"}

        async with self.session.get(url, headers=headers) as resp:
            if resp.status != 200:
                _LOGGER.error("Failed to fetch power state for device %s", device_id)
                return None
            data = await resp.json()
            _LOGGER.debug("Power state response: %s", data)
            return data
