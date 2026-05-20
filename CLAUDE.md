# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run (uv gère l'env automatiquement)
uv run python app.py    # auto-selects a free port between 5000–5010

# Ajouter une dépendance
uv add <package>

# Setup manuel (si besoin sans uv)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

No test suite, no linter configured.

## Architecture

Single-file Flask backend (`app.py`) + vanilla JS/CSS frontend (`templates/index.html`). No build step, no JS framework. SQLite database (`calendrier.db`) auto-initialized on first run via `init_db()`.

### Calendar system

The Rectitude calendar uses a custom system:
- 12 months of 30 days each (`Ordium` → `Finalis`)
- Month 13 = "Jours du Silence" (5 regular days + 1 "Jour Fantôme" for leap years)
- **Year offset**: An 0 = Gregorian year 2413. Internal `an` field stores offset from 2413.
- **Month 13 mapping**: Silence days 1–6 map to Gregorian Dec 26–31 of the same year. Day 1 of the next year wraps to Jan 1 of `year + 1`.
- Events with `an = NULL` and `is_annual = 1` recur every year regardless of `an`.

The functions `timeline_date_from_event` and `map_timeline_date_to_internal` in `app.py` handle the bidirectional conversion between internal (an, month, day) and Gregorian (YYYY-MM-DD).

### DB helpers

Three thin wrappers used throughout:
- `qall(sql, args)` → list of dicts
- `qone(sql, args)` → dict or None
- `run(sql, args)` → lastrowid (auto-commits)

### Migrations

Schema changes are applied inline in `init_db()` using `PRAGMA table_info` + `ALTER TABLE`. Follow this pattern for new column additions.

### Event recurrence

`_event_matches(event, an, month)` evaluates whether an event is visible for a given year/month. Supported values for the `recurrence` column: `none`, `annual`, `monthly`, `decadal`, `every_n_years`. The `recur_n` column stores the interval for `decadal`/`every_n_years`.

### Import/export

Two CSV formats are supported side-by-side for events, entities, and relations:
- **Native format**: columns like `name`, `month`, `day`, `an`, `faction`, `recurrence`
- **Timeline format** (Aeon-compatible): columns `Title`, `Start Date`, `End Date`, `Type`, `Tags`, `Calendar` — dates are Gregorian YYYY-MM-DD, reverse-converted to internal format on import

Import endpoints accept both BOM-encoded UTF-8 and plain UTF-8.

### Factions

Six built-in factions seeded at startup (CGU, Harmonie Synthétique, Dark Umbrae, Résistance, Pureté Humaine, Illuminés). Each faction carries `border_color`, `bg_color`, `text_color` used directly in the frontend for card styling.

### Frontend views

`templates/index.html` implements all views in a single page (no routing library):
- **Calendrier** — month grid with decade rows (10 days each), sidebar with events for selected day
- **Timeline** — scrollable axis or list mode, with range selectors (day/month/year/era)
- **Réseau** — entity/relation graph with periods panel
- **Factions** — faction manager
- **Mois / Silence** — month and Silence day editors

Theme toggle (dark/light) is implemented via `body.light` CSS class.
