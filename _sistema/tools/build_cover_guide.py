#!/usr/bin/env python3
"""Cover uniche per ogni guida → site/covers/guida-<slug>.jpg (+ varianti).

Perché esiste: i pin creati via RSS partono dall'immagine dell'item — se tutti
gli item di uno stesso feed condividono la stessa cover, Pinterest rischia di
deduplicarli e di non pubblicarli. Ogni guida ha quindi una sua immagine in
stile pin (titolo della guida + foto/layour di nicchia).

Le VARIANTI (--varianti N) servono a fare volume: per 1 pin al giorno su ogni
board servono molti più pin che guide, e la stessa guida può avere più pin
(segnalati da `pin:` nel frontmatter) purché abbiano immagine DIVERSA. La
variante v forza un layout diverso dalla v-1 e usa come testo il titolo del pin
v, così le immagini non si somigliano: è la difesa contro il deduplicatore.

La cover è DETERMINISTICA: rng seminato sullo slug (e sul numero di variante)
→ rigenerandola non cambia (e quindi non genera commit inutili). In più viene
ricreata solo se la guida sorgente è più nuova della cover.

Attenzione: la variante 1 riprende esattamente il comportamento di prima del
27/09/2026 (nome `guida-<slug>.jpg`, rng `cover:<slug>`, layout scelto a caso).
Così le 40 cover già pubblicate restano valide byte per byte e il sito non
cambia: le varianti 2+ sono file nuovi.

Sul perché della `foto:` nel frontmatter: il rng da solo NON bastava. La foto
usciva da `rng.choice` sulla cartella degli sfondi della nicchia, quindi la
scelta dipendeva da quanti file ci erano: aggiungere le foto per le 7 guide
nuove ha spostato la scelta di 37 guide su 40 (misurato il 27/09/2026).
Ora ogni guida porta `foto: <file>.jpg` nel frontmatter e la scelta è ferma:
le cover si possono rigenerare per sempre senza che cambi la foto.

Uso:
  python3 tools/build_cover_guide.py                  # solo mancanti/aggiornate
  tools/build_cover_guide.py --force                  # rigenera tutte
  tools/build_cover_guide.py --varianti 6              # + 5 varianti per guida
  tools/build_cover_guide.py --registra-sfondi --force  # fissa la foto mancante
Di solito la chiama tools/routine.py prima del build del sito.
NB: serve PIL + assets/ (fonts e foto) → gira in locale, non in CI.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "content" / "guide"
OUT = ROOT / "site" / "covers"
NICCHIA = {"casa": "casa", "cibo": "cibo", "fin": "finanza", "par": "parenting"}

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
import immagini  # noqa: E402
from build_guide import _parse  # noqa: E402


def _scrive_foto(src: Path, foto: str) -> bool:
    """Scrive `foto: <file>` nel frontmatter. True se il file è cambiato.

    Tiene la chiave subito dopo `descrizione` così il frontmatter resta
    leggibile; se il frontmatter non c'è non lo invento (una guida senza
    frontmatter non è una guida valida e va segnalata, non sistemata qui).
    """
    testo = src.read_text(encoding="utf-8")
    if not testo.startswith("---"):
        print(f"  ! {src.stem}: nessun frontmatter, non posso fissare la foto")
        return False
    _, fm, resto = testo.split("---", 2)
    righe = fm.rstrip("\n").split("\n")
    fuori = [i for i, l in enumerate(righe) if l.startswith("foto:")]
    for i in fuori:
        del righe[i]
    inserisco = dopo = False
    for i, l in enumerate(righe):
        if l.startswith("descrizione:"):
            dopo = True
        elif dopo and l and not l.startswith((" ", "\t", "-")):
            righe.insert(i, f"foto: {foto}")
            inserisco = True
            break
    if not inserisco:
        righe.append(f"foto: {foto}")
    nuovo = "---\n" + "\n".join(righe) + "\n---" + resto
    if nuovo == testo:
        return False
    src.write_text(nuovo, encoding="utf-8")
    return True


def _sezioni(body: str) -> list[str]:
    """Titoli delle sezioni ## della guida → checklist del layout "lista"."""
    return [r[3:].strip() for r in body.splitlines() if r.startswith("## ")][:6]


# Layout usati dalle varianti 2+. Sono quelli che `scegli_layout` ammetterebbe
# per una guida: `mockup` resta fuori perché pretende un item digitale/pod/email
# e su una guida produrrebbe un render fuorviante.
LAYOUT_VARIANTE = ("fullbleed", "split", "lista", "collage")


def _pin_di(meta: dict, v: int) -> dict:
    """Il pin v (1-based) dichiarato nel frontmatter, o un dizionario vuoto."""
    pins = meta.get("pin") or []
    if isinstance(pins, list) and 1 <= v <= len(pins) and isinstance(pins[v - 1], dict):
        return pins[v - 1]
    return {}


def _nome_cover(slug: str, v: int) -> str:
    """La variante 1 mantiene il nome di sempre, così il sito non cambia."""
    return f"guida-{slug}.jpg" if v == 1 else f"guida-{slug}-v{v}.jpg"


def _genera_una(src: Path, meta: dict, body: str, cfg: dict, v: int) -> Path:
    """Disegna la variante v della cover di una guida. Naming deterministico."""
    slug = src.stem
    # La variante 1 conserva il rng di prima (cover:<slug>): le 40 cover già
    # pubblicate restano byte per byte identiche. Dalla 2 in poi il seme
    # include la variante, così ogni pin ha una grafica sua.
    rng = random.Random(f"cover:{slug}" if v == 1 else f"cover:{slug}:v{v}")
    pin = _pin_di(meta, v)
    titolo_pin = str(pin.get("t") or meta.get("titolo", slug))
    item = {"id": slug, "titolo": titolo_pin, "kw": meta.get("kw") or []}
    if meta.get("foto"):
        item["foto"] = str(meta["foto"])  # foto fermata: non cambia al rigenerare
    if v > 1:
        # forzo il layout: è la variante visiva della cover. Senza, il rng
        # potrebbe scegliere lo stesso layout della v1 e Pinterest la
        # deduplicerebbe.
        item["layout"] = LAYOUT_VARIANTE[(v - 2) % len(LAYOUT_VARIANTE)]
    testo = {
        "titolo": titolo_pin,
        "descrizione": str(pin.get("d") or meta.get("descrizione", "")),
        "overlay": titolo_pin,
        "sottotitolo": str(meta.get("board", "")),
        "passi": _sezioni(body),
    }
    png, _ = immagini.genera_immagine(item, testo, cfg, rng)
    dst = OUT / _nome_cover(slug, v)
    with Image.open(png) as im:
        im.convert("RGB").save(dst, "JPEG", quality=88, optimize=True)
    return dst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--varianti", type=int, default=1, metavar="N",
                    help="genera N cover per guida (1 = solo quella di sempre, "
                         "6 = quella più 5 varianti per il volume)")
    ap.add_argument("--registra-sfondi", action="store_true",
                    help="scrive foto: nel frontmatter delle guide che non l'hanno "
                         "(da usare con --force: fissa la scelta attuale)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    n_var = max(1, args.varianti)
    fatte, saltate, fissate = 0, 0, 0
    for src in sorted(SRC.glob("*.md")):
        slug = src.stem
        meta, body = _parse(src)
        nid = NICCHIA.get(slug.split("-")[0], slug.split("-")[0])
        cfg_p = ROOT / "config" / "nicchie" / f"{nid}.yaml"
        if not cfg_p.exists():
            print(f"  ? {slug}: nicchia '{nid}' sconosciuta, salto")
            continue
        cfg = yaml.safe_load(cfg_p.read_text(encoding="utf-8"))
        for v in range(1, n_var + 1):
            dst = OUT / _nome_cover(slug, v)
            if (not args.force and v == 1 and dst.exists()
                    and dst.stat().st_mtime >= src.stat().st_mtime):
                saltate += 1
                continue
            _genera_una(src, meta, body, cfg, v)
            fatte += 1
            print(f"  ✓ {dst.name}")
        if args.registra_sfondi and not meta.get("foto"):
            scelta = immagini.sfondi_scelti().get(slug)
            if scelta and _scrive_foto(src, scelta):
                fissate += 1
    msg = f"cover guide: {fatte} create, {saltate} già aggiornate"
    if n_var > 1:
        msg += f" ({n_var} varianti per guida)"
    if fissate:
        msg += f", {fissate} sfondi fissati nel frontmatter"
    print(msg)
    if args.registra_sfondi and fissate:
        print("  NB: le guide toccate hanno il mtime più nuovo delle cover → il prossimo")
        print("      build le rigenera. Senza --force è un solo giro.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
