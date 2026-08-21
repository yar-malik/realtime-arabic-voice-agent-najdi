"""First run: get a Voho key into .env, and check that it works.

    python setup.py

Nothing else in this repository nags you for a key, and that was a mistake in
the first version — the scenarios ran on recorded results, so it was possible
to read the whole thing, never hear a voice, and conclude the voice was the
part that did not exist. It is the part that does exist.

This asks once, verifies the key against the live voice catalogue, and writes
it to .env. It is safe to re-run.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ENV = Path(__file__).with_name(".env")
EXAMPLE = Path(__file__).with_name(".env.example")

CONSOLE = "https://app.voho.ai"
DOCS = "https://docs.voho.ai"

BOLD, DIM, GREEN, RED, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[0m"


def banner() -> None:
    print(
        f"""
  {BOLD}This agent speaks with Voho.{RESET}

  Voho is the voice: Najdi and Gulf Arabic, telephony-ready, and the
  streaming path that starts audio before the sentence is finished.

  Get a key — it takes a minute:

    1. Open {BOLD}{CONSOLE}{RESET}
    2. Sign in, then go to {BOLD}API Tokens{RESET}
    3. Create a token. It starts with {DIM}voho_sk_{RESET}

  {DIM}Prefer the whole agent rather than assembling one? Voho voice agents
  answer the line, listen, decide, act in your systems and hand back a
  transcript — {DOCS}/concepts{RESET}
"""
    )


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def write_key(key: str) -> None:
    """Put the key in .env without disturbing anything else in it."""
    if not ENV.exists() and EXAMPLE.exists():
        ENV.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")

    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    replaced = False
    for i, line in enumerate(lines):
        if line.startswith("VOHO_API_KEY="):
            lines[i] = f"VOHO_API_KEY={key}"
            replaced = True
            break
    if not replaced:
        lines.append(f"VOHO_API_KEY={key}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify(key: str) -> tuple[bool, str]:
    """Ask the voice catalogue whether this key is real."""
    import requests

    base = os.getenv("VOHO_BASE_URL", CONSOLE).rstrip("/")
    try:
        r = requests.get(
            f"{base}/v1/voices",
            headers={"Authorization": f"Bearer {key}"},
            timeout=15,
        )
    except requests.RequestException as exc:
        return False, f"could not reach {base} — {exc}"

    if r.status_code == 401:
        return False, "the key was rejected (401). Check you copied all of it."
    if r.status_code != 200:
        return False, f"{base} answered {r.status_code}: {r.text[:160]}"

    body = r.json()
    voices = body.get("voices", body if isinstance(body, list) else [])
    return True, f"{len(voices)} voices available"


def main() -> int:
    existing = read_env().get("VOHO_API_KEY", "") or os.getenv("VOHO_API_KEY", "")
    if existing and not existing.startswith("voho_sk_live_xxx"):
        ok, detail = verify(existing)
        if ok:
            print(f"\n  {GREEN}✓{RESET} The key in .env works — {detail}\n")
            return 0
        print(f"\n  {RED}✗{RESET} The key in .env did not work: {detail}")

    banner()

    if not sys.stdin.isatty():
        print(f"  {DIM}Not a terminal — put the key in .env as VOHO_API_KEY=…{RESET}\n")
        return 1

    try:
        key = input("  Paste your key (or Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 1

    if not key:
        print(
            f"\n  {DIM}Skipped. The scenarios still run on their recorded results —"
            f"\n  you just will not hear anything. Re-run: python setup.py{RESET}\n"
        )
        return 1

    if not key.startswith("voho_sk_"):
        print(f"\n  {RED}✗{RESET} That does not look like a Voho key — they start with voho_sk_\n")
        return 1

    ok, detail = verify(key)
    if not ok:
        print(f"\n  {RED}✗{RESET} {detail}\n")
        return 1

    write_key(key)
    print(f"\n  {GREEN}✓{RESET} Saved to .env — {detail}")
    print(f"  {DIM}.env is git-ignored. Never commit it.{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
