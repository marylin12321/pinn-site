#!/usr/bin/env python3
"""Imposta un secret del repository GitHub via API (Actions secrets).

Uso:
  python3 tools/set_github_secret.py PINTEREST_TOKEN_FINANZA <valore>
  python3 tools/set_github_secret.py PINTEREST_TOKEN_FINANZA       # legge da stdin

Richiede ~/.github-token-pinn (token GitHub con scope repo).
"""
from __future__ import annotations

import base64, os, sys
from pathlib import Path

import nacl.encoding
import nacl.public
import nacl.secret
import nacl.utils
import requests

OWNER, REPO = "marylin12321", "pinn-site"
TOKEN_FILE = Path.home() / ".github-token-pinn"


def _token() -> str:
    return TOKEN_FILE.read_text().strip()


def _pubkey() -> tuple[str, str]:
    r = requests.get(
        f"https://api.github.com/repos/{OWNER}/{REPO}/actions/secrets/public-key",
        headers={"Authorization": f"token {_token()}",
                 "Accept": "application/vnd.github.v3+json"}, timeout=30)
    r.raise_for_status()
    d = r.json()
    return d["key"], d["key_id"]


def _encrypt(value: str, pubkey: str) -> str:
    from nacl.bindings import crypto_box_seal
    pk = nacl.public.PublicKey(pubkey.encode(), encoder=nacl.encoding.Base64Encoder)
    encrypted = crypto_box_seal(value.encode(), bytes(pk))
    return base64.b64encode(encrypted).decode()


def set_secret(name: str, value: str) -> dict:
    pubkey, key_id = _pubkey()
    enc = _encrypt(value, pubkey)
    r = requests.put(
        f"https://api.github.com/repos/{OWNER}/{REPO}/actions/secrets/{name}",
        headers={"Authorization": f"token {_token()}",
                 "Accept": "application/vnd.github.v3+json"},
        json={"encrypted_value": enc, "key_id": key_id}, timeout=30)
    r.raise_for_status()
    return r.json()


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: python3 tools/set_github_secret.py <NOME_SECRET> [valore|stdin]")
        return 1
    name = sys.argv[1]
    if len(sys.argv) >= 3:
        value = sys.argv[2]
    else:
        value = input(f"Inserisci il valore per {name}: ").strip()
    if not value:
        print("valore vuoto"); return 1
    set_secret(name, value)
    print(f"✓ secret {name} impostato su {OWNER}/{REPO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
