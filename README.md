# Calendrier de la Rectitude

> *"Le temps ne s'écoule pas. Il obéit."*

Application Flask de gestion du calendrier interne de la Rectitude — un système temporel sur mesure pour un univers de gouvernance totalitaire, de rituels et de factions en conflit.

---

## Aperçu

La Rectitude n'utilise pas le calendrier grégorien. Son système commence à l'**An 0** (équivalent 2413 après J.-C.) et s'organise en **12 mois de 30 jours**, complétés par les **Jours du Silence** — 5 jours rituels hors-calendrier, plus un *Jour Fantôme* les années bissextiles, officiellement nié.

Cette application permet de naviguer, éditer et exporter la chronologie de cet univers.

---

## Fonctionnalités

- **Vue calendrier** — navigation mois par mois avec affichage des événements par jour
- **Timeline** — axe chronologique scrollable en mode axe ou liste, avec sélection de plage (jour / mois / année / ère)
- **Réseau** — graphe des entités (personnages, lieux, factions) et de leurs relations, avec gestion des périodes
- **Événements** — création, modification, duplication, récurrence (`annual`, `monthly`, `decadal`, `every_n_years`)
- **Factions** — 6 factions pré-configurées (CGU, Harmonie Synthétique, Dark Umbrae, Résistance, Pureté Humaine, Illuminés)
- **Import / Export CSV** — formats natif Rectitude et Timeline (compatible Aeon)
- **Export PDF** — impression du calendrier mensuel
- **Thème clair / sombre** — bascule intégrée

---

## Installation

**Avec [uv](https://github.com/astral-sh/uv) (recommandé)**

```bash
git clone https://github.com/obareau/calendrier-de-la-rectitude-v1.git
cd calendrier-de-la-rectitude-v1
uv run python app.py
```

**Sans uv**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

Ouvrez ensuite `http://127.0.0.1:5000`.  
Le port est sélectionné automatiquement entre 5000 et 5010.  
La base de données `calendrier.db` est créée automatiquement au premier lancement.

---

## Système calendaire

| Élément | Détail |
|---|---|
| Mois | 12 mois × 30 jours (`Ordium` → `Finalis`) |
| Saisons | Glacies Disciplinae · Aetheria · Chronos Lux · Ferrum Tenebris |
| Jours du Silence | Mois 13 — 5 jours rituels + 1 Jour Fantôme (bissextile) |
| Année de référence | An 0 = 2413 après J.-C. |
| Avant l'An 0 | Dates affichées selon le calendrier grégorien |

---

## Stack

- **Backend** — Python 3.13, Flask 3, SQLite
- **Frontend** — Vanilla JS + CSS (aucune dépendance externe)
- **Gestion des dépendances** — [uv](https://github.com/astral-sh/uv)

---

## Structure

```
app.py              # backend Flask + API REST + init DB
templates/
  index.html        # interface complète (toutes vues)
  about.html
  changelog.html
calendrier.db       # base SQLite (générée au premier lancement)
pyproject.toml      # dépendances uv
```

---

## Pages

| URL | Description |
|---|---|
| `/` | Interface principale |
| `/about` | À propos du projet |
| `/changelog` | Journal des modifications |
