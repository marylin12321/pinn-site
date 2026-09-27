"""Pin sociali per i printable: cover 1000×1500 con badge 'PDF GRATIS'.

Genera covers/printable-<slug>.jpg per ogni printable in config/printable.yaml.
Usato da build_sito.py → build_cover_guide.py è per le guide, questo per i printable.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COV = ROOT / "site" / "covers"

sys.path.insert(0, str(ROOT / "tools"))
import build_printable as bp  # noqa: E402


def main() -> int:
    specs = bp._carica()
    for s in specs:
        p = COV / f"printable-{s['slug']}.jpg"
        if p.exists() and not p.stat().st_size == 0:
            print(f"  ✓ {s['slug']}: cover già presente")
            continue
        png = ROOT / "site" / "printable" / f"{s['slug']}_preview.png"
        if not png.exists():
            bp.build(s)
        r = bp.cover(s)
        print(f"  ✓ {s['slug']}: cover → {r}" if r else f"  ✗ {s['slug']}: fallita")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
