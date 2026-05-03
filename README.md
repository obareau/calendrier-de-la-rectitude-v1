# Calendrier de la Rectitude

Application Flask de gestion du calendrier interne de la Rectitude.

## Fonctionnalités

- Édition des mois, des jours du silence, des factions et des événements
- Vue calendrier avec navigation par mois et sélection de jour
- Timeline historique et tableau par faction
- Création, modification, duplication et suppression d'événements
- Export PDF
- Export et import CSV d'événements
- Transition calendrier : grégorien avant le 1er janvier 2413, Rectitude après le 31 décembre 2412
- Export et import Timeline CSV compatible, adapté au calendrier de la Rectitude
- Pages `À propos` et `Changelog`
- Pas d’authentification pour l’instant

## Installation

1. Créez un environnement Python (recommandé)
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Installez les dépendances
   ```bash
   python3 -m pip install -r requirements.txt
   ```

## Lancement

```bash
python3 app.py
```

Ouvrez ensuite `http://127.0.0.1:5000`.

## Structure

- `app.py` : backend Flask + API
- `templates/` : interface et pages d’information
- `calendrier.db` : base SQLite générée automatiquement
- `README.md`, `ABOUT.md`, `CHANGELOG.md`

## Git

Initialisez un dépôt local puis créez un dépôt GitHub distant si besoin :

```bash
git init
git add .
git commit -m "Initial commit"
```

Avec GitHub CLI :

```bash
gh repo create
```
