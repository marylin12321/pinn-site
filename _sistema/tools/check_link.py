#!/usr/bin/env python3
"""Salute dei link Amazon: un prodotto fuori produzione = commissione persa in silenzio.

Controlla tutti i prodotti dei config e segnala quelli KO (pagina 404, "non
disponibile", nessun "aggiungi al carrello"). Amazon risponde spesso 503 ai
bot: il 503 NON viene contato come KO, altrimenti ogni controllo urlizza.

Uso:
  python3 tools/check_link.py                # tutti i prodotti, tabella + JSON
  python3 tools/check_link.py --nicchia casa # solo una nicchia
  python3 tools/check_link.py --json         # solo il percorso del report
  python3 tools/check_link.py --no-wait      # niente pausa (slower ma ok)

Esito: 0 tutto vivo · 1 almeno un KO · 2 errore di rete/config.
Report: output/link_health.json (per confrontare i giri).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
NICCHIE = ["casa", "cibo", "finanza", "parenting"]
OUT = ROOT / "output" / "link_health.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "it-IT,it;q=0.9",
           "Accept": "text/html,application/xhtml+xml"}


def _prodotti() -> list[tuple[str, str, str]]:
    """(nicchia, id_prodotto, link) dai config."""
    out = []
    for nid in NICCHIE:
        p = ROOT / "config" / "nicchie" / f"{nid}.yaml"
        if not p.exists():
            continue
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for prod in cfg.get("prodotti") or []:
            link = (prod.get("link") or "").strip()
            if "amazon." in link:
                out.append((nid, prod.get("id", "?"), link))
    return out


def _verifica(link: str) -> dict:
    """Stato di un link Amazon. Non distingue 503 (bot) da KO reale."""
    esito: dict = {"http": 0, "stato": "KO", "motivo": "", "prezzo": "", "titolo": ""}
    req = urllib.request.Request(link, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            esito["http"] = r.status
            html = r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        esito["http"] = e.code
        if e.code in (503, 429, 403):
            esito["stato"] = "BOT"
            esito["motivo"] = f"HTTP {e.code} (anti-bot, non è un KO)"
            return esito
        esito["motivo"] = f"HTTP {e.code}"
        return esito
    except Exception as e:  # noqa: BLE001
        esito["motivo"] = f"errore rete: {type(e).__name__}"
        return esito

    if "non disponibile" in html.lower() and "aggiungi al carrello" not in html.lower():
        esito["motivo"] = "prodotto non disponibile"
        return esito
    if "aggiungi al carrello" in html.lower() or "carrello" in html.lower():
        esito["stato"] = "OK"
    m = re.search(r'<span class="a-offscreen">\s*([^<]{2,25})', html)
    if m:
        esito["prezzo"] = m.group(1).strip()
    t = re.search(r'id="productTitle"[^>]*>\s*([^<]{5,120})', html)
    if t:
        esito["titolo"] = re.sub(r"\s+", " ", t.group(1)).strip()[:70]
    if esito["stato"] == "KO" and not esito["motivo"]:
        esito["motivo"] = "pagina senza segnali di prodotto (layout cambiato?)"
    return esito


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nicchia", action="append", help="limita a una nicchia (ripetibile)")
    ap.add_argument("--json", action="store_true", help="stampa solo il path del report")
    ap.add_argument("--no-wait", action="store_true", help="nessuna pausa tra le richieste")
    args = ap.parse_args()

    voci = [v for v in _prodotti() if not args.nicchia or v[0] in args.nicchia]
    if not voci:
        print("Nessun prodotto da controllare.", file=sys.stderr)
        return 2

    risultati = []
    for i, (nid, pid, link) in enumerate(voci, 1):
        esito = _verifica(link)
        risultati.append({"nicchia": nid, "id": pid, "link": link, **esito})
        if not args.json:
            segno = {"OK": "✓", "KO": "✗", "BOT": "?"}.get(esito["stato"], "?")
            dettaglio = esito["motivo"] or esito["prezzo"] or esito["titolo"][:30]
            print(f"  {segno} {pid:11s} {esito['http'] or '---':>3}  {dettaglio}")
        if not args.no_wait and i < len(voci):
            time.sleep(0.8)  # gentile con Amazon: niente raffica

    ok = [r for r in risultati if r["stato"] == "OK"]
    ko = [r for r in risultati if r["stato"] == "KO"]
    bot = [r for r in risultati if r["stato"] == "BOT"]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"data": datetime.now().isoformat(timespec="seconds"),
         "totale": len(risultati), "ok": len(ok), "ko": len(ko), "bot": len(bot),
         "dettaglio": risultati}, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(OUT)
    else:
        print(f"\n{len(ok)}/{len(risultati)} vivi · {len(ko)} KO · {len(bot)} bloccati anti-bot")
        if ko:
            print("DA SOSTITUIRE: " + ", ".join(r["id"] for r in ko))
        print(f"report: {OUT}")
    return 1 if ko else 0


if __name__ == "__main__":
    raise SystemExit(main())
