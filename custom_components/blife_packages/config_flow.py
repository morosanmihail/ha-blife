"""Config flow for BLife Packages integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import AUTH_BASE_URL, AUTH_LOGIN_PATH, CONF_API_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate credentials and return token + api_url."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-spike-origin": "mobile",
    }

    login_data = {
        "email": data[CONF_USERNAME],
        "password": data[CONF_PASSWORD],
    }

    login_url = f"{AUTH_BASE_URL}{AUTH_LOGIN_PATH}"
    try:
        async with aiohttp.ClientSession() as session:
            _LOGGER.info("Authenticating against %s", login_url)
            async with session.post(
                login_url,
                headers=headers,
                json=login_data,
            ) as response:
                _LOGGER.info("Authentication call to %s responded with status %d", login_url, response.status)
                if response.status == 401:
                    raise InvalidAuth

                if response.status != 200:
                    _LOGGER.error("Login failed with status %d", response.status)
                    raise CannotConnect

                body = await response.json(content_type=None)

                if isinstance(body, dict) and not body.get("success", True):
                    errors = body.get("errors") or []
                    error_msg = errors[0] if errors else "Login rejected by server"
                    _LOGGER.error("Login failed: %s", error_msg)
                    raise InvalidAuth

                # Response: {"value": {"token": "...", "type": "Bearer"}}
                token = None
                token_type = "Bearer"
                firstname = ""

                if isinstance(body, dict):
                    value = body.get("value") or {}
                    if isinstance(value, dict):
                        token = value.get("token")
                        token_type = value.get("type") or "Bearer"

                if not token:
                    _LOGGER.warning("No token in login response. Keys: %s", list(body.keys()) if isinstance(body, dict) else type(body))
                    raise CannotConnect

                firstname = data[CONF_USERNAME].split("@")[0].split(".")[0].capitalize()
                _LOGGER.info("Authentication succeeded, token type %s", token_type)

                return {
                    "title": f"BLife - {firstname}",
                    "firstname": firstname,
                    "token": token,
                    "token_type": token_type,
                    CONF_API_URL: None,
                }
    except aiohttp.ClientError as err:
        _LOGGER.error("Connection error during login: %s", err)
        raise CannotConnect from err


class BLifePackagesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BLife Packages."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                entry_data = {
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    "firstname": info["firstname"],
                    "token": info["token"],
                    "token_type": info["token_type"],
                    CONF_API_URL: info[CONF_API_URL],
                }
                return self.async_create_entry(title=info["title"], data=entry_data)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthorization request."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauthorization confirmation."""
        errors: dict[str, str] = {}

        if user_input is not None:
            reauth_entry = self._get_reauth_entry()
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={
                        **reauth_entry.data,
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        "firstname": info["firstname"],
                        "token": info["token"],
                        "token_type": info["token_type"],
                        CONF_API_URL: info[CONF_API_URL],
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )
