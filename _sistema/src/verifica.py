"""Pre-flight: valida la configurazione prima di pubblicare.

Controlla i 4 punti che, se sbagliati, non si vedono finché non è troppo tardi:
  1) link prodotti compilati (revenue)  2) board su Pinterest (lista esatta)
  3) handle/identità account            4) hosting (dove finiscono le immagini)
più: font, crediti foto, regole disclosure, shortener banditi.

Exit code 0 = si può pubblicare; 1 = almeno un BLOCCANTE.
Uso:  python3 src/verifica.py
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from util import ROOT, config_nicchie, log, sistema_cfg

VETTI_SHORTENER = ("bit.ly", "tinyurl", "t.co", "goo.gl", "cutt.ly", "is.gd", "ow.ly")
# ^ fallback se manca la chiave in config; fonte verità = sistema["validazione"]["dominii_vietati"]

_esiti: list[tuple[str, str, str]] = []  # (livello, area, messaggio)


def _ok(area: str, msg: str) -> None:
    _esiti.append(("OK", area, msg))
    log("ok", f"[{area}] {msg}")


def _warn(area: str, msg: str) -> None:
    _esiti.append(("WARN", area, msg))
    log("warn", f"[{area}] {msg}")


def _fail(area: str, msg: str) -> None:
    _esiti.append(("BLOCCANTE", area, msg))
    log("err", f"[{area}] BLOCCANTE — {msg}")


def _shortener(url: str, vietati: list | tuple = VETTI_SHORTENER) -> str | None:
    if not url:
        return None
    dom = (urlparse(url).netloc or "").lower().removeprefix("www.")
    for v in vietati:
        if dom == v or dom.endswith("." + v):
            return v
    return None


def esegui(reale: bool = True) -> bool:
    """Esegue tutti i controlli. Ritorna True se nessun BLOCCANTE."""
    global _esiti
    _esiti = []
    sistema = sistema_cfg()
    cfgs = config_nicchie()
    vietati = (sistema.get("validazione") or {}).get("dominii_vietati") or list(VETTI_SHORTENER)

    # ---------- 1. regole di sistema ----------
    regole = sistema["regole"]
    if regole["pin_giorno_max"] > 20:
        _fail("regole", f"pin_giorno_max={regole['pin_giorno_max']} supera il tetto breve (20).")
    else:
        _ok("regole", f"tetto {regole['pin_giorno_max']} pin/giorno nel limite del brief.")
    if not 150 <= regole["descrizione_min_char"] < regole["descrizione_max_char"] <= 500:
        _fail("regole", "intervalli descrizione incoerenti (min≥150, max≤500).")
    if regole["righe_csv_max"] > 200:
        _fail("regole", "righe_csv_max > 200 (limite ufficiale bulk Pinterest).")
    else:
        _ok("regole", f"split CSV a {regole['righe_csv_max']} righe/file.")

    # hosting: la radice del sito è l'unica fonte degli URL di tutto il sistema
    # (guide, pin, feed, stampabili, sitemap, Media URL del CSV). Si controlla
    # qui una volta sola: prima viveva in ogni config di nicchia come
    # `media_base_url`, cioè quattro copie di una cosa che non le leggeva
    # nessuno, con il rischio che una delle quattro restasse indietro.
    sito = str((sistema.get("hosting") or {}).get("sito_pubblico") or "").strip()
    if not sito:
        _fail("hosting", "hosting.sito_pubblico non è impostato in config/system.yaml — "
                         "senza la radice del sito tutti gli URL sono sbagliati.")
    elif not sito.startswith(("http://", "https://")):
        _fail("hosting", f"hosting.sito_pubblico non è un URL valido: {sito}")
    else:
        _ok("hosting", sito if sito.endswith("/") else sito + "/")

    # disclosure: le diciture commerciali devono contenere una parola AGCOM ammessa
    disc = sistema["disclosure"]
    agcom = re.compile(r"#adv|pubblicit|advertising", re.I)
    for chiave in ("affiliato", "affiliato_amazon", "proprio"):
        val = (disc.get(chiave) or "").strip()
        if val and not agcom.search(val):
            _fail("disclosure", f"'{chiave}' senza dicitura AGCOM ammessa (Pubblicità/ADV/Advertising): {val!r}")
        elif val:
            _ok("disclosure", f"'{chiave}' conforme.")
    if not agcom.search(disc.get("affiliato", "")):
        _fail("disclosure", "disclosure affiliato vuota/mancante: obbligatoria FTC+AGCOM.")
    for chiave in ("valore", "email"):
        if disc.get(chiave):
            _warn("disclosure", f"'{chiave}' non vuoto — i pin di valore/email non servono disclosure.")

    # ---------- 2. per nicchia ----------
    for nid, cfg in cfgs.items():
        # handle
        handle = (cfg["nicchia"].get("handle") or "").strip()
        if not handle or "da creare" in handle:
            _warn("handle", f"{nid}: handle da verificare/creare — {handle or '(vuoto)'}")
        else:
            _ok("handle", f"{nid}: {handle}")

        # boards (lista esatta da replicare su Pinterest)
        boards = cfg["nicchia"].get("boards") or []
        if not boards:
            _fail("boards", f"{nid}: nessuna board in config — il CSV non avrà dove pubblicare.")
        else:
            _ok("boards", f"{nid}: " + " | ".join(boards))

        # prodotti / link
        prodotti = cfg.get("prodotti") or []
        con_link = [p for p in prodotti if (p.get("link") or "").strip()]
        vuoti = [p["id"] for p in prodotti if not (p.get("link") or "").strip()]
        if len(prodotti) < regole["min_prodotti_per_nicchia"]:
            _warn("prodotti", f"{nid}: {len(prodotti)} prodotti (< {regole['min_prodotti_per_nicchia']} consigliati).")
        else:
            _ok("prodotti", f"{nid}: {len(prodotti)} prodotti configurati.")
        if reale and not con_link:
            _warn("link", f"{nid}: NESSUN link compilato → solo pin di valore, zero revenue. "
                          "Compila 'link:' in config/nicchie/" + nid + ".yaml")
        elif con_link:
            _ok("link", f"{nid}: {len(con_link)}/{len(prodotti)} link compilati "
                        f"({len(vuoti)} ancora vuoti).")

        # shortener banditi in ogni link configurato (lista dal config, non hardcoded)
        for p in prodotti:
            lk = (p.get("link") or "").strip()
            s = _shortener(lk, vietati)
            if s:
                _fail("link", f"{nid}/{p.get('id')}: shortener vietato {s} — Pinterest lo tratta come spam.")

        # tag affiliato Amazon: ogni link Amazon deve contenere il tracking ID,
        # altrimenti le vendite non vengono attribuite (= commissioni perse)
        tracking = ((sistema.get("affiliazioni") or {}).get("amazon_tracking_id") or "").strip().lower()
        for p in prodotti:
            lk = (p.get("link") or "").strip()
            if not lk or "amazon." not in urlparse(lk).netloc.lower():
                continue
            if not tracking:
                _warn("link", f"{nid}/{p.get('id')}: link Amazon ma amazon_tracking_id vuoto "
                              "in config/system.yaml — imposta lo StoreID.")
            elif f"tag={tracking}" not in lk.lower():
                livello = _fail if reale else _warn
                livello("link", f"{nid}/{p.get('id')}: link Amazon SENZA tag '{tracking}' — "
                                "vendite non attribuite! Ricrealo con la SiteStripe (link lungo).")

        # foto di sfondo + crediti.
        # In CI assets/backgrounds non c'è di proposito (16 MB di foto non stanno
        # nel repo del sito): le cover sono già committate e la pipeline le riusa.
        # Qui il controllo va saltato, non segnalato come difetto.
        cartella = ROOT / "assets" / "backgrounds" / nid
        if not (ROOT / "assets" / "backgrounds").exists():
            continue
        foto = [p for p in cartella.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")] \
            if cartella.exists() else []
        if len(foto) < 2:
            _warn("foto", f"{nid}: solo {len(foto)} foto di sfondo (consigliate ≥3, vedi tools/fetch_pexels.py).")
        else:
            att = cartella / "ATTRIBUTI.md"
            if not att.exists() or "CREDITO MANCANTE" in att.read_text(encoding="utf-8"):
                _warn("foto", f"{nid}: crediti foto incompleti — rigenera ATTRIBUTI.md.")
            else:
                _ok("foto", f"{nid}: {len(foto)} foto con crediti completi.")

    # ---------- 3. font referenziati ----------
    fonts_dir = ROOT / "assets" / "fonts"
    for nid, cfg in cfgs.items():
        for chiave, nome in (cfg.get("design") or {}).items():
            if chiave.startswith("font_") and nome and not (fonts_dir / f"{nome}.ttf").exists() \
                    and not (fonts_dir / nome).exists():
                _warn("font", f"{nid}: font '{nome}' ({chiave}) non trovato in assets/fonts/.")

    # ---------- riepilogo ----------
    n_fail = sum(1 for e in _esiti if e[0] == "BLOCCANTE")
    n_warn = sum(1 for e in _esiti if e[0] == "WARN")
    n_ok = sum(1 for e in _esiti if e[0] == "OK")
    print()
    if n_fail:
        log("err", f"VERIFICA: {n_fail} bloccanti, {n_warn} avvisi, {n_ok} ok — non pubblicare.")
    elif n_warn:
        log("warn", f"VERIFICA: 0 bloccanti, {n_warn} avvisi, {n_ok} ok — puoi pubblicare, ma leggi gli avvisi.")
    else:
        log("ok", f"VERIFICA: tutto verde ({n_ok} ok) — pronto per la pubblicazione.")
    return n_fail == 0


def main() -> int:
    """Pre-flight stand-alone: `python3 src/verifica.py`.

    Girava solo dentro la CLI legacy (src/main.py verifica). È Ora lanciato anche
    dalla pipeline, prima del build: se la configurazione si sposta (handle
    sbagliato, board rinominata, link prodotto vuoto) lo scopriamo in un run
    rosso invece di un mese dopo, quando il pin esce con il link sbagliato.
    """
    return 0 if esegui(reale=False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
