#!/usr/bin/env python3
"""Lint dei testi delle guide: refusi, alfabeti sbagliati, frasi da call center.

Non corregge: segnala file e numero di riga, così la sistemazione resta manuale
(le guide sono scritte a mano, non generate da un template).

Il frontmatter YAML non viene controllato: lì le date e i numeri sono attesi.

Uso:
  python3 tools/lint_guide.py            # esce 1 se trova problemi
  python3 tools/lint_guide.py --verbose  # elenco anche delle guide pulite
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "content" / "guide"

# alfabeti che non hanno niente a che fare con l'italiano (bug tipico dei generatori)
VIETATI: list[tuple[str, re.compile]] = [
    ("cirillico", re.compile(r"[Ѐ-ӿ]")),
    ("greco", re.compile(r"[Ͱ-Ͽ]")),
    ("cinese", re.compile(r"[一-鿿぀-ヿ]")),
    ("arabo", re.compile(r"[؀-ۿ]")),
    ("fullwidth", re.compile(r"[！-｠]")),
]

# refusi e slop tipici: (nome, regex) — solo sul corpo della guida
PATTERNI: list[tuple[str, re.compile]] = [
    ("doppio spazio", re.compile(r"\S {2,}\S")),
    ("spazio prima della punteggiatura", re.compile(r"\s+[.,;:!?]")),
    ("virgola senza spazio", re.compile(r",[^\s0-9]")),
    ("punto senza maiuscola", re.compile(r"[a-zà-ù]\.(?:\s+|\s*$)[a-zà-ù]")),
    ("apostrofo doppio", re.compile(r"''")),
    ("virgolette sbilanciate", re.compile(r"[«»“”]")),
    ("frase da call center", re.compile(
        r"\b(ti consigliamo|consigliamo di|è importante ricordare|non dimenticare di|"
        r"scopri come|approfondisci|trasforma la tua|vivi meglio|la tua casa dei sogni|"
        r"incredibile|rivoluzionari\w*|soluzione definitiva|passione per)\b", re.I)),
    ("parola troncata", re.compile(r"\b(piu|puo|cosi|perche|gia|verra|puoche)\b", re.I)),
    ("spazio finale", re.compile(r"[ \t]+$")),
    ("parola ripetuta", re.compile(r"\b(\w{4,})\s+\1\b", re.I)),
]


def _corpo(testo: str) -> list[tuple[int, str]]:
    """(numero_riga, riga) del corpo, escluso il frontmatter."""
    righe = testo.splitlines()
    if righe and righe[0].strip() == "---":
        for i in range(1, len(righe)):
            if righe[i].strip() == "---":
                return [(j + 1, righe[j]) for j in range(i + 1, len(righe))]
    return [(i + 1, r) for i, r in enumerate(righe)]


def check(verbose: bool = False) -> bool:
    """Controlla tutte le guide. Ritorna False se trova problemi."""
    problemi = 0
    guide = sorted(SRC.glob("*.md"))
    for src in guide:
        testo = src.read_text(encoding="utf-8")
        if not (testo.startswith("---") and "titolo:" in testo.split("---", 2)[1]):
            print(f"✗ {src.name}: frontmatter senza titolo")
            problemi += 1
        for n, riga in _corpo(testo):
            for nome, rx in VIETATI:
                if rx.search(riga):
                    print(f"✗ {src.name}:{n} {nome}: «{riga[:60]}»")
                    problemi += 1
            for nome, rx in PATTERNI:
                m = rx.search(riga)
                if m:
                    print(f"✗ {src.name}:{n} {nome}: …{riga[max(0, m.start()-35):m.end()+35]}…")
                    problemi += 1
        if verbose:
            print(f"· {src.name}: {len(testo.split())} parole, {testo.count('## ')} sezioni")
    if problemi:
        print(f"LINT ✗ {problemi} problemi da correggere a mano.")
        return False
    print(f"LINT ✓ {len(guide)} guide pulite.")
    return True


def main() -> int:
    return 0 if check(verbose="--verbose" in sys.argv) else 1


if __name__ == "__main__":
    raise SystemExit(main())
