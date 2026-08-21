"""Voho's WebSocket speech endpoint.

`wss://app.voho.ai/v1/speech/ws` exists for one case: text arriving
*incrementally* while audio flows back on the same connection. That is exactly
what a language model emitting tokens into a live call looks like — you start
speaking the first sentence while the model is still writing the second.

The protocol is three frames out and three in:

    →  {"type": "start", "voice": "layla", "model": "sada-1", "format": "opus"}
    →  {"type": "text",  "text": "أهلاً "}      (as many as you like)
    →  {"type": "flush"}
    ←  {"type": "ready"} then {"type": "started"} then binary audio frames

Audio begins before you have finished sending text. It is pipelined, not
batched at the end — which is the whole point.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import AsyncIterator

import websockets

BASE_WS = os.getenv("VOHO_WS_URL", "wss://app.voho.ai/v1/speech/ws")
API_KEY = os.getenv("VOHO_API_KEY", "")
DEFAULT_VOICE = os.getenv("VOHO_VOICE", "layla")
DEFAULT_MODEL = os.getenv("VOHO_MODEL", "sada-1")


class VohoError(RuntimeError):
    pass


MISSING_KEY = """No Voho API key.

  Run:  python setup.py

It walks you through creating one at https://app.voho.ai (API Tokens),
checks it against the live voice catalogue, and writes it to .env."""


def has_key() -> bool:
    return bool(API_KEY) and not API_KEY.startswith("voho_sk_live_xxx")


class SpeechSession:
    """One utterance, streamed.

    Usage:

        async with SpeechSession() as speech:
            async for token in llm_tokens():
                await speech.send(token)
            await speech.finish()
            async for chunk in speech.audio():
                play(chunk)

    `first_audio_ms` is populated as soon as the first binary frame lands. It
    is the number worth watching: everything else about a live agent can be
    fixed later, but a caller hears this one immediately.
    """

    def __init__(
        self,
        *,
        voice: str = DEFAULT_VOICE,
        model: str = DEFAULT_MODEL,
        fmt: str = "opus",
    ) -> None:
        if not has_key():
            raise VohoError(MISSING_KEY)
        self.voice = voice
        self.model = model
        self.fmt = fmt
        self.first_audio_ms: float | None = None
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._started_at: float | None = None

    async def __aenter__(self) -> "SpeechSession":
        self._ws = await websockets.connect(
            BASE_WS, additional_headers={"Authorization": f"Bearer {API_KEY}"}
        )
        await self._expect("ready")
        self._started_at = time.perf_counter()
        await self._ws.send(
            json.dumps(
                {
                    "type": "start",
                    "voice": self.voice,
                    "model": self.model,
                    "format": self.fmt,
                }
            )
        )
        await self._expect("started")
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _expect(self, frame_type: str) -> dict:
        """Read control frames until the expected one arrives."""
        assert self._ws is not None
        while True:
            raw = await self._ws.recv()
            if isinstance(raw, bytes):
                # Audio cannot arrive before `started`; if it does, something
                # is badly out of order and silently dropping it would hide it.
                raise VohoError(f"audio frame arrived while waiting for {frame_type}")
            frame = json.loads(raw)
            if frame.get("type") == "error":
                raise VohoError(frame.get("message", "unknown error"))
            if frame.get("type") == frame_type:
                return frame

    async def send(self, text: str) -> None:
        """Append text to the utterance. Call it per token if you like."""
        assert self._ws is not None
        await self._ws.send(json.dumps({"type": "text", "text": text}))

    async def finish(self) -> None:
        """No more text is coming."""
        assert self._ws is not None
        await self._ws.send(json.dumps({"type": "flush"}))

    async def audio(self) -> AsyncIterator[bytes]:
        """Yield audio frames in arrival order until the utterance ends."""
        assert self._ws is not None
        async for raw in self._ws:
            if isinstance(raw, bytes):
                if self.first_audio_ms is None and self._started_at is not None:
                    self.first_audio_ms = (time.perf_counter() - self._started_at) * 1000
                yield raw
                continue
            frame = json.loads(raw)
            if frame.get("type") in ("done", "finished", "end"):
                return
            if frame.get("type") == "error":
                raise VohoError(frame.get("message", "unknown error"))


async def speak_stream(tokens: AsyncIterator[str], **kw) -> tuple[bytes, float | None]:
    """Drive a whole utterance and collect it. Returns (audio, first_audio_ms).

    Convenience for the non-live case — a test, or writing a file. On a real
    call you want `SpeechSession` directly so you can play frames as they land
    instead of waiting for the last one.
    """
    async with SpeechSession(**kw) as speech:

        async def pump() -> None:
            async for token in tokens:
                await speech.send(token)
            await speech.finish()

        pumping = asyncio.create_task(pump())
        chunks = [chunk async for chunk in speech.audio()]
        await pumping
        return b"".join(chunks), speech.first_audio_ms
