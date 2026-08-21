# Real-Time Arabic Voice Agent — Najdi

> Answers a caller from your own documents, and starts speaking before it has finished writing the sentence.

Built for Saudi Arabia. The agent answers in **Najdi Arabic** — the dialect of
Riyadh and central Saudi Arabia — from a knowledge base you control, and cites
the document and section every answer came from.

<p align="center">
  <a href="https://voho.ai/demos/realtime-arabic-rag">
    <img src="docs/demo.png" alt="A question asked in Arabic, answered from three retrieved policy documents with the top source quoted, a tool call resolving the caller's own invoice dates, and first audio at 310 ms" width="900">
  </a>
</p>

<p align="center">
  <b><a href="https://voho.ai/demos/realtime-arabic-rag">▶ Play the live demo</a></b> — runs in your browser, no sign-up.
</p>

---

## The point

The naive shape is: retrieve → write the whole answer → synthesise it → play
it. Every stage waits for the one before it, and the caller hears silence for
the sum of all four.

This does it differently. Retrieval runs on the question, the model starts
writing, and each token goes into an **open Voho WebSocket** as it arrives.
Audio comes back while the sentence is still being written. The number that
matters is `first_audio_ms` — the gap the caller actually experiences, printed
on every run.

## What speaks, and what listens

Voho is a speech **synthesis** API. It speaks; it does not transcribe. So the
listening end is yours to choose — this repository starts from text, and any
recogniser that hands you a string will drop straight in.

| Part | What does it | Where |
| --- | --- | --- |
| Speaking | **Voho** over `wss://app.voho.ai/v1/speech/ws`, pipelined | [`voho_ws.py`](voho_ws.py) |
| Retrieval | BM25 over your `.md` files — no vector database, no model download | [`rag.py`](rag.py) |
| Tools | Lookups the model calls mid-sentence | [`tools.py`](tools.py) |
| The answer | Any OpenAI-compatible endpoint, or none at all | [`agent.py`](agent.py) |

## Quick start

You need a Voho API key. Create one at [app.voho.ai](https://app.voho.ai) under
**API Tokens**.

```bash
git clone https://github.com/yar-malik/realtime-arabic-voice-agent-najdi.git
cd realtime-arabic-voice-agent-najdi
pip install -r requirements.txt
cp .env.example .env      # then paste your key into .env
python examples/ask.py
```

```
  12 passages indexed from knowledge/

───── كم المدة اللي أقدر أرجع فيها قطعة غيار بعد الشراء؟

  يمكن استرجاع قطع الغيار خلال ثلاثين يوماً من تاريخ الشراء…

  · returns and warranty policy, §2 مدة الاسترجاع
  · returns and warranty policy, §4 العيوب المصنعية

  first audio at 310 ms
  out/answer-01.opus · 46 KB
```

Ask your own:

```bash
python examples/ask.py "متى يفتح فرع الرياض يوم الجمعة؟"
```

Add `--no-audio` to run retrieval and generation without spending anything on
speech — the fastest way to check whether your documents actually answer the
question.

## Your own documents

Drop `.md` files into `knowledge/`. They are split on `##` headings, and the
heading becomes the citation, so an answer points at somewhere a person can
actually turn to rather than at a chunk number.

No vector database, no embedding model, no cold start. For a few thousand
passages BM25 retrieves about as well and begins instantly, which matters when
the alternative is loading a model in front of a live caller.

**Arabic needs three things that English does not**, all in `rag.py`:

- **Normalisation** — أ إ آ all become ا, ة becomes ه, tashkeel is stripped.
- **Affixes** — the definite article and common suffixes come off both sides, so الفاتورة and فاتورة are one word.
- **Broken plurals** — Arabic does not pluralise by adding a letter: فرع becomes فروع, changing inside the word. Dropping the internal weak letters approximates the root. Without this, a question about branch opening hours retrieves the escalation procedure, because both mention الفرع.

It is not a morphological analyser. It is the cheap 90%, and it is short enough
to read in one sitting.

## Tools

Retrieval answers *what is the policy*. It cannot answer *how long do I have
left* — that needs the caller's own invoice. [`tools.py`](tools.py) holds a
small registry the model calls mid-sentence:

```python
lookup_purchase(invoice="INV-77120")
  → bought      2026-08-02
  → window ends 2026-09-01
  → 11 days left
```

Keep the set small and the descriptions blunt. A tool the model half
understands is worse than one it does not have.

## The WebSocket protocol

Three frames out, three in:

```python
async with SpeechSession(voice="layla") as speech:
    async for token in llm_tokens():
        await speech.send(token)      # {"type": "text",  "text": "…"}
    await speech.finish()             # {"type": "flush"}
    async for chunk in speech.audio():
        play(chunk)                   # binary frames, in arrival order
```

Audio begins before you have finished sending text. It is genuinely pipelined,
not batched at the end.

## Running inside your own network

Saudi enterprises frequently require that documents and call audio do not leave
the building. Point `VOHO_WS_URL` at your own deployment and `LLM_BASE_URL` at
a self-hosted model — the knowledge base is already local, and nothing else in
the code changes.

## Security

- No key is committed. `.env` is git-ignored; `.env.example` holds placeholders only.
- Rotate keys from the dashboard, and scope one key per environment.

## More Voho examples

| Repository | What it covers | Live demo |
| --- | --- | --- |
| [realtime-arabic-voice-agent-najdi](https://github.com/yar-malik/realtime-arabic-voice-agent-najdi) | Streaming answers from your own documents | [Play it](https://voho.ai/demos/realtime-arabic-rag) |
| [ai-voice-agent-saudi-najdi](https://github.com/yar-malik/ai-voice-agent-saudi-najdi) | Booking appointments by phone | [Play it](https://voho.ai/demos/appointment-booking) |
| [charco-voice-agent-najdi](https://github.com/yar-malik/charco-voice-agent-najdi) | Taking restaurant orders by phone | [Play it](https://voho.ai/demos/restaurant-ordering) |
| [arabic-engineering-ai-copilot](https://github.com/yar-malik/arabic-engineering-ai-copilot) | Asking engineering archives | [Play it](https://voho.ai/demos/industrial-copilot) |
| [saudi-arabic-voice-agent](https://github.com/yar-malik/saudi-arabic-voice-agent) | Phone agents in Najdi Arabic | [Play it](https://voho.ai/demos/contact-center-ai) |

## Want this in production?

We build the first workflow with you, on your own systems — usually live
within a month.

**[Book a call →](https://voho.ai/book-demo)**

---

MIT licensed. Built by [Voho](https://voho.ai) — enterprise AI for Saudi Arabia.
