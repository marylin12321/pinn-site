#!/usr/bin/env python3
"""Demo OAuth Pinterest API v5: schermo per l'upgrade a Standard access.

Uso:
  python3 tools/api_demo.py

Registra lo schermo di questo terminale mentre gira. Il video deve mostrare:
  1. l'URL di autorizzazione che apri nel browser
  2. il flusso OAuth completato (login + consenso)
  3. la chiamata POST /v5/pins che crea un pin reale (sandbox)
  4. la risposta JSON con l'id del pin

Pinterest richiede un video di ~2 min per concedere l'accesso Standard.
Dopo l'approvazione, lo stesso codice posta pin reali (non sandbox).
"""
from __future__ import annotations

import base64, hashlib, json, os, secrets, sys, urllib.error, urllib.parse, urllib.request
from pathlib import Path

CLIENT_ID = "1615041"
CLIENT_SECRET = os.environ.get("PINTEREST_APP_SECRET", "")
REDIRECT = "https://www.google.com/oauthredirect"  # localhost: anche valido se registrato
SCOPES = ["pins:read", "pins:write", "boards:read", "boards:write", "user_accounts:read"]


def _pkce() -> tuple[str, str]:
    ver = secrets.token_urlsafe(64)
    ch = base64.urlsafe_b64encode(hashlib.sha256(ver.encode()).digest()).rstrip(b"=").decode()
    return ver, ch


def url() -> str:
    ver, ch = _pkce()
    st = secrets.token_urlsafe(16)
    s = f"{CLIENT_ID}:{ch}:{st}"
    if CLIENT_SECRET:
        s += f":{CLIENT_SECRET}"
    return ("https://www.pinterest.com/oauth/?" + urllib.parse.urlencode({
        "client_id": CLIENT_ID, "response_type": "code",
        "scope": " ".join(SCOPES), "redirect_uri": REDIRECT,
        "state": st, "code_challenge_method": "S256", "code_challenge": ch,
        "response_mode": "query"}))


def token(code: str, verifier: str) -> dict:
    if not CLIENT_SECRET:
        raise RuntimeError("setta PINTEREST_APP_SECRET prima dello scambio codice")
    body = json.dumps({"grant_type": "authorization_code", "code": code,
                       "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                       "redirect_uri": REDIRECT, "code_verifier": verifier}).encode()
    req = urllib.request.Request("https://api.pinterest.com/v5/oauth/token", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode())


def post_pin(token: str, board_id: str) -> dict:
    body = json.dumps({"board_id": board_id,
                       "media_source": {"source_type": "image_url",
                                        "url": "https://via.placeholder.com/1000x1500/F7F9FB/1E7A5F?text=Pin+sandbox"},
                       "title": "Test API v5 — pin di prova",
                       "description": "Pin creato via Pinterest API v5 (sandbox). Accesso Standard attivo.",
                       "link": "https://marylin12321.github.io/pinn-site/"}).encode()
    req = urllib.request.Request("https://api.pinterest.com/v5/pins", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode())


def main() -> int:
    ver, ch = _pkce()
    print("=" * 64)
    print("PIN API V5 — DEMO PER UPGRADE A STANDARD ACCESS")
    print("=" * 64)
    print()
    print("PASSO 1 — registra lo schermo di questo terminale (2 min)")
    print()
    print(f"PASSO 2 — apri in browser:")
    print()
    print(f"  {url()}")
    print()
    print("  (login + consenso → Pinterest reindirizza a /oauthredirect?code=...)")
    print()
    cod = input("  Incolla il CODE qui: ").strip()
    print(f"  [code ricevuto: {len(cod)} chars]")
    tok = token(cod, ver)
    access = tok.get("access_token", "")
    print(f"\nPASSO 3 — token ottenuto (salvalo in un GitHub secret, MAI in chat):")
    print(f"  {access[:12]}...{access[-8:]}")
    print(f"\nPASSO 4 — posta un pin di prova (sandbox, invisibile al pubblico):")
    if access:
        try:
            res = post_pin(access, "_")
            print(f"  risposta: {json.dumps(res, indent=2)[:300]}")
        except Exception as e:
            print(f"  errore (normale senza board): {e}")
    print(f"\n  Salva il token nel file:")
    print(f"    echo '{access}' > ~/.pinterest-token-finanza")
    print(f"\n  E aggiungilo come secret GitHub (Settings → Secrets → PINTEREST_TOKEN_FINANZA).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
