"""Constants for the Qwen ASR Speech-to-Text integration."""

DOMAIN = "hass_stt_qwen"

CONF_API_KEY = "api_key"
CONF_API_URL = "api_url"
CONF_MODEL = "model"
CONF_REGION = "region"
CONF_ENABLE_SERVER_VAD = "enable_server_vad"
CONF_VAD_THRESHOLD = "vad_threshold"
CONF_VAD_SILENCE_DURATION_MS = "vad_silence_duration_ms"
CONF_TIMEOUT = "timeout"

DEFAULT_API_URL_BEIJING = "wss://dashscope.aliyuncs.com/api-ws/v1"
DEFAULT_API_URL_SINGAPORE = "wss://dashscope-intl.aliyuncs.com/api-ws/v1"
DEFAULT_MODEL = "qwen3-asr-flash-realtime"
DEFAULT_REGION = "beijing"

SUPPORTED_MODELS = [
    "qwen3-asr-flash-realtime",
    "qwen3-asr-flash-realtime-2025-10-27"
]

SUPPORTED_REGIONS = [
    "beijing",
    "singapore",
]

# Qwen ASR supports multiple languages
SUPPORTED_LANGUAGES = [
    "zh",  # Chinese
    "en",  # English
    "yue",  # Cantonese
    "ja",  # Japanese
    "ko",  # Korean
    "es",  # Spanish
    "fr",  # French
    "de",  # German
    "it",  # Italian
    "pt",  # Portuguese
    "ru",  # Russian
    "ar",  # Arabic
    "tr",  # Turkish
    "vi",  # Vietnamese
    "th",  # Thai
    "id",  # Indonesian
    "ms",  # Malay
]
