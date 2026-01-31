"""Setting up QwenSTTProvider."""
from __future__ import annotations

from collections.abc import AsyncIterable
import logging

from homeassistant.components.stt import (
    AudioBitRates,
    AudioChannels,
    AudioCodecs,
    AudioFormats,
    AudioSampleRates,
    SpeechMetadata,
    SpeechResult,
    SpeechResultState,
)
from homeassistant.components.stt import SpeechToTextEntity

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
    SUPPORTED_LANGUAGES,
)
from .qwen3_asr_client import Qwen3AsrClient

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Qwen STT from a config entry."""
    data = config_entry.data
    options = config_entry.options

    api_key = data[CONF_API_KEY]
    model = data.get(CONF_MODEL, DEFAULT_MODEL)
    region = data.get(CONF_REGION, DEFAULT_REGION)

    api_url = options.get(CONF_API_URL) or DEFAULT_API_URL_SINGAPORE if region == "singapore" else DEFAULT_API_URL_BEIJING
    enable_server_vad = options.get(CONF_ENABLE_SERVER_VAD, False)
    vad_threshold = options.get(CONF_VAD_THRESHOLD, 0.0)
    vad_silence_duration_ms = options.get(CONF_VAD_SILENCE_DURATION_MS, 400)
    timeout = options.get(CONF_TIMEOUT, 30)

    async_add_entities(
        [
            QwenSTTEntity(
                hass,
                config_entry,
                api_key,
                api_url,
                model,
                enable_server_vad=enable_server_vad,
                vad_threshold=vad_threshold,
                vad_silence_duration_ms=vad_silence_duration_ms,
                timeout=timeout,
            )
        ]
    )


class QwenSTTEntity(SpeechToTextEntity):
    """The Qwen STT entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api_key: str,
        api_url: str,
        model: str,
        *,
        enable_server_vad: bool,
        vad_threshold: float,
        vad_silence_duration_ms: int,
        timeout: int,
    ) -> None:
        """Init Qwen STT service."""
        self.hass = hass
        self._config_entry = config_entry
        self._api_key = api_key
        self._api_url = api_url
        self._model = model
        self._enable_server_vad = enable_server_vad
        self._vad_threshold = vad_threshold
        self._vad_silence_duration_ms = vad_silence_duration_ms
        self._timeout = timeout
        self._client = self._create_client()
        
        self._attr_name = f"Qwen ASR ({model})"
        self._attr_unique_id = f"{config_entry.entry_id}_{model}"

    @property
    def supported_languages(self) -> list[str]:
        """Return a list of supported languages."""
        return SUPPORTED_LANGUAGES

    @property
    def supported_formats(self) -> list[AudioFormats]:
        """Return a list of supported formats."""
        return [AudioFormats.WAV]

    @property
    def supported_codecs(self) -> list[AudioCodecs]:
        """Return a list of supported codecs."""
        return [AudioCodecs.PCM]

    @property
    def supported_bit_rates(self) -> list[AudioBitRates]:
        """Return a list of supported bitrates."""
        return [AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self) -> list[AudioSampleRates]:
        """Return a list of supported samplerates."""
        return [AudioSampleRates.SAMPLERATE_16000]

    @property
    def supported_channels(self) -> list[AudioChannels]:
        """Return a list of supported channels."""
        return [AudioChannels.CHANNEL_MONO]

    def _create_client(self):
        """Create and return the appropriate client based on model."""
        session = async_get_clientsession(self.hass)

        if self._model.startswith("qwen3-asr"):
            client = Qwen3AsrClient(
                session,
                self._api_key,
                self._api_url,
                self._model,
            )
            client.enable_server_vad = self._enable_server_vad
            client.vad_threshold = self._vad_threshold
            client.vad_silence_duration_ms = self._vad_silence_duration_ms
            client.timeout = self._timeout
            return client
        else:
            _LOGGER.error("Unsupported model: %s", self._model)
            raise ValueError(f"Unsupported model: {self._model}")

    async def async_process_audio_stream(
        self, metadata: SpeechMetadata, stream: AsyncIterable[bytes]
    ) -> SpeechResult:
        """Process audio stream using the configured client."""
        if (
            metadata.format not in self.supported_formats
            or metadata.codec not in self.supported_codecs
            or metadata.bit_rate not in self.supported_bit_rates
            or metadata.sample_rate not in self.supported_sample_rates
            or metadata.channel not in self.supported_channels
        ):
            _LOGGER.error(
                "Unsupported audio metadata: format=%s codec=%s bit_rate=%s sample_rate=%s channel=%s",
                metadata.format,
                metadata.codec,
                metadata.bit_rate,
                metadata.sample_rate,
                metadata.channel,
            )
            return SpeechResult("", state=SpeechResultState.ERROR)
        return await self._client.async_process_audio_stream(metadata, stream)
