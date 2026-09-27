#!/usr/bin/env python3
"""Scarica foto candidate da Openverse/Wikimedia (licenze liberali) per le nicchie.

Flusso:
  1. python3 tools/fetch_foto.py --nicchia casa           → candidati + contact sheet
  2. guardi output/candidati/casa_sheet.png e scegli gli indici
  3. python3 tools/fetch_foto.py --nicchia casa --seleziona 1,4,7

Le foto con licenza CC-BY/CC-BY-SA richiedono attribuzione: i crediti finiscono in
assets/backgrounds/<nicchia>/ATTRIBUTI.md (obbligatorio tenerli, vedi docs/05).
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from util import SFONDI_DIR  # noqa: E402

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

CAND = Path(__file__).resolve().parent.parent / "output" / "candidati"
UA = {"User-Agent": "sistema-pinterest-foto/1.0 (curatela free-license)"}

QUERIES = {
    # Scene lifestyle/textura on-trend 2026 (Imperfect by Design, warm-film,
    # natural light, moody, rustic, muted) — niente "minimalist living room" stock.
    "casa": [
        "warm natural light entryway shoes bench",
        "open wooden shelf plants white linen",
        "white linen folded texture soft",
        "dark moody closet organized",
        "clay pot plant warm morning light",
        "organized desk morning light ceramic",
        "rustic wooden shelf baskets linen",
        "soft white bed linen texture top",
    ],
    "cibo": [
        "dark moody sourdough bread baking",
        "terracotta ceramic bowl pasta fresh",
        "rustic bread sourdough dark wood",
        "fresh greens market market basket",
        "warm light breakfast flatlay berries",
        "potted herbs kitchen window light",
        "moody food photography dark slate",
        "handmade pasta dough wooden table",
    ],
    "finanza": [
        "old money desk leather notebook warm",
        "warm gold plant coins ceramic bowl",
        "cream marble calculator warm light",
        "handwritten budget planner cream paper",
        "soft gold coins potted plant morning",
        "minimalist wooden desk warm lamp notebook",
        "cream paper notebook gold coins plant",
        "muted brass coins ceramic warm",
    ],
    "parenting": [
        "soft pastel cotton baby clothes linen",
        "wooden toys muted colors basket",
        "knit baby blanket cream soft",
        "baby feet on natural linen",
        "pastel nursery texture wall paint",
        "soft knit stuffed toy muted colors",
        "wooden toy figure natural light",
        "baby linen onesie flat lay soft",
    ],
}


def _get(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def cerca_openverse(q: str, n: int) -> list[dict]:
    url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(
        {"q": q, "license": "cc0,pdm,by,by-sa", "page_size": n * 2, "mature": "false"}
    )
    dati = json.loads(_get(url))
    return dati.get("results", [])


def cerca_commons(q: str, n: int) -> list[dict]:
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "query", "format": "json", "generator": "search",
            "gsrnamespace": 6, "gsrsearch": q, "gsrlimit": n * 2,
            "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 1600,
        }
    )
    dati = json.loads(_get(url))
    out = []
    for pagina in (dati.get("query", {}).get("pages", {}) or {}).values():
        info = (pagina.get("imageinfo") or [{}])[0]
        if not info.get("thumburl"):
            continue
        meta = info.get("extmetadata", {})
        out.append(
            {
                "url": info["thumburl"],
                "title": pagina.get("title", ""),
                "creator": (meta.get("Artist", {}).get("value", "") or "")[:120],
                "license": meta.get("LicenseShortName", {}).get("value", "?"),
                "foreign_landing_url": info.get("descriptionurl", ""),
                "provider": "wikimedia",
            }
        )
    return out


def licenza_ok(lic: str) -> bool:
    lic = (lic or "").lower()
    return any(x in lic for x in ("cc0", "pdm", "public domain", "cc by", "cc-by", "by-sa", "attribution"))


def scarica_candidati(nicchia: str, quanti: int) -> list[Path]:
    cartella = CAND / nicchia
    cartella.mkdir(parents=True, exist_ok=True)
    esistenti = sorted(cartella.glob("[0-9][0-9][0-9]_*.jpg"))
    if len(esistenti) >= quanti:
        return esistenti[:quanti]
    meta_vie = cartella / "meta.json"
    meta = json.loads(meta_vie.read_text()) if meta_vie.exists() else {}
    scaricate: list[Path] = []
    visti: set[str] = set(meta.get("visti", []))

    for q in QUERIES.get(nicchia, []):
        if len(scaricate) >= quanti:
            break
        risultati = []
        try:
            risultati = cerca_openverse(q, 8)
        except Exception as e:
            print(f"  ! openverse fallito ({e}), provo Wikimedia")
        if not risultati:
            try:
                risultati = cerca_commons(q, 8)
            except Exception as e:
                print(f"  ! wikimedia fallito ({e})")
        for ris in risultati:
            if len(scaricate) >= quanti:
                break
            u = ris.get("url")
            if not u or u in visti or not licenza_ok(ris.get("license", "")):
                continue
            visti.add(u)
            try:
                dati = _get(u, timeout=30)
                img = Image.open(io.BytesIO(dati))
                if img.width < 900 and img.height < 900:
                    continue
                img = img.convert("RGB")
                if img.width < 1000:
                    img = img.resize((1000, int(img.height * 1000 / img.width)))
                idx = len(scaricate) + 1
                nome = cartella / f"{idx:03d}_{q.replace(' ', '-')[:24]}.jpg"
                img.save(nome, "JPEG", quality=90)
                scaricate.append(nome)
                meta[nome.name] = {
                    "titolo": ris.get("title", ""),
                    "creatore": ris.get("creator", ""),
                    "licenza": ris.get("license", ""),
                    "fonte": ris.get("foreign_landing_url", ""),
                    "provider": ris.get("provider", "openverse"),
                }
            except Exception:
                continue
    meta["visti"] = sorted(visti)
    meta_vie.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    return scaricate


def contact_sheet(nicchia: str) -> Path:
    cartella = CAND / nicchia
    file = sorted(cartella.glob("[0-9][0-9][0-9]_*.jpg"))
    if not file:
        raise SystemExit("nessun candidato da mostrare")
    celle, cols = [], 4
    cella = 300
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42)
    for i, p in enumerate(file, start=1):
        img = Image.open(p).convert("RGB")
        scala = max(cella / img.width, cella / img.height)
        img = img.resize((int(img.width * scala), int(img.height * scala)))
        x, y = (img.width - cella) // 2, (img.height - cella) // 2
        celle.append(img.crop((x, y, x + cella, y + cella)))
    righe = (len(celle) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cella, righe * cella), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    for i, c in enumerate(celle):
        px, py = (i % cols) * cella, (i // cols) * cella
        sheet.paste(c, (px, py))
        etichetta = str(i + 1)
        larg = d.textlength(etichetta, font=font)
        d.rectangle([px, py, px + larg + 22, py + 56], fill=(0, 0, 0))
        d.text((px + 11, py + 4), etichetta, font=font, fill=(255, 255, 0))
    percorso = cartella.parent / f"{nicchia}_sheet.png"
    sheet.save(percorso)
    return percorso


def seleziona(nicchia: str, indici: list[int]) -> None:
    cartella = CAND / nicchia
    file = sorted(cartella.glob("[0-9][0-9][0-9]_*.jpg"))
    meta = json.loads((cartella / "meta.json").read_text())
    destino = SFONDI_DIR / nicchia
    destino.mkdir(parents=True, exist_ok=True)
    righe_attr = []
    for i in indici:
        if i < 1 or i > len(file):
            print(f"  ! indice {i} fuori intervallo (1..{len(file)})")
            continue
        src = file[i - 1]
        shutil.copy(src, destino / src.name)
        m = meta.get(src.name, {})
        righe_attr.append(
            f"- `{src.name}` — {m.get('titolo', '?')} · foto: {m.get('creatore', '?')} · "
            f"licenza: {m.get('licenza', '?')} · fonte: {m.get('fonte', '?')}"
        )
        print(f"  ✓ {src.name} → assets/backgrounds/{nicchia}/")
    if righe_attr:
        attr = destino / "ATTRIBUTI.md"
        preesistente = attr.read_text() if attr.exists() else f"# Crediti foto — {nicchia}\n"
        attr.write_text(preesistente + "\n".join(righe_attr) + "\n")
        print(f"  ✓ crediti aggiunti in {attr}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--nicchia", required=True)
    p.add_argument("--quanti", type=int, default=12)
    p.add_argument("--seleziona", default=None, help="indici separati da virgola da promuovere")
    a = p.parse_args()
    if a.seleziona:
        seleziona(a.nicchia, [int(x) for x in a.seleziona.split(",")])
        return
    file = scarica_candidati(a.nicchia, a.quanti)
    print(f"{len(file)} candidati in {CAND / a.nicchia}")
    if file:
        print(f"contact sheet: {contact_sheet(a.nicchia)}")


if __name__ == "__main__":
    main()
