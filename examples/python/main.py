"""Talk to a Saudi Arabic phone agent and hear it answer.

Standard library only — Python 3.9 or newer.

    export VOHO_API_KEY=voho_sk_live_...   # app.voho.ai -> API Tokens
    python examples/python/main.py

New accounts start with $25 of credit, so this costs nothing to try.
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

KEY = os.environ.get("VOHO_API_KEY")
BASE = os.environ.get("VOHO_BASE_URL", "https://app.voho.ai")

if not KEY:
    sys.exit("Set VOHO_API_KEY first — create one at https://app.voho.ai/tokens")


def voho(path, body, raw=False):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as res:
            return res.read() if raw else json.load(res)
    except urllib.error.HTTPError as err:
        detail = json.loads(err.read() or b"{}").get("error", {})
        sys.exit("%s: %s" % (detail.get("code", err.code), detail.get("message", "request failed")))


def spent(cents):
    print("\nCharged $%.2f from your Voho balance." % (cents / 100))

said = " ".join(sys.argv[1:]) or "وش سياسة الاسترجاع عندكم؟"
agent_id = os.environ.get("VOHO_AGENT_ID")

if not agent_id:
    # No agent configured yet: speak the line so you hear the voice, and say
    # where to make an agent that can answer back.
    print("VOHO_AGENT_ID is not set — speaking a line instead.\n")
    audio = voho("/v1/speech", {"text": "أهلاً بك، معك ليلى. كيف أقدر أساعدك؟", "voice": "layla", "model": "sada-1", "format": "mp3"}, raw=True)
    with open("voho.mp3", "wb") as fh:
        fh.write(audio)
    print("Wrote voho.mp3 — play it.")
    print("\nTo have a conversation: create an agent at https://app.voho.ai/agents,")
    print("copy its id from the URL, then: export VOHO_AGENT_ID=...")
    sys.exit(0)

print("Caller:", said)
out = voho("/v1/agents/%s/reply" % agent_id, {
    "text": said,
    "variables": {"company": os.environ.get("VOHO_COMPANY", "شركتنا")},
})

print("Agent :", out["reply"])
if out.get("audio"):
    with open("reply.mp3", "wb") as fh:
        fh.write(base64.b64decode(out["audio"]))
    print("\nWrote reply.mp3 — that is what the caller would hear.")
spent(out["cost_cents"])
