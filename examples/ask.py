"""Ask the knowledge base a question and hear the answer.

    python examples/ask.py "كم المدة اللي أقدر أرجع فيها قطعة غيار؟"

With no argument it runs a few questions in Arabic and English. Add --no-audio
to skip synthesis entirely — retrieval and generation still run, which is the
fastest way to check whether your documents are answering the question before
you spend anything on speech.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

import agent  # noqa: E402
import rag  # noqa: E402
from voho_ws import VohoError  # noqa: E402

OUT = Path("out")

QUESTIONS = [
    "كم المدة اللي أقدر أرجع فيها قطعة غيار بعد الشراء؟",
    "القطع الكهربائية المفتوحة كم مدتها؟",
    "متى يفتح فرع الرياض يوم الجمعة؟",
]


async def ask(question: str, index: rag.Index, *, speak: bool, n: int) -> None:
    print(f"\n\033[2m─────\033[0m {question}")

    try:
        result = await agent.answer(question, index=index, speak=speak)
    except VohoError as exc:
        print(f"  \033[33mno audio:\033[0m {exc}")
        result = await agent.answer(question, index=index, speak=False)

    print(f"\n  {result.text.strip()}\n")
    for cite in result.citations:
        print(f"  \033[2m· {cite}\033[0m")

    if result.first_audio_ms is not None:
        print(f"\n  \033[32mfirst audio at {result.first_audio_ms:.0f} ms\033[0m")
    if result.audio:
        OUT.mkdir(exist_ok=True)
        path = OUT / f"answer-{n:02d}.opus"
        path.write_bytes(result.audio)
        print(f"  \033[2m{path} · {len(result.audio) // 1024} KB\033[0m")


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    speak = "--no-audio" not in sys.argv

    index = rag.load()
    print(f"\033[2m  {len(index.passages)} passages indexed from {rag.KNOWLEDGE_DIR}/\033[0m")

    for n, question in enumerate(args or QUESTIONS, start=1):
        await ask(question, index, speak=speak, n=n)
    print()


if __name__ == "__main__":
    asyncio.run(main())
