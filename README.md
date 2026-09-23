# pinn-site

Static hosting + landing page for the Pinterest Multi-Niche system, served with GitHub Pages → https://marylin12321.github.io/pinn-site/

## Structure

- `index.html` — "Quattro Mondi" landing (the single link used on all 4 Pinterest profiles)
- `pin/` — generated pin images (1000×1500), referenced as Media URLs in the bulk-upload CSVs

## ⚠️ Auto-generated — do not edit by hand

Everything here is published by `tools/pubblica_immagini.py`:
- the landing comes from `tools/build_landing.py` (reads the niche configs)
- the images come from `output/immagini/` after `python3 src/main.py genera`

To update: change the sources in the project, then re-run the publish script.
