"""The agent: retrieve, generate, speak — overlapping, not in sequence.

The naive shape is retrieve → generate the whole answer → synthesise it →
play it. Every stage waits for the one before, and the caller hears silence
for the sum of all four.

What happens here instead: retrieval runs on the question, generation starts,
and each token is pushed into an open Voho WebSocket as it arrives. Audio
comes back while the sentence is still being written. The number to watch is
`first_audio_ms` — the gap the caller actually experiences.

The language model is optional. With no key configured, `answer()` composes
the reply straight from the retrieved passages, which is enough to hear the
pipeline work and to test the citation behaviour.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import AsyncIterator

import rag
import tools
from voho_ws import SpeechSession

MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_KEY = os.getenv("OPENAI_API_KEY")
LLM_BASE = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")

SYSTEM = """أنت موظف خدمة عملاء سعودي. تتكلم باللهجة النجدية بأسلوب مختصر ومهذب.

قواعد:
- جاوب من المقاطع المرفقة فقط. إذا ما كان الجواب فيها، قل إنك ما تعرف واعرض التحويل لموظف.
- لا تخترع أرقام أو تواريخ. إذا احتاج السؤال بيانات العميل نفسه، استخدم الأدوات المتاحة.
- جمل قصيرة. المتصل يسمعك ولا يقرأك."""


@dataclass
class Answer:
    text: str
    citations: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    first_audio_ms: float | None = None
    audio: bytes = b""


async def _llm_tokens(question: str, hits: list[rag.Hit]) -> AsyncIterator[str]:
    """Stream tokens out of the model, running any tool call it asks for."""
    import httpx

    context = "\n\n".join(
        f"[{h.cite()}]\n{h.passage.text}" for h in hits
    )
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"المقاطع:\n{context}\n\nالسؤال: {question}"},
    ]

    async with httpx.AsyncClient(timeout=60) as client:
        for _ in range(2):  # one round of tool calls, then the final answer
            pending: dict[int, dict] = {}
            said_anything = False

            async with client.stream(
                "POST",
                f"{LLM_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {LLM_KEY}"},
                json={
                    "model": MODEL,
                    "messages": messages,
                    "tools": tools.SCHEMA,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    body = line[6:]
                    if body == "[DONE]":
                        break
                    delta = json.loads(body)["choices"][0].get("delta", {})

                    if content := delta.get("content"):
                        said_anything = True
                        yield content

                    for tc in delta.get("tool_calls", []) or []:
                        slot = pending.setdefault(
                            tc["index"], {"id": "", "name": "", "arguments": ""}
                        )
                        slot["id"] += tc.get("id") or ""
                        fn = tc.get("function", {})
                        slot["name"] += fn.get("name") or ""
                        slot["arguments"] += fn.get("arguments") or ""

            if not pending:
                return

            # Run what it asked for, feed the results back, let it finish.
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": c["id"],
                            "type": "function",
                            "function": {"name": c["name"], "arguments": c["arguments"]},
                        }
                        for c in pending.values()
                    ],
                }
            )
            for call in pending.values():
                result = tools.call(call["name"], call["arguments"])
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
            if said_anything:
                yield " "


async def _passage_tokens(hits: list[rag.Hit]) -> AsyncIterator[str]:
    """No model configured: read the best passage back, a word at a time.

    Not an answer so much as a quotation, but it exercises every part of the
    pipeline — which is what you want before you have wired a model up.
    """
    if not hits:
        yield "ما لقيت جواب لهذا السؤال في المستندات."
        return
    for word in hits[0].passage.text.split():
        yield word + " "
        await asyncio.sleep(0)  # let the socket drain between tokens


async def answer(
    question: str,
    *,
    index: rag.Index | None = None,
    voice: str | None = None,
    speak: bool = True,
) -> Answer:
    """Answer one question, streaming the audio as it is produced."""
    hits = rag.search(question, index=index)
    result = Answer(text="", citations=[h.cite() for h in hits])

    tokens = _llm_tokens(question, hits) if LLM_KEY else _passage_tokens(hits)

    if not speak:
        async for token in tokens:
            result.text += token
        return result

    kwargs = {"voice": voice} if voice else {}
    async with SpeechSession(**kwargs) as speech:

        async def pump() -> None:
            async for token in tokens:
                result.text += token
                await speech.send(token)
            await speech.finish()

        pumping = asyncio.create_task(pump())
        chunks: list[bytes] = []
        async for chunk in speech.audio():
            chunks.append(chunk)
        await pumping

        result.audio = b"".join(chunks)
        result.first_audio_ms = speech.first_audio_ms

    return result
