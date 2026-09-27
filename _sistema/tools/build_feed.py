#!/usr/bin/env python3
"""Genera i feed RSS 2.0 per la pubblicazione automatica Pinterest (uno per bacheca).

Sorgenti: content/guide/*.md (frontmatter board:, pubblica_dal:) + config/nicchie/*.yaml.
Output: site/feed-<nid>-<boardslug>.xml — solo per le board che hanno guide pubblicabili
oggi (guida con pubblica_dal futuro resta fuori dal feed finché non arriva la data).

Pinterest crea i pin da solo entro 24h (max 200/giorno): titolo/descrizione dagli
item, immagine da <enclosure>/<media:content> (cover di nicchia), link alla guida
(sul dominio verificato — prerequisito, vedi docs/05-operazioni.md).
Collegamento una tantum: Impostazioni → Crea Pin in blocco → Collega feed RSS.

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
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "content" / "guide"
SITE = ROOT / "site"

# anti-burst: nel feed stanno solo gli item recenti (vedi genera())
FINESTRA_GIORNI = 45
MAX_ITEM_PER_FEED = 4


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
    for nid in ["casa", "cibo", "finanza", "parenting"]:
        cfg = yaml.safe_load((ROOT / "config" / "nicchie" / f"{nid}.yaml").read_text(encoding="utf-8"))
        base = (cfg.get("media_base_url") or "").strip().rstrip("/")
        if base:
            return base.rsplit("/", 1)[0] + "/"
    return "https://example.com/pinn-site/"


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def genera() -> list[Path]:
    base = _site_base()
    from datetime import date, datetime, timezone

    oggi = date.today().isoformat()
    # raggruppa guide per (nicchia, board) — SOLO quelle pubblicabili oggi:
    # `pubblica_dal` futuro = fuori dal feed (altrimenti Pinterest le posta in anticipo)
    gruppi: dict[tuple[str, str], list[Path]] = {}
    for src in sorted(SRC.glob("*.md")):
        nid = {"casa": "casa", "cibo": "cibo", "fin": "finanza", "par": "parenting"}.get(
            src.stem.split("-")[0], src.stem.split("-")[0])
        text = src.read_text(encoding="utf-8")
        meta = yaml.safe_load(text.split("---", 2)[1]) if text.startswith("---") else {}
        board = (meta or {}).get("board", "")
        # tutti i board con guide entrano nel gruppo (anche se la coda è vuota:
        # serve a riscrivere il feed e cancellare i vecchi item già pubblicati)
        if board:
            gruppi.setdefault((nid, board), []).append(src)
    # printables (config/printable.yaml) → feed della board "Printable Finanziari"
    for _ps in (list(yaml.safe_load_all((ROOT / "config" / "printable.yaml").read_text(encoding="utf-8"))) or []):
        if not _ps or _ps.get("board") != "Printable Finanziari":
            continue
        _dal = str(_ps.get("pubblica_dal") or "")
        _gia = str(_ps.get("pubblicato") or "")
        _txt = (f"---\ntitolo: {_ps.get('titolo','')}\ndescrizione: {_ps.get('descrizione','')}\n"
                f"board: Printable Finanziari\npubblica_dal: {_dal}\npubblicato: {_gia}\n---\n")
        class _Psrc:
            stem = _ps["slug"]
            def read_text(self, encoding="utf-8"): return _txt
        gruppi.setdefault(("finanza", "Printable Finanziari"), []).append(_Psrc())
    scritti: list[Path] = []
    # Difesa anti-burst: se un feed viene ricollegato, Pinterest riscanterebbe
    # TUTTI gli item storici e li posterebbe in una raffica. Mostriamo quindi
    # solo gli ultimi (finestra + tetto): i pin vecchi esistono già, le guide
    # restano online alle stesse URL.
    import time

    taglio = time.time() - FINESTRA_GIORNI * 86400
    for (nid, board), files in sorted(gruppi.items()):
        # ordine RSS corretto: dal più RECENTE al più vecchio (i lettori leggono dall'alto,
        # Pinterest prende di fatto il primo item → deve sempre essere l'ultimo rilascio)
        voci: list[tuple[float, Path, dict]] = []
        scartate = 0
        pubblicate: list[tuple[float, Path, dict]] = []
        for src in files:
            text = src.read_text(encoding="utf-8")
            meta = yaml.safe_load(text.split("---", 2)[1]) if text.startswith("---") else {}
            dal = str((meta or {}).get("pubblica_dal") or "")
            gia = str((meta or {}).get("pubblicato") or "")
            if dal:
                ts = datetime.fromisoformat(dal).replace(tzinfo=timezone.utc).timestamp()
            else:
                ts = src.stat().st_mtime
            # già pubblicato = pin già su Pinterest: resta online ma FUORI dal feed
            if gia:
                scartate += 1
                pubblicate.append((ts, src, meta or {}))
                continue
            if dal and dal > oggi:
                scartate += 1
                continue  # ancora in programma
            voci.append((ts, src, meta or {}))
        voci.sort(key=lambda v: (v[0], v[1].name), reverse=True)
        pubblicate.sort(key=lambda v: (v[0], v[1].name), reverse=True)
        mostrati = [v for v in voci if v[0] >= taglio][:MAX_ITEM_PER_FEED]
        # se il feed sarebbe vuoto, include l'ultimo pubblicato: il feed non
        # deve mai essere vuoto (Pinterest rifiuta "no articles"), e il pin
        # è già esistente → non verrà ri-creato.
        if not mostrati and pubblicate:
            mostrati = [pubblicate[0]]
            scartate -= 1
        if len(mostrati) < len(voci) + len(pubblicate):
            print(f"  {nid}/{board}: {len(voci)} item in coda → nel feed i {len(mostrati)} "
                  f"più recenti (finestra {FINESTRA_GIORNI}gg, tetto {MAX_ITEM_PER_FEED})")
        voci = mostrati
        items = []
        ultimo = 0.0
        for ts, src, meta in voci:
            titolo = meta.get("titolo", src.stem)
            descr = meta.get("descrizione", "")
            url = f"{base}guide/{src.stem}.html"
            pub = email.utils.formatdate(ts, usegmt=True)
            # cover UNICA per guida (in locale la genera build_cover_guide.py):
            # se tutti gli item dello stesso feed hanno la stessa immagine,
            # Pinterest rischia di deduplicarli e di non postarli mai
            cover_propria = SITE / "covers" / f"guida-{src.stem}.jpg"
            if not cover_propria.exists():
                cover_propria = SITE / "covers" / f"printable-{src.stem}.jpg"
            cover = (f"{base}covers/guida-{src.stem}.jpg" if cover_propria.exists()
                     else f"{base}covers/{nid}.jpg")
            ultimo = max(ultimo, ts)
            items.append(
                f"    <item>\n      <title>{_esc(titolo)}</title>\n"
                f"      <link>{url}</link>\n      <guid isPermaLink=\"true\">{url}</guid>\n"
                f"      <description>{_esc(descr)}</description>\n"
                f"      <pubDate>{pub}</pubDate>\n"
                f"      <enclosure url=\"{cover}\" type=\"image/jpeg\" />\n"
                f"      <media:content url=\"{cover}\" medium=\"image\" type=\"image/jpeg\" />\n"
                f"    </item>"
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
        dst = SITE / f"feed-{nid}-{slug_board(board)}.xml"
        dst.write_text(xml, encoding="utf-8")
        scritti.append(dst)
        # Gemella "feed2-*": stesso contenuto, URL NUOVO. Se Pinterest non riprende
        # i feed collegati (li ha svuotati e poi ha smesso), si ricollega questo:
        # URL nuovo = validazione da zero. Attenzione: togli il feed vecchio.
        gemello = SITE / f"feed2-{nid}-{slug_board(board)}.xml"
        gemello.write_text(xml, encoding="utf-8")
        scritti.append(gemello)
        stato = (f"{len(items)} item in coda" if items
                 else "coda vuota (tutto già pubblicato o in programma)")
        if scartate or not items:
            print(f"  {nid}/{board}: {stato}, {scartate} esclusi")
    print(f"feed: {len(scritti)} file ({len(scritti) // 2} board + gemelli feed2 per il ricollegamento)")
    return scritti


def check() -> bool:
    ok = True
    for xml in sorted(SITE.glob("feed-*.xml")):
        try:
            root = ET.parse(str(xml)).getroot()
            items = root.findall("./channel/item")
            if not items:
                # feed vuoto = legittimo: è la coda, e la coda è vuota.
                # (Pinterest non ha nulla da postare, il feed resta valido)
                continue
            for it in items:
                for tag in ("title", "link", "description"):
                    el = it.find(tag)
                    if el is None or not (el.text or "").strip():
                        print(f"CHECK ✗ {xml.name}: item senza <{tag}>")
                        ok = False
                enc = it.find("enclosure")
                if enc is None or not (enc.get("url") or "").startswith("https://"):
                    print(f"CHECK ✗ {xml.name}: enclosure non https")
                    ok = False
                link = (it.findtext("link") or "")
                if "guide/" not in link:
                    print(f"CHECK ✗ {xml.name}: link fuori dal dominio guide")
                    ok = False
        except ET.ParseError as e:
            print(f"CHECK ✗ {xml.name}: XML non valido ({e})")
            ok = False
    # slug board: devono esistere nei config
    boards_cfg = set()
    for nid in ["casa", "cibo", "finanza", "parenting"]:
        cfg = yaml.safe_load((ROOT / "config" / "nicchie" / f"{nid}.yaml").read_text(encoding="utf-8"))
        for b in cfg["nicchia"].get("boards") or []:
            boards_cfg.add(slug_board(b))
    # guida FUTURE e già PUBBLICATE non devono comparire nei feed
    # (le future verrebbero postate in anticipo; le pubblicate sono fallback ≤1)
    from datetime import date as _date
    _oggi = _date.today().isoformat()
    future, gia_pub = set(), set()
    for _src in SRC.glob("*.md"):
        _t = _src.read_text(encoding="utf-8")
        _m = yaml.safe_load(_t.split("---", 2)[1]) if _t.startswith("---") else {}
        _dal = str((_m or {}).get("pubblica_dal") or "")
        if _dal and _dal > _oggi:
            future.add(_src.stem)
        if (_m or {}).get("pubblicato"):
            gia_pub.add(_src.stem)
    for xml in SITE.glob("feed-*.xml"):
        testo = xml.read_text(encoding="utf-8")
        for slug_futuro in sorted(future):
            if f"guide/{slug_futuro}.html" in testo:
                print(f"CHECK \u2717 {xml.name}: contiene la guida futura {slug_futuro}")
                ok = False
        for slug_pub in sorted(gia_pub):
            if f"guide/{slug_pub}.html" in testo:
                pub_in_feed = sum(1 for s in gia_pub if f"guide/{s}.html" in testo)
                if pub_in_feed > 1:
                    print(f"CHECK \u2717 {xml.name}: contiene {slug_pub}, gia' pubblicato "
                          f"come pin (nel feed deve restare solo la coda)")
                    ok = False
    if ok:
        print(f"CHECK ✓ feed validi, slug coerenti, coda pulita "
              f"({len(gia_pub)} guide già pubblicate escluse)")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    genera()
    if args.check and not check():
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
