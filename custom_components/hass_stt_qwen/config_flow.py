"""Config flow for Qwen ASR Speech-to-Text integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import ClientError, WSMsgType, WSServerHandshakeError
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_API_URL,
    CONF_ENABLE_SERVER_VAD,
    CONF_MODEL,
    CONF_REGION,
    CONF_TIMEOUT,
    CONF_VAD_SILENCE_DURATION_MS,
    CONF_VAD_THRESHOLD,
    DEFAULT_API_URL_BEIJING,
    DEFAULT_API_URL_SINGAPORE,
    DEFAULT_MODEL,
    DEFAULT_REGION,
    DOMAIN,
    SUPPORTED_MODELS,
    SUPPORTED_REGIONS,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_MODEL, default=DEFAULT_MODEL): vol.In(SUPPORTED_MODELS),
        vol.Optional(CONF_REGION, default=DEFAULT_REGION): vol.In(SUPPORTED_REGIONS),
    }
)

STEP_OPTIONS_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_API_URL): str,
        vol.Optional(CONF_ENABLE_SERVER_VAD, default=False): bool,
        vol.Optional(CONF_VAD_THRESHOLD, default=0.0): vol.Coerce(float),
        vol.Optional(CONF_VAD_SILENCE_DURATION_MS, default=400): vol.Coerce(int),
        vol.Optional(CONF_TIMEOUT, default=30): vol.Coerce(int),
    }
)

class QwenSTTConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Qwen ASR Speech-to-Text."""

    VERSION = 1


    async def _async_validate(self, user_input: dict[str, Any]) -> None:
        api_key = user_input[CONF_API_KEY]
        model = user_input.get(CONF_MODEL, DEFAULT_MODEL)
        region = user_input.get(CONF_REGION, DEFAULT_REGION)
        api_url = (
            DEFAULT_API_URL_SINGAPORE if region == "singapore" else DEFAULT_API_URL_BEIJING
        )
        uri = f"{api_url}/realtime?model={model}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        session = async_get_clientsession(self.hass)
        async with session.ws_connect(uri, headers=headers, heartbeat=30) as ws:
            await ws.send_json(
                {
                    "event_id": "event_validate",
                    "type": "session.update",
                    "session": {
                        "modalities": ["text"],
                        "input_audio_format": "pcm",
                        "sample_rate": 16000,
                        "input_audio_transcription": {"language": "zh"},
                        "turn_detection": None,
                    },
                }
            )
            async with asyncio.timeout(5):
                async for msg in ws:
                    if msg.type != WSMsgType.TEXT:
                        continue
                    try:
                        data = msg.json()
                    except Exception:
                        continue
                    msg_type = data.get("type")
                    if msg_type in ("session.created", "session.updated"):
                        return
                    if msg_type == "error":
                        raise ClientError(str(data.get("error", {})))

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors: dict[str, str] = {}

        # Check if already configured
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        try:
            await self._async_validate(user_input)
        except WSServerHandshakeError as err:
            if err.status in (401, 403):
                errors["base"] = "invalid_auth"
            else:
                errors["base"] = "cannot_connect"
        except TimeoutError:
            errors["base"] = "cannot_connect"
        except ClientError:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error validating Qwen ASR configuration")
            errors["base"] = "cannot_connect"

        if errors:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors=errors,
            )

        return self.async_create_entry(title="Qwen ASR", data=user_input)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return QwenSTTOptionsFlow(config_entry)


class QwenSTTOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        super().__init__(config_entry)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(CONF_API_URL, default=opts.get(CONF_API_URL, "")): str,
                vol.Optional(
                    CONF_ENABLE_SERVER_VAD,
                    default=opts.get(CONF_ENABLE_SERVER_VAD, False),
                ): bool,
                vol.Optional(
                    CONF_VAD_THRESHOLD,
                    default=opts.get(CONF_VAD_THRESHOLD, 0.0),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_VAD_SILENCE_DURATION_MS,
                    default=opts.get(CONF_VAD_SILENCE_DURATION_MS, 400),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_TIMEOUT,
                    default=opts.get(CONF_TIMEOUT, 30),
                ): vol.Coerce(int),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
