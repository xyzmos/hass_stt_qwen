"""WebSocket client for Qwen3 ASR."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterable
import json
import logging
import time
from typing import Final

from aiohttp import ClientError, WSCloseCode, WSMsgType

from homeassistant.components.stt import SpeechMetadata, SpeechResult, SpeechResultState

_LOGGER = logging.getLogger(__name__)

# Maximum time to wait for a response (in seconds)
WEBSOCKET_TIMEOUT: Final = 30


class Qwen3AsrClientError(Exception):
    pass


class Qwen3AsrClientTimeout(Qwen3AsrClientError):
    pass


class Qwen3AsrClient:
    """WebSocket client for Qwen3 ASR API."""

    def __init__(
        self,
        client,
        api_key: str,
        api_url: str,
        model: str,
    ) -> None:
        """Initialize the WebSocket client."""
        self.client = client
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.start_time = 0.0
        self.ws = None
        self.timeout = WEBSOCKET_TIMEOUT
        self.enable_server_vad = False
        self.vad_threshold = 0.0
        self.vad_silence_duration_ms = 400

    def _new_event_id(self) -> str:
        return f"event_{int(time.time() * 1000)}"

    def _normalize_language(self, language: str | None) -> str:
        if not language:
            return "zh"
        lower = language.lower()
        if lower.startswith("zh"):
            return "zh"
        return lower

    async def _iter_pcm16(self, stream: AsyncIterable[bytes]) -> AsyncIterable[bytes]:
        buf = bytearray()
        state = "probe"
        pos = 0
        data_remaining: int | None = None

        async for chunk in stream:
            if state == "raw":
                if chunk:
                    yield chunk
                continue

            if chunk:
                buf.extend(chunk)

            if state == "probe":
                if len(buf) < 12:
                    continue
                if buf[:4] != b"RIFF" or buf[8:12] != b"WAVE":
                    yield bytes(buf)
                    buf.clear()
                    state = "raw"
                    continue
                state = "wav_chunks"
                pos = 12

            if state == "wav_chunks":
                while True:
                    if len(buf) < pos + 8:
                        break
                    chunk_id = bytes(buf[pos : pos + 4])
                    chunk_size = int.from_bytes(buf[pos + 4 : pos + 8], "little")
                    end = pos + 8 + chunk_size + (chunk_size % 2)
                    if len(buf) < end:
                        break
                    if chunk_id == b"data":
                        del buf[: pos + 8]
                        data_remaining = chunk_size
                        state = "wav_data"
                        break
                    pos = end
                    if pos > 65536:
                        yield bytes(buf)
                        buf.clear()
                        state = "raw"
                        break

            if state == "wav_data" and data_remaining is not None:
                while buf and data_remaining > 0:
                    take = min(len(buf), data_remaining)
                    yield bytes(buf[:take])
                    del buf[:take]
                    data_remaining -= take
                if data_remaining == 0:
                    if buf:
                        yield bytes(buf)
                        buf.clear()
                    state = "raw"

    async def _send_audio_stream(self, stream: AsyncIterable[bytes]) -> None:
        """Send audio chunks to WebSocket server."""
        try:
            chunk_count = 0
            async for chunk in self._iter_pcm16(stream):
                if not chunk or self.ws.closed:
                    _LOGGER.debug("Stopping audio send: empty chunk or closed connection")
                    break
                # Audio data must be base64 encoded
                b64 = base64.b64encode(chunk).decode("utf-8")
                await self.ws.send_json(
                    {
                        "event_id": self._new_event_id(),
                        "type": "input_audio_buffer.append",
                        "audio": b64,
                    }
                )
                chunk_count += 1
                _LOGGER.debug("Audio chunk #%d sent (%d bytes)", chunk_count, len(chunk))

            if not self.ws.closed:
                # Signal the end of the audio stream to the server
                _LOGGER.info("Sent %d audio chunks, sending finish", chunk_count)
                if not self.enable_server_vad:
                    await self.ws.send_json(
                        {
                            "event_id": self._new_event_id(),
                            "type": "input_audio_buffer.commit",
                        }
                    )
                await self.ws.send_json(
                    {
                        "event_id": self._new_event_id(),
                        "type": "session.finish",
                    }
                )

                # Set start time after sending all audio data
                self.start_time = time.perf_counter()

        except asyncio.CancelledError:
            _LOGGER.debug("send_audio() was cancelled")
            raise
        except Exception:
            _LOGGER.exception("Error sending audio")
            if not self.ws.closed:
                await self.ws.close(
                    code=WSCloseCode.INTERNAL_ERROR,
                    message=b"Error sending audio",
                )
            raise

    async def _receive_transcription(self, send_task: asyncio.Task) -> str:
        """Receive transcription results from WebSocket server."""
        final_text: str | None = None
        try:
            async with asyncio.timeout(self.timeout):
                async for msg in self.ws:
                    if msg.type == WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        msg_type = data.get("type")
                        _LOGGER.debug("Received message type: %s", msg_type)

                        if msg_type == "session.created":
                            _LOGGER.info("Session created: %s", data.get("session", {}).get("id"))
                        elif msg_type == "session.updated":
                            _LOGGER.info("Session updated")
                        elif msg_type == "conversation.item.input_audio_transcription.text":
                            text = data.get("text") or data.get("stash") or ""
                            if text:
                                _LOGGER.debug('Intermediate transcription: "%s"', text)
                        elif msg_type == "conversation.item.input_audio_transcription.completed":
                            # Get final transcription
                            final_text = (data.get("transcript") or data.get("text") or "").strip()
                            if self.start_time > 0:
                                duration = time.perf_counter() - self.start_time
                                _LOGGER.info(
                                    "Transcription processing duration: %.2f seconds",
                                    duration,
                                )
                            _LOGGER.info('Final transcription received: "%s"', final_text)
                            return final_text or ""
                        elif msg_type == "input_audio_buffer.speech_started":
                            _LOGGER.info("Speech started")
                        elif msg_type == "input_audio_buffer.speech_stopped":
                            _LOGGER.info("Speech stopped")
                        elif msg_type == "input_audio_buffer.committed":
                            _LOGGER.info("Audio buffer committed")
                        elif msg_type == "session.finished":
                            final_text = (data.get("transcript") or final_text or "").strip()
                            _LOGGER.info('Session finished: "%s"', final_text)
                            return final_text or ""
                        elif msg_type == "error":
                            error_msg = data.get("error", {})
                            raise Qwen3AsrClientError(str(error_msg))
                        else:
                            _LOGGER.debug("Unhandled message type: %s, data: %s", msg_type, data)
                    elif msg.type == WSMsgType.BINARY:
                        _LOGGER.warning("Received unexpected binary message (%d bytes)", len(msg.data))
                    elif msg.type == WSMsgType.ERROR:
                        raise Qwen3AsrClientError(str(self.ws.exception()))
                    elif msg.type == WSMsgType.CLOSED:
                        _LOGGER.info("WebSocket closed by server")
                        break
                    else:
                        _LOGGER.debug("Received message of type: %s", msg.type)
        except TimeoutError:
            raise Qwen3AsrClientTimeout("Timeout waiting for transcription response")
        except asyncio.CancelledError:
            _LOGGER.debug("receive_transcription() was cancelled")
            raise
        except Qwen3AsrClientError:
            raise
        except Exception as err:
            raise Qwen3AsrClientError(str(err)) from err
        finally:
            if not send_task.done():
                send_task.cancel()

        if final_text is not None:
            return final_text
        raise Qwen3AsrClientError("WebSocket closed before transcription completed")

    def _create_session_config(self, metadata: SpeechMetadata) -> dict:
        """Create configuration for the transcription session."""
        language = self._normalize_language(metadata.language)
        if self.enable_server_vad:
            turn_detection = {
                "type": "server_vad",
                "threshold": self.vad_threshold,
                "silence_duration_ms": self.vad_silence_duration_ms,
            }
        else:
            turn_detection = None
        config = {
            "event_id": self._new_event_id(),
            "type": "session.update",
            "session": {
                "modalities": ["text"],
                "input_audio_format": "pcm",
                "sample_rate": 16000,
                "input_audio_transcription": {
                    "language": language,
                },
                "turn_detection": turn_detection,
            },
        }
        return config

    async def _handle_tasks(
        self, send_task: asyncio.Task, recv_task: asyncio.Task
    ) -> None:
        """Handle task completion and cancellation logic."""
        try:
            done, pending = await asyncio.wait(
                [send_task, recv_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Handle task completion and cancellation
            if recv_task in done:
                _LOGGER.debug("Transcription finished - cancelling audio task")
                if not send_task.done():
                    send_task.cancel()
                await asyncio.gather(send_task, return_exceptions=True)
            elif send_task in done:
                _LOGGER.debug("Audio finished - waiting for final transcription")
                await recv_task
            else:
                _LOGGER.warning(
                    "Unexpected state in task completion, ensuring tasks are awaited/cancelled"
                )
                for task in pending:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

            for task in done:
                if task.exception():
                    _LOGGER.error("Task completed with exception: %s", task.exception())
        finally:
            if not self.ws.closed:
                try:
                    await self.ws.close()
                    _LOGGER.debug("WebSocket closed cleanly")
                except Exception:
                    _LOGGER.exception("Error closing WebSocket connection")

    async def async_process_audio_stream(
        self, metadata: SpeechMetadata, stream: AsyncIterable[bytes]
    ) -> SpeechResult:
        """Process audio stream via WebSocket to Qwen3 ASR Realtime API."""

        # Construct WebSocket URL for realtime API
        uri = f"{self.api_url}/realtime?model={self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        _LOGGER.info(
            "Starting Qwen3 ASR transcription: language=%s, format=%s, sample_rate=%s, channels=%s",
            metadata.language,
            metadata.format,
            metadata.sample_rate,
            metadata.channel,
        )

        try:
            _LOGGER.debug("Opening WebSocket connection to %s", uri)
            async with self.client.ws_connect(uri, headers=headers, heartbeat=30) as ws:
                self.ws = ws
                self.start_time = 0  # Reset start_time

                config = self._create_session_config(metadata)
                _LOGGER.debug("Sending session configuration: %s", config)
                await ws.send_json(config)

                # Create and manage concurrent tasks
                send_task = asyncio.create_task(self._send_audio_stream(stream))
                recv_task = asyncio.create_task(self._receive_transcription(send_task))

                # Handle tasks completion
                await self._handle_tasks(send_task, recv_task)

                # Process final result
                if not recv_task.done() or recv_task.cancelled():
                    return SpeechResult("", SpeechResultState.ERROR)

                exc = recv_task.exception()
                if exc:
                    _LOGGER.error("Transcription failed: %s", exc)
                    return SpeechResult("", SpeechResultState.ERROR)

                final_text = recv_task.result().strip()

                _LOGGER.info('Transcription completed successfully: "%s"', final_text)

                if not final_text:
                    _LOGGER.warning("Qwen3 ASR transcription resulted in empty text")
                    return SpeechResult("", SpeechResultState.SUCCESS)

                return SpeechResult(final_text, SpeechResultState.SUCCESS)

        except ClientError as err:
            _LOGGER.error("WebSocket connection error: %s", err)
            return SpeechResult("", SpeechResultState.ERROR)
        except Exception:
            _LOGGER.exception("Unexpected error in WebSocket communication")
            return SpeechResult("", SpeechResultState.ERROR)
