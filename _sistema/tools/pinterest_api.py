#!/usr/bin/env python3
"""Pinterest API v5: pubblica le guide in coda come pin (al posto dell'RSS fermo).

Perché: l'auto-publish da RSS ha creato i primi 15 pin e poi si è fermo. Con
l'API v5 postiamo noi: la coda guide in coda diventa pin reali, con la cover
già online, il link alla guida e la descrizione scritta a mano.

Requisiti (vedi docs/09-api-pinterest.md):
  - app con accesso **Standard** (in Trial i pin sono sandbox: invisibili al pubblico)
  - token OAuth con scope `pins:write` e `boards:read`
  - il token si legge da PINTEREST_TOKEN_<NICCHIA> o da ~/.pinterest-token-<nicchia>

Uso:
  python3 tools/pinterest_api.py --elenca                    # account + board trovate
  python3 tools/pinterest_api.py --coda                      # cosa verrebbe postato
  python3 tools/pinterest_api.py --posta --dry-run           # prova, senza chiamate
  python3 tools/pinterest_api.py --posta --nicchia finanza --max 1
  python3 tools/pinterest_api.py --posta --tutte             # tutti i profili con token

Dopo un post riuscito la guida viene marcata `pubblicato:` → esce da feed e coda.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import pendenze  # noqa: E402

API = "https://api.pinterest.com/v5"
NICCHIE = ["casa", "cibo", "finanza", "parenting"]


def _token(nid: str) -> str:
    for k in (f"PINTEREST_TOKEN_{nid.upper()}", "PINTEREST_TOKEN"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    p = Path.home() / f".pinterest-token-{nid}"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return ""


def _get(path: str, token: str, campi: str = "") -> dict:
    url = f"{API}{path}" + (f"?fields={campi}" if campi else "")
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(path: str, token: str, payload: dict, tentativi: int = 3) -> dict:
    corpo = json.dumps(payload).encode("utf-8")
    for n in range(tentativi):
        req = urllib.request.Request(f"{API}{path}", data=corpo, method="POST", headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json",
            "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            corpo_errore = e.read().decode("utf-8", "ignore")[:300]
            if e.code == 429 and n < tentativi - 1:      # troppe richieste: rallenta
                attesa = 3 * (n + 1)
                print(f"    (429: attendo {attesa}s)")
                time.sleep(attesa)
                continue
            raise RuntimeError(f"HTTP {e.code}: {corpo_errore}") from None
    raise RuntimeError("esauriti i tentativi")


def _account(token: str) -> dict:
    return _get("/user_account", token, "id,username,profile_url")


def _boards(token: str) -> dict[str, str]:
    """{nome board: board_id} dell'account del token."""
    out: dict[str, str] = {}
    pagina = _get("/boards?page_size=25", token, "id,name")
    for b in pagina.get("items", []):
        out[b["name"]] = b["id"]
    return out


def _payload(voce: dict, board_id: str, immagine: str) -> dict:
    return {
        "board_id": board_id,
        "media_source": {"source_type": "image_url", "url": immagine},
        "title": voce["titolo"],
        "description": voce["descrizione"],
        "link": voce["link"],
    }


def _copertina(voce: dict) -> str:
    """Cover della guida se esiste, altrimenti la cover di nicchia."""
    if voce.get("cover_esiste"):
        return voce["immagine"]
    return f"{voce['link'].split('/guide/')[0]}covers/{voce['nicchia']}.jpg"


def _pubblica(nid: str, max_pin: int, dry_run: bool, segna: bool) -> tuple[int, int]:
    token = _token(nid)
    if not token:
        print(f"  {nid}: nessun token (PINTEREST_TOKEN_{nid.upper()} o "
              f"~/.pinterest-token-{nid}) → skip")
        return 0, 0
    try:
        acc = _account(token)
    except Exception as e:  # noqa: BLE001
        print(f"  {nid}: token non valido o permessi insufficienti → {e}")
        return 0, 0
    print(f"  {nid}: account @{acc.get('username', '?')} ({acc.get('id')})")
    try:
        boards = _boards(token)
    except Exception as e:  # noqa: BLE001
        print(f"    board non leggibili: {e}")
        return 0, 0
    print(f"    board trovate: {len(boards)}")

    coda = pendenze.coda(nid)
    if not coda:
        print("    coda vuota: niente da postare")
        return 0, 0
    fatti = saltati = 0
    for voce in coda:
        if fatti >= max_pin:
            print(f"    (tetto --max {max_pin} raggiunto, {len(coda) - fatti} in attesa)")
            break
        board_id = boards.get(voce["board"])
        if not board_id:
            near = [b for b in boards if voce["board"].lower() in b.lower()]
            print(f"    ✗ {voce['slug']}: board «{voce['board']}» non trovata"
                  f"{' (simile: ' + ', '.join(near) + ')' if near else ''}")
            saltati += 1
            continue
        img = _copertina(voce)
        if dry_run:
            print(f"    [dry] {voce['slug']} → board «{voce['board']}»\n"
                  f"          titolo: {voce['titolo']}\n"
                  f"          img:    {img}\n"
                  f"          link:   {voce['link']}")
            fatti += 1
            continue
        try:
            res = _post("/pins", token, _payload(voce, board_id, img))
        except Exception as e:  # noqa: BLE001
            print(f"    ✗ {voce['slug']}: {e}")
            saltati += 1
            continue
        pin_id = res.get("id", "?")
        print(f"    ✓ {voce['slug']} → pin {pin_id} (board «{voce['board']}»)")
        if segna and pendenze.segna_pubblicata(voce["slug"]):
            print(f"      marcata pubblicata: esce da feed e coda")
        fatti += 1
        time.sleep(1.5)  # gentile: 1 pin ogni 1,5s
    return fatti, saltati


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--elenca", action="store_true", help="mostra account e board del token")
    ap.add_argument("--coda", action="store_true", help="mostra la coda guide")
    ap.add_argument("--posta", action="store_true", help="pubblica la coda come pin")
    ap.add_argument("--nicchia", action="append", choices=NICCHIE, help="limita a una nicchia")
    ap.add_argument("--tutte", action="store_true", help="tutti i profili con un token")
    ap.add_argument("--max", type=int, default=1, help="pin per profilo in questo giro")
    ap.add_argument("--dry-run", action="store_true", help="non chiama la API")
    ap.add_argument("--no-segna", action="store_true", help="non marcare le guide pubblicate")
    args = ap.parse_args()

    profili = args.nicchia or (NICCHIE if args.tutte else [])

    if args.coda:
        for v in pendenze.coda():
            print(f"  {v['nicchia']:8s} {v['slug']:10s} → «{v['board']}» | {v['titolo']}")
        print(f"\ntotale in coda: {len(pendenze.coda())}")
        return 0

    if args.elenca or not (args.posta or profili):
        for nid in (profili or NICCHIE):
            token = _token(nid)
            if not token:
                print(f"  {nid}: nessun token")
                continue
            try:
                acc = _account(token)
                print(f"  {nid}: @{acc.get('username')} (id {acc.get('id')})")
                for nome, bid in sorted(_boards(token).items()):
                    print(f"      - {nome} → {bid}")
            except Exception as e:  # noqa: BLE001
                print(f"  {nid}: errore → {e}")
        return 0

    totale = ko = 0
    for nid in profili:
        f, k = _pubblica(nid, args.max, args.dry_run, not args.no_segna)
        totale += f
        ko += k
    print(f"\n{'DRY-RUN: ' if args.dry_run else ''}pin pubblicati: {totale} · errori: {ko}")
    if not args.dry_run and totale:
        print("ricorda di girare la routine (build + push) per allineare feed e guide.")
    return 0 if not ko else 1


if __name__ == "__main__":
    raise SystemExit(main())
