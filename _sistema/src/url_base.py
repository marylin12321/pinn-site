"""Radice pubblica del sito: una sola fonte di verità per tutto il sistema.

Prima questa cosa era implementata sei volte, identica, in sei file
(build_sito, build_guide, build_feed, build_printable, export_guide_csv,
pendenze) efaceva la stessa cosa fragile:

    base.rsplit("/", 1)[0] + "/"

cioè "togli l'ultimo pezzo dell'URL" per passare da
  https://utente.github.io/pinn-site/pin   (dove stavano le immagini grezze)
a
  https://utente.github.io/pinn-site/       (radice del sito)

Una regola così dipende da un dettaglio invisibile: se `media_base_url`
avesse finito con un altro nome di cartella, o non avesse avuto nessuna
sotto-cartella, il risultato sarebbe stato un URL diverso senza che nessuno
se ne accorgesse. Il 27/09/2026 le immagini grezze hanno smesso di essere
pubblicate (pin/ = 119 MB di PNG che nessuna pagina, feed o CSV citava), e con
loro anche la sotto-cartella: la trappola rsplit non aveva più senso.

Ora la radice sta scritta per esteso in config/system.yaml:

    hosting:
      sito_pubblico: "https://marylin12321.github.io/pinn-site/"

e qui sotto c'è solo il codice per leggerla. `media_base_url` resta nei
config di nicchia per i moduli legacy (csv_export, links, verifica) e come
piano di riserva se `sito_pubblico` non fosse impostato.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Sito di riserva se config/system.yaml non dice nulla: meglio un URL che
# esiste già (la radice del repo) del silenzio.
FALLBACK = "https://example.com/pinn-site/"

NICCHIE = ("casa", "cibo", "finanza", "parenting")

_avvisato = False


def _system(root: Path) -> dict:
    p = root / "config" / "system.yaml"
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def site_base(root: Path | None = None) -> str:
    """URL del sito con slash finale, es. https://utente.github.io/pinn-site/."""
    global _avvisato
    r = root or ROOT

    sito = (_system(r).get("hosting") or {}).get("sito_pubblico")
    if sito and str(sito).strip():
        return str(sito).strip().rstrip("/") + "/"

    # Piano di riserva: il primo media_base_url non vuoto, usato così com'è.
    # Niente rsplit: se qualcuno ha ancora la sotto-cartella dentro, è un
    # refuso da correggere e va detto, non riscritto di nascosto.
    for nid in NICCHIE:
        p = r / "config" / "nicchie" / f"{nid}.yaml"
        if not p.exists():
            continue
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        b = str(cfg.get("media_base_url") or "").strip().rstrip("/")
        if b:
            if not _avvisato:
                _avvisato = True
                warnings.warn(
                    "hosting.sito_pubblico non è impostato in config/system.yaml: "
                    f"uso media_base_url di {nid}. Se finisce con una sotto-cartella "
                    "verrà fuori un URL sbagliato.",
                    stacklevel=2,
                )
            return b + "/"
    return FALLBACK


def main() -> int:
    """Stampare la radice e da dove viene: `python3 src/url_base.py`."""
    print(site_base())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
