"""Utilità condivise: percorsi, caricamento config, hashing, similarità testuale."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
NICHIE_DIR = CONFIG_DIR / "nicchie"
OUTPUT_DIR = ROOT / "output"
IMMAGINI_DIR = OUTPUT_DIR / "immagini"
CSV_DIR = OUTPUT_DIR / "csv"
PREVISTE_DIR = OUTPUT_DIR / "previste"
STATO_DIR = ROOT / "state"
GIORNATE_DIR = STATO_DIR / "giornate"
FONTS_DIR = ROOT / "assets" / "fonts"
SFONDI_DIR = ROOT / "assets" / "backgrounds"
MANIFEST_REALE = OUTPUT_DIR / "manifest.jsonl"
MANIFEST_DEMO = OUTPUT_DIR / "manifest_demo.jsonl"

_COLORI = {"info": "\033[36m", "ok": "\033[32m", "warn": "\033[33m", "err": "\033[31m"}
_RESET = "\033[0m"


def log(tipo: str, msg: str) -> None:
    prefisso = {"info": "·", "ok": "✓", "warn": "!", "err": "✗"}.get(tipo, "·")
    colore = _COLORI.get(tipo, "")
    print(f"{colore}{prefisso}{_RESET} {msg}")


def carica_yaml(percorso: Path) -> dict:
    with open(percorso, encoding="utf-8") as f:
        dati = yaml.safe_load(f)
    if not isinstance(dati, dict):
        raise ValueError(f"Config non valida: {percorso}")
    return dati


def sistema_cfg() -> dict:
    return carica_yaml(CONFIG_DIR / "system.yaml")


def config_nicchie() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in sorted(NICHIE_DIR.glob("*.yaml")):
        out[p.stem] = carica_yaml(p)
    return out


def config_nicchia(nid: str) -> dict:
    p = NICHIE_DIR / f"{nid}.yaml"
    if not p.exists():
        disponibili = ", ".join(sorted(config_nicchie()))
        raise SystemExit(f"Nicchia '{nid}' inesistente. Disponibili: {disponibili}")
    return carica_yaml(p)


def sha_bytes(dati: bytes) -> str:
    return hashlib.sha256(dati).hexdigest()


def sha_file(p: Path) -> str:
    return sha_bytes(p.read_bytes())


def normalizza(testo: str) -> str:
    testo = unicodedata.normalize("NFKD", testo.lower())
    testo = "".join(c for c in testo if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\s]", " ", testo)


def tokenizza(testo: str) -> list[str]:
    return [t for t in normalizza(testo).split() if len(t) > 2]


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def leggi_manifest(demo: bool = False) -> list[dict]:
    percorso = MANIFEST_DEMO if demo else MANIFEST_REALE
    if not percorso.exists():
        return []
    righe = []
    with open(percorso, encoding="utf-8") as f:
        for n, linea in enumerate(f, start=1):
            linea = linea.strip()
            if not linea:
                continue
            try:
                righe.append(json.loads(linea))
            except json.JSONDecodeError:
                log("warn", f"manifest riga {n} corrotta: saltata "
                            "(ripristina da backup se il pin serviva).")
    return righe


def appendi_manifest(riga: dict, demo: bool = False) -> None:
    percorso = MANIFEST_DEMO if demo else MANIFEST_REALE
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(percorso, "a", encoding="utf-8") as f:
        f.write(json.dumps(riga, ensure_ascii=False) + "\n")


def riscrivi_manifest(righe: list[dict], demo: bool = False) -> None:
    percorso = MANIFEST_DEMO if demo else MANIFEST_REALE
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(percorso, "w", encoding="utf-8") as f:
        for r in righe:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def luminanza(hex_colore: str) -> float:
    """Luminanza relativa (WCAG) da hex #RRGGBB."""
    h = hex_colore.lstrip("#")
    if len(h) != 6:
        return 0.5
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def f(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrasto_ok(colore1: str, colore2: str) -> bool:
    l1, l2 = sorted((luminanza(colore1), luminanza(colore2)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05) >= 4.5


def colore_su(colore_sx: str, chiaro: str, scuro: str) -> str:
    """Sceglie il testo (chiaro/scuro) con contrasto ≥4.5:1 rispetto a colore_sx."""
    return chiaro if contrasto_ok(colore_sx, chiaro) else scuro
