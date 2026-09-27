#!/usr/bin/env python3
"""Genera i feed RSS 2.0 per la pubblicazione automatica Pinterest (uno per bacheca).

Sorgenti: content/guide/*.md (frontmatter board:, pin:, kw:, pubblica_dal:) +
config/nicchie/*.yaml + config/printable.yaml.
Output: site/feed-<nid>-<boardslug>.xml — e il gemello feed2- con lo stesso
contenuto (URL nuovo, da usare se i feed collegati smettono di essere letti).

Pinterest crea i pin da solo entro 24h (max 200/giorno): titolo/descrizione dagli
item, immagine da <enclosure>/<media:content>, link alla guida (sul dominio
rivendicato — prerequisito, vedi docs/05-operazioni.md). Collegamento una tantum
per ogni feed: Impostazioni → Crea Pin in blocco → Collega feed RSS.

## Una guida, più pin

Per fare volume (1 pin al giorno per board) servono molti più pin che guide.
Una guida può quindi produrre più pin, dichiarati nel frontmatter:

    pin:
      - t: "Come organizzare il sotto lavandino: 12 idee che funzionano"
        d: "Il metodo in 5 mosse, con i prodotti che servono davvero."
        v: 1
      - t: "Sotto lavandino disordinato? Ecco cosa ci metti dentro"
        d: "..."
        v: 2

`v` è il numero di variante: sceglie la cover (guida-<slug>.jpg per v=1,
guida-<slug>-v2.jpg per v=2, …) e le varianti hanno ognuna un layout diverso,
altrimenti Pinterest le deduplica. Una guida senza `pin:` ne genera uno solo,
dal titolo e dalla descrizione: il comportamento di prima.

Due dettagli che vengono da come funziona un lettore RSS, non da Pinterest:

- il <guid> NON è il link alla guida. Due pin della stessa guida hanno lo
  stesso link, e un guid identico fa sì che il secondo venga scartato come
  "già visto". Il guid è quindi l'URL della cover, univoco per variante.
- l'ordine è dal più recente al più vecchio, come vuole RSS, ma Pinterest
  pubblica il più vecchio prima: per questo nel feed c'è un solo item per
  giorno (regole.pin_per_feed_giorno). Se ne mettessimo più, Pinterest li
  prenderebbe tutti insieme e il ritmo quotidiano diventerebbe un botto.

Uso:
  python3 tools/build_feed.py            # (di solito via tools/build_sito.py)
  python3 tools/build_feed.py --check    # valida XML + slug board vs Pinterest
"""
from __future__ import annotations

import argparse
import email.utils
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import url_base  # noqa: E402 — radice del sito, fonte unica

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "content" / "guide"
SITE = ROOT / "site"
NICCHIE = {"casa": "casa", "cibo": "cibo", "fin": "finanza", "par": "parenting",
           "budget": "finanza", "tracker": "finanza", "piano": "finanza",
           "sfida": "finanza", "calcolatore": "finanza", "cash": "finanza",
           "agenda": "finanza"}
# finestra dei pin già usati: serve al commento del ricalcolo, non al calcolo
FINESTRA_GIORNI = 45


def slug_board(board: str) -> str:
    """Slug stile Pinterest: minuscole, spazi→trattini, & e speciali via.
    Verificato contro gli slug live (es. 'Pulizie & Routine' → 'pulizie-routine')."""
    s = board.lower()
    s = re.sub(r"[àáâä]", "a", s)
    s = re.sub(r"[èéêë]", "e", s)
    s = re.sub(r"[ìíîï]", "i", s)
    s = re.sub(r"[òóôö]", "o", s)
    s = re.sub(r"[ùúûü]", "u", s)
    s = s.replace("&", " ")
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", "-", s.strip())


def _site_base() -> str:
    return url_base.site_base(ROOT)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _frontmatter(src: Path) -> dict:
    testo = src.read_text(encoding="utf-8")
    if not testo.startswith("---"):
        return {}
    try:
        return yaml.safe_load(testo.split("---", 2)[1]) or {}
    except yaml.YAMLError:
        return {}


def _pin_di(meta: dict, v: int) -> dict:
    pins = meta.get("pin") or []
    if isinstance(pins, list) and 1 <= v <= len(pins) and isinstance(pins[v - 1], dict):
        return pins[v - 1]
    return {}


def _n_varianti(meta: dict) -> int:
    """Quanti pin ha la guida. Zero pin dichiarati → 1 (il pin unico di prima)."""
    pins = meta.get("pin") or []
    return max(1, len(pins)) if isinstance(pins, list) else 1


def _cover_di(slug: str, v: int) -> str:
    """Nome file della cover della variante v. Coerente con build_cover_guide.py."""
    return f"guida-{slug}.jpg" if v == 1 else f"guida-{slug}-v{v}.jpg"


def _pin(nid: str, slug: str, meta: dict, v: int, base: str) -> dict | None:
    """Un pin pronto per il feed, o None se la variante non ha una cover.

    `None` quando la cover non esiste: metterei nell'item un'immagine che non
    c'è e Pinterest mostrerebbe un quadratino vuoto, o prenderebbe la cover
    generica di nicchia — che è proprio l'immagine condivisa che fa
    deduplicare i pin. Meglio il pin che salta, e lo dice.
    """
    pin = _pin_di(meta, v)
    nome_cover = _cover_di(slug, v)
    if not (SITE / "covers" / nome_cover).exists():
        # i printable hanno una copertura diversa (printable-<slug>.jpg)
        if (SITE / "covers" / f"printable-{slug}.jpg").exists():
            nome_cover = f"printable-{slug}.jpg"
        elif v == 1 and (SITE / "covers" / f"{nid}.jpg").exists():
            nome_cover = f"{nid}.jpg"
        else:
            return None
    titolo = str(pin.get("t") or meta.get("titolo") or slug).strip()
    descr = str(pin.get("d") or meta.get("descrizione") or "").strip()
    if not titolo or not descr:
        return None
    url = f"{base}guide/{slug}.html"
    return {
        "nid": nid, "slug": slug, "v": v,
        "board": str(meta.get("board") or "").strip(),
        "titolo": titolo, "descrizione": descr,
        "url": url,
        "cover": f"{base}covers/{nome_cover}",
        "guid": f"{base}covers/{nome_cover}",   # univoco per variante, vedi docstring
        "kw": [str(k).strip() for k in (meta.get("kw") or []) if str(k).strip()],
        "dal": str(meta.get("pubblica_dal") or "").strip(),
        "gia": str(meta.get("pubblicato") or "").strip(),
    }


def _raccogli(base: str) -> tuple[dict[tuple[str, str], list[dict]],
                                  dict[tuple[str, str], dict]]:
    """Tutti i pin di tutti i board, raggruppati per (nicchia, board).

    Restituisce anche i pin "di banchina": l'ultimo pin n.1 di una guida già
    pubblicata, per board. Non entra mai nelle rotazione (quel pin esiste già su
    Pinterest, rimetterlo produrrebbe un duplicato), ma serve quando un board
    non ha più niente da sfilare: un feed vuoto viene rifiutato, e il pin di
    banchina è già esistente quindi non viene ricreato.
    """
    gruppi: dict[tuple[str, str], list[dict]] = {}
    banchina: dict[tuple[str, str], dict] = {}
    for src in sorted(SRC.glob("*.md")):
        meta = _frontmatter(src)
        board = str(meta.get("board") or "").strip()
        if not board:
            continue
        prefisso = src.stem.split("-")[0]
        nid = NICCHIE.get(prefisso, prefisso)
        chiave = (nid, board)
        primo = _pin(nid, src.stem, meta, 1, base)
        if primo is None:
            print(f"  ! {src.stem} v1: nessuna cover, pin saltato "
                  f"(genera le varianti con build_cover_guide.py --varianti N)")
            continue
        if primo["gia"]:
            # già su Pinterest: vale solo come pin di banchina
            prec = banchina.get(chiave)
            if prec is None or primo["giorno"] > prec["giorno"]:
                primo["giorno"] = date.fromisoformat(primo["gia"])
                banchina[chiave] = primo
            continue
        gruppi.setdefault(chiave, []).append(primo)
        for v in range(2, _n_varianti(meta) + 1):
            p = _pin(nid, src.stem, meta, v, base)
            if p is None:
                print(f"  ! {src.stem} v{v}: nessuna cover, pin saltato "
                      f"(genera le varianti con build_cover_guide.py --varianti N)")
                continue
            gruppi.setdefault(chiave, []).append(p)
    # printables (config/printable.yaml) → feed della board "Printable Finanziari"
    for ps in (yaml.safe_load_all((ROOT / "config" / "printable.yaml").read_text(encoding="utf-8")) or []):
        if not ps or ps.get("board") != "Printable Finanziari":
            continue
        meta = {
            "titolo": ps.get("titolo", ""), "descrizione": ps.get("descrizione", ""),
            "board": "Printable Finanziari", "pubblica_dal": str(ps.get("pubblica_dal") or ""),
            "pubblicato": str(ps.get("pubblicato") or ""), "kw": ps.get("kw") or [],
        }
        p = _pin("finanza", ps["slug"], meta, 1, base)
        if not p:
            continue
        chiave = ("finanza", "Printable Finanziari")
        if p["gia"]:
            if p["gia"]:
                p["giorno"] = date.fromisoformat(p["gia"])
            banchina[chiave] = p
        else:
            gruppi.setdefault(chiave, []).append(p)
    # i board che hanno solo pin di banchina devono avere comunque un feed
    for chiave in banchina:
        gruppi.setdefault(chiave, [])
    return gruppi, banchina


def _piano(pins: list[dict], ancora: str, oggi: date, per_giorno: int) -> list[dict]:
    """Ordina i pin del board e dice quali devono stare nel feed oggi.

    Il pin numero i del board esce il giorno ancora + i, uno al giorno: è un
    calendario calcolato, quindi non va aggiornato a mano e in CI dà lo stesso
    risultato di oggi. Un `pubblica_dal` esplicito può solo posticipare il
    pin, mai anticiparlo (è il controllo che avevi prima).

    Restituisce gli ultimi `per_giorno` pin già usciti. Se il board ha già
    finito le scorte, l'ultimo pin resta nel feed all'infinito: è già esistente
    su Pinterest, quindi non viene ricreato, e il feed non resta mai vuoto.
    """
    for i, p in enumerate(sorted(pins, key=lambda q: (q["slug"], q["v"]))):
        giorno = ancora + timedelta(days=i // per_giorno)
        if p["dal"]:
            try:
                giorno = max(giorno, date.fromisoformat(p["dal"]))
            except ValueError:
                pass
        p["giorno"] = giorno
    ordinati = sorted(pins, key=lambda q: (q["giorno"], q["slug"], q["v"]))
    usciti = [p for p in ordinati if p["giorno"] <= oggi]
    if len(usciti) >= per_giorno:
        return usciti[-per_giorno:]
    return usciti


def genera() -> list[Path]:
    base = _site_base()
    sistema = yaml.safe_load((ROOT / "config" / "system.yaml").read_text(encoding="utf-8")) or {}
    regole = sistema.get("regole") or {}
    pub = sistema.get("pubblicazione") or {}
    per_giorno = int(regole.get("pin_per_feed_giorno") or 1)
    ancora = date.fromisoformat(str(pub.get("pin_ancora") or date.today().isoformat()))
    oggi = date.today()
    gruppi, banchina = _raccogli(base)

    scritti: list[Path] = []
    for (nid, board), pins in sorted(gruppi.items()):
        mostrati = _piano(pins, ancora, oggi, per_giorno)
        di_banchina = False
        if not mostrati:
            # niente da sfilare oggi: il feed non può restare vuoto
            mostrati = [banchina[(nid, board)]] if (nid, board) in banchina else []
            di_banchina = bool(mostrati)
        items = []
        ultimo = 0.0
        for p in mostrati:
            ts = datetime.combine(p["giorno"], datetime.min.time(),
                                  tzinfo=timezone.utc).timestamp()
            ultimo = max(ultimo, ts)
            # Le keyword finiscono in due posti. Nei <category>, che è dove un
            # lettore RSS le cerca, e in coda alla descrizione, che è il campo
            # che Pinterest usa davvero per il testo del pin. Solo tre, perché
            # un elenco di cinque a fine descrizione si legge come spam: le altre
            # due restano nei <category>.
            descr = p["descrizione"]
            if p["kw"]:
                descr = f"{descr} {' · '.join(p['kw'][:3])}"
            items.append(
                f"    <item>\n      <title>{_esc(p['titolo'])}</title>\n"
                f"      <link>{p['url']}</link>\n"
                f"      <guid isPermaLink=\"false\">{p['guid']}</guid>\n"
                f"      <description>{_esc(descr)}</description>\n"
                f"      <pubDate>{email.utils.formatdate(ts, usegmt=True)}</pubDate>\n"
                f"      <enclosure url=\"{p['cover']}\" type=\"image/jpeg\" />\n"
                f"      <media:content url=\"{p['cover']}\" medium=\"image\" type=\"image/jpeg\" />\n"
                + "".join(f"      <category>{_esc(k)}</category>\n" for k in p["kw"])
                + "    </item>"
            )
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">\n'
            f"  <channel>\n    <title>Quattro Mondi — {_esc(board)}</title>\n"
            f"    <link>{base}guide/</link>\n"
            f"    <description>Guide {_esc(board)} (Quattro Mondi)</description>\n"
            f"    <language>it-it</language>\n"
            f"    <lastBuildDate>{email.utils.formatdate(ultimo, usegmt=True)}</lastBuildDate>\n"
            + "\n".join(items)
            + "\n  </channel>\n</rss>\n"
        )
        for prefisso in ("feed", "feed2"):
            dst = SITE / f"{prefisso}-{nid}-{slug_board(board)}.xml"
            dst.write_text(xml, encoding="utf-8")
            scritti.append(dst)
        if len(pins) <= per_giorno:
            stato = f"scorte esaurite: {len(pins)} pin in tutto, il feed ripete l'ultimo"
        else:
            stato = f"{len(pins)} pin in coda"
        if di_banchina:
            stato = "in attesa (ancora non scaduta) · mostro il pin già pubblicato"
        print(f"  {nid}/{board}: {stato} → {len(items)} item")
    print(f"feed: {len(scritti)} file ({len(scritti) // 2} board + gemelli feed2)")
    print(f"ritmo: {per_giorno} pin/giorno per board · ancora {ancora} · "
          f"copertura ~{max((len(p) for p in gruppi.values()), default=0) // per_giorno} giorni")
    return scritti


def check() -> bool:
    """Il feed scritto deve corrispondere esattamente a quello che dice lo
    scheduler. È un controllo più forte del vecchio "non rimettere i pin già
    pubblicati": se i due divergono, lo scheduler è cambiato senza rigenerare
    i feed, e Pinterest si troverebbe item fuori programma.
    """
    ok = True
    sistema = yaml.safe_load((ROOT / "config" / "system.yaml").read_text(encoding="utf-8")) or {}
    regole = sistema.get("regole") or {}
    per_giorno = int(regole.get("pin_per_feed_giorno") or 1)
    ancora = date.fromisoformat(str((sistema.get("pubblicazione") or {}).get("pin_ancora")
                                    or date.today().isoformat()))
    oggi = date.today()
    gruppi, banchina = _raccogli(_site_base())

    for (nid, board), pins in sorted(gruppi.items()):
        attesi = _piano(pins, ancora, oggi, per_giorno)
        if not attesi and (nid, board) in banchina:
            # board finito: in feed c'è il pin di banchina, che è già su
            # Pinterest. Non è una ripubblicazione, è l'unico modo per non
            # lasciare il feed vuoto.
            attesi = [banchina[(nid, board)]]
        attesi_guid = {p["guid"] for p in attesi}
        for prefisso in ("feed", "feed2"):
            xml = SITE / f"{prefisso}-{nid}-{slug_board(board)}.xml"
            if not xml.exists():
                print(f"CHECK ✗ {xml.name}: non generato")
                ok = False
                continue
            try:
                items = ET.parse(str(xml)).getroot().findall("./channel/item")
            except ET.ParseError as e:
                print(f"CHECK ✗ {xml.name}: XML non valido ({e})")
                ok = False
                continue
            for it in items:
                for tag in ("title", "link", "description", "guid"):
                    el = it.find(tag)
                    if el is None or not (el.text or "").strip():
                        print(f"CHECK ✗ {xml.name}: item senza <{tag}>")
                        ok = False
                enc = it.find("enclosure")
                url = (enc.get("url") if enc is not None else "") or ""
                if not url.startswith("https://"):
                    print(f"CHECK ✗ {xml.name}: enclosure non https")
                    ok = False
                elif not (SITE / "covers" / url.rsplit("/", 1)[-1]).exists():
                    print(f"CHECK ✗ {xml.name}: immagine inesistente {url}")
                    ok = False
                if "guide/" not in (it.findtext("link") or ""):
                    print(f"CHECK ✗ {xml.name}: link fuori dal dominio guide")
                    ok = False
            if {it.findtext("guid") for it in items} != attesi_guid:
                if {it.findtext("guid") for it in items} - attesi_guid:
                    print(f"CHECK ✗ {xml.name}: item non previsti dallo scheduler")
                    ok = False
                if attesi_guid - {it.findtext("guid") for it in items}:
                    print(f"CHECK ✗ {xml.name}: item previsti e mancanti")
                    ok = False
            if len(items) > per_giorno:
                print(f"CHECK ✗ {xml.name}: {len(items)} item, il ritmo è {per_giorno}/giorno")
                ok = False

    # ritmo: quanti pin escono davvero per account a settimana. Con
    # pin_per_feed_giorno=1 e 5 board per account sono ~35 a settimana, cioè i
    # 5 al giorno per cui è impostata la cadenza. Il tetto serve a fermare una
    # corsa, non a descrivere il piano.
    per_account: dict[str, dict[tuple[int, int], int]] = {}
    for (nid, board), pins in gruppi.items():
        for p in _piano(pins, ancora, oggi, per_giorno):
            anno, sett, _ = p["giorno"].isocalendar()
            per_account.setdefault(nid, {}).setdefault((anno, sett), 0)
            per_account[nid][(anno, sett)] += 1
    max_sett = int(regole.get("pin_settimana_max") or 0)
    if max_sett:
        for nid, settimane in sorted(per_account.items()):
            for (anno, sett), n in sorted(settimane.items()):
                if n > max_sett:
                    print(f"CHECK ✗ ritmo: {nid} {anno}-W{sett:02d} = {n} pin (tetto {max_sett})")
                    ok = False
    if ok:
        tutte = [(a, s) for d in per_account.values() for (a, s) in d]
        anno, sett = max(tutte) if tutte else (0, 0)
        print(f"CHECK ✓ {len(gruppi)} board coerenti con lo scheduler · "
              f"coda fino a {anno}-W{sett:02d}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    genera()
    if args.check and not check():
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
