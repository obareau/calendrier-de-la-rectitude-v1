from flask import Flask, jsonify, request, render_template, g
import csv
import io
import json
import os
import socket
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

app = Flask(__name__)
DB      = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'calendrier.db')
VERSION = "1.5.0"

# ── Atlas bridge ────────────────────────────────────────────────────────────────
# Chronos est garant du temps ; l'Atlas est garant de la cohérence (graphe + lore).
# Connexion en lecture live via l'API HTTP de l'Atlas, avec cache court + fallback
# gracieux : si l'Atlas est éteint, Chronos continue d'afficher ses propres événements.
ATLAS_URL = os.environ.get('ATLAS_URL', 'http://localhost:5557').rstrip('/')
ATLAS_TTL = 45  # secondes
_atlas_cache = {}

def _atlas_get(path):
    """GET sur l'API Atlas avec cache mémoire (ATLAS_TTL) et fallback None si hors ligne."""
    now = time.time()
    hit = _atlas_cache.get(path)
    if hit and now - hit[0] < ATLAS_TTL:
        return hit[1]
    try:
        with urllib.request.urlopen(ATLAS_URL + path, timeout=3) as r:
            data = json.loads(r.read().decode('utf-8'))
        _atlas_cache[path] = (now, data)
        return data
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None

# ── DB helpers ────────────────────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db: db.close()

def qall(sql, args=()):
    return [dict(r) for r in get_db().execute(sql, args).fetchall()]

def qone(sql, args=()):
    r = get_db().execute(sql, args).fetchone()
    return dict(r) if r else None

def run(sql, args=()):
    cur = get_db().execute(sql, args)
    get_db().commit()
    return cur.lastrowid


def resolve_month(value):
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    if v.isdigit():
        return int(v)
    for m in qall("SELECT num,name,abbr FROM months"):
        if v.lower() in {str(m['num']).lower(), m['name'].lower(), (m['abbr'] or '').lower()}:
            return m['num']
    return None


def resolve_faction(value):
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    if v.isdigit():
        if qone("SELECT id FROM factions WHERE id=?", (int(v),)):
            return int(v)
    row = qone("SELECT id FROM factions WHERE lower(name)=?", (v.lower(),))
    return row['id'] if row else None


def resolve_entity(value):
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    if v.isdigit():
        if qone("SELECT id FROM entities WHERE id=?", (int(v),)):
            return int(v)
    row = qone("SELECT id FROM entities WHERE lower(name)=?", (v.lower(),))
    return row['id'] if row else None


def timeline_date_from_event(e):
    year = 2413 + (e['an'] if e['an'] is not None else 0)
    if e['month'] == 13:
        day = e['day']
        mapped = 25 + day
        if mapped <= 31:
            month = 12
            day_val = mapped
        else:
            month = 1
            day_val = mapped - 31
            year += 1
    else:
        month = e['month']
        day_val = e['day']
    return f"{year:04d}-{month:02d}-{day_val:02d}"


def parse_timeline_date(value):
    if not value:
        return None
    try:
        parts = value.strip().split('-')
        if len(parts) != 3:
            return None
        y, m, d = map(int, parts)
        return y, m, d
    except ValueError:
        return None


def map_timeline_date_to_internal(year, month, day):
    if month == 12 and 26 <= day <= 31:
        return year - 2413, 13, day - 25
    return year - 2413, month, day

# ── Init ──────────────────────────────────────────────────────────────────────

def init_db():
    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS factions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT    NOT NULL UNIQUE,
                border_color TEXT    NOT NULL DEFAULT '#6b7280',
                bg_color     TEXT    NOT NULL DEFAULT 'rgba(31,41,55,0.4)',
                text_color   TEXT    NOT NULL DEFAULT '#d1d5db'
            );
            CREATE TABLE IF NOT EXISTS months (
                num    INTEGER PRIMARY KEY,
                name   TEXT NOT NULL,
                abbr   TEXT NOT NULL,
                season TEXT
            );
            CREATE TABLE IF NOT EXISTS silence_days (
                num   INTEGER PRIMARY KEY,
                name  TEXT NOT NULL,
                sub   TEXT NOT NULL DEFAULT '',
                fantome INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                an           INTEGER,
                month        INTEGER NOT NULL,
                day          INTEGER NOT NULL,
                name         TEXT    NOT NULL,
                description  TEXT,
                is_annual    INTEGER NOT NULL DEFAULT 0,
                recurrence   TEXT    NOT NULL DEFAULT 'none',
                recur_n      INTEGER,
                faction_id   INTEGER REFERENCES factions(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS entities (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL UNIQUE,
                entity_type  TEXT NOT NULL,
                description  TEXT,
                faction_id   INTEGER REFERENCES factions(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS entity_relations (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id         INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                target_id         INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                relation_alignment TEXT NOT NULL DEFAULT 'neutral',
                relation_type     TEXT NOT NULL DEFAULT 'neutral',
                description       TEXT
            );
            CREATE TABLE IF NOT EXISTS periods (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL,
                description  TEXT,
                start_an     INTEGER,
                start_month  INTEGER NOT NULL,
                start_day    INTEGER NOT NULL,
                end_an       INTEGER,
                end_month    INTEGER NOT NULL,
                end_day      INTEGER NOT NULL
            );
        """)

        # ── Migrate: add recurrence columns if missing ──
        cols = [r[1] for r in db.execute("PRAGMA table_info(events)").fetchall()]
        if 'recurrence' not in cols:
            db.execute("ALTER TABLE events ADD COLUMN recurrence TEXT NOT NULL DEFAULT 'none'")
        if 'recur_n' not in cols:
            db.execute("ALTER TABLE events ADD COLUMN recur_n INTEGER")
        # ── Migrate: Atlas link columns (slug d'entité + relation miroir) ──
        if 'atlas_entity' not in cols:
            db.execute("ALTER TABLE events ADD COLUMN atlas_entity TEXT")
        if 'atlas_relation_id' not in cols:
            db.execute("ALTER TABLE events ADD COLUMN atlas_relation_id INTEGER")

        # ── Factions ──
        db.executemany(
            "INSERT OR IGNORE INTO factions (name,border_color,bg_color,text_color) VALUES (?,?,?,?)",
            [
                ('CGU',                  '#dc2626', 'rgba(127,29,29,0.25)',  '#fca5a5'),
                ('Harmonie Synthétique', '#9333ea', 'rgba(88,28,135,0.25)', '#d8b4fe'),
                ('Dark Umbrae',          '#6b7280', 'rgba(31,41,55,0.5)',   '#d1d5db'),
                ('Résistance',           '#16a34a', 'rgba(20,83,45,0.25)',  '#86efac'),
                ('Pureté Humaine',       '#3b82f6', 'rgba(30,58,95,0.25)',  '#93c5fd'),
                ('Illuminés',            '#f59e0b', 'rgba(61,44,0,0.25)',   '#fcd34d'),
            ]
        )

        # ── Months ──
        db.executemany("INSERT OR IGNORE INTO months VALUES (?,?,?,?)", [
            (1,  'Ordium',           'ORD', 'Glacies Disciplinae'),
            (2,  'Fervor',           'FER', 'Glacies Disciplinae'),
            (3,  'Laboris',          'LAB', 'Glacies Disciplinae'),
            (4,  'Prudium',          'PRU', 'Aetheria'),
            (5,  'Valoris',          'VAL', 'Aetheria'),
            (6,  'Constium',         'CON', 'Aetheria'),
            (7,  'Septium',          'SEP', 'Chronos Lux'),
            (8,  'Servium',          'SRV', 'Chronos Lux'),
            (9,  'Fortium',          'FOR', 'Chronos Lux'),
            (10, 'Decorum',          'DEC', 'Ferrum Tenebris'),
            (11, 'Rectium',          'REC', 'Ferrum Tenebris'),
            (12, 'Finalis',          'FIN', 'Ferrum Tenebris'),
            (13, 'Jours du Silence', 'SIL', None),
        ])

        # ── Silence days ──
        db.executemany("INSERT OR IGNORE INTO silence_days (num,name,sub,fantome) VALUES (?,?,?,?)", [
            (1, 'Jour de la Mémoire',    'Commémoration des fondateurs',          0),
            (2, 'Jour du Bilan',          'Autocritique publique obligatoire',      0),
            (3, 'Jour de la Rectitude',   'Renouvellement des serments',            0),
            (4, 'Jour du Silence absolu', '24h sans parole — imposé',              0),
            (5, 'Jour du Retour',         "Retour à l'ordre",                       0),
            (6, 'Jour Fantôme',           'Nié officiellement — bissextile',        1),
        ])

        # ── Events (seed only once) ──
        if db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0:
            fac = {r['name']: r['id'] for r in db.execute("SELECT id,name FROM factions")}
            db.executemany(
                "INSERT INTO events (an,month,day,name,description,is_annual,recurrence,faction_id) VALUES (?,?,?,?,?,?,?,?)",
                [
                    (None,1, 1,  "Jour de l'Ordium",        "Premier jour de l'an — parade de la Rectitude",                  1,'annual',fac['CGU']),
                    (None,6, 15, "Journée de l'Harmonie",   "Mi-année — cérémonie sonique de l'Harmonie Synthétique",         1,'annual',fac['Harmonie Synthétique']),
                    (None,11,1,  "Fête de la Rectitude",    "Apogée idéologique — purges rituelles",                          1,'annual',fac['CGU']),
                    (None,12,30, "Nuit de Finalis",          "Dernier jour avant le Silence — nuit des règlements de comptes", 1,'annual',fac['Dark Umbrae']),
                    (0,  1, 1,  "Jour de la Fondation",     "Fondation officielle du C.G.U. — An 0",                          0,'none',  fac['CGU']),
                    (2,  2, 1,  "Effacement d'Unit-734",    "Effacement d'Unit-734 par la Rectitude",                         0,'none',  fac['CGU']),
                    (390,7, 1,  "Programme Homo Mecanicus", "Lancement du programme de fusion humains-machines",               0,'none',  fac['CGU']),
                    (402,4, 1,  "Union Zoe × H.M.",         "Début de la lignée hybride — union avec l'Homo Mechanicus",      0,'none',  fac['Résistance']),
                    (421,12,30, "Nuit de la Capture",       "Capture de Joy par la Rectitude lors d'une opération de sabotage",0,'none', fac['Résistance']),
                    (422,1, 3,  "Jour de Joy",               "Mort physique de Joy — date sacrée de la résistance",            0,'none',  fac['Résistance']),
                    (450,1, 1,  "Réactivation NOVA-7",      "Réactivation partielle de NOVA-7 pour conseiller les renégats",   0,'none',  fac['Résistance']),
                    (452,1, 10, "Révélation L1L1TH",        "Révélation sur L1L1TH et le Code Originel",                      0,'none',  fac['Résistance']),
                    (455,1, 1,  "Confrontation Finale",     "Confrontation finale entre la C.G.U. et les rebelles",            0,'none',  fac['CGU']),
                ]
            )
        db.commit()

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/version')
def api_version():
    return jsonify({'version': VERSION})

# ── Atlas proxy (lecture) ───────────────────────────────────────────────────────

@app.route('/api/atlas/entities')
def api_atlas_entities():
    """Entités du graphe Atlas (personnages, factions, lieux…) pour lier un événement."""
    g = _atlas_get('/api/graph')
    if g is None:
        return jsonify({'online': False, 'entities': []})
    ents = [
        {'id': n.get('id'), 'label': n.get('label'),
         'category': n.get('category'), 'subcat': n.get('subcat')}
        for n in g.get('nodes', [])
    ]
    ents.sort(key=lambda e: (e['category'] or '', (e['label'] or '').lower()))
    return jsonify({'online': True, 'entities': ents})

@app.route('/api/atlas/timeline')
def api_atlas_timeline():
    """Relations datées de l'Atlas (`since`) + indice de certitude (metadata.since_confidence).

    Dérivé de /api/graph (qui porte les métadonnées) plutôt que de /api/timeline.
    """
    g = _atlas_get('/api/graph')
    if g is None:
        return jsonify({'online': False, 'events': []})
    labels = {n.get('id'): n.get('label') for n in g.get('nodes', [])}
    out = []
    for r in g.get('relations', []):
        since = (r.get('since') or 'An0')
        try:
            an = int(since.replace('An', ''))
        except ValueError:
            an = 0
        out.append({
            'id': r.get('id'), 'an': an, 'since': since, 'type': r.get('rel_type'),
            'source': r.get('source'), 'source_label': labels.get(r.get('source'), r.get('source')),
            'target': r.get('target'), 'target_label': labels.get(r.get('target'), r.get('target')),
            'confidence': (r.get('metadata') or {}).get('since_confidence'),
        })
    return jsonify({'online': True, 'events': out})

@app.route('/api/atlas/lore/<slug>')
def api_atlas_lore(slug):
    """Extrait de lore d'une entité, servi depuis le vault robotariis-writing via l'Atlas."""
    v = _atlas_get('/api/vault/' + urllib.parse.quote(slug))
    if v is None:
        return jsonify({'online': False})
    return jsonify({'online': True, **v})

@app.route('/api/atlas/health')
def api_atlas_health():
    """Santé/cohérence du graphe Atlas (contradictions, orphelins, totaux)."""
    s = _atlas_get('/api/stats')
    if s is None:
        return jsonify({'online': False})
    return jsonify({'online': True, 'health': s.get('health', {}),
                    'totals': s.get('totals', {}), 'factions': s.get('factions', [])})

@app.route('/api/atlas/node/<slug>')
def api_atlas_node(slug):
    """Détail d'une entité + toutes ses relations (pour la vue Destinée / Les Parques)."""
    g = _atlas_get('/api/graph')
    if g is None:
        return jsonify({'online': False})
    nodes = {n['id']: n for n in g.get('nodes', [])}
    rels = []
    for r in g.get('relations', []):
        if r.get('source') == slug or r.get('target') == slug:
            other = r['target'] if r['source'] == slug else r['source']
            since = r.get('since') or 'An0'
            try:
                an = int(since.replace('An', ''))
            except ValueError:
                an = 0
            rels.append({'other': other, 'other_label': nodes.get(other, {}).get('label', other),
                         'rel_type': r.get('rel_type'), 'direction': 'out' if r['source'] == slug else 'in',
                         'since': since, 'an': an})
    return jsonify({'online': True, 'node': nodes.get(slug), 'relations': rels})

@app.route('/api/atlas/tensions')
def api_atlas_tensions():
    """Tensions inférées entre factions/entités (alliance/conflit) — pour la cohérence."""
    t = _atlas_get('/api/tensions')
    if t is None:
        return jsonify({'online': False, 'tensions': []})
    return jsonify({'online': True, 'tensions': t})

_LORE_TEMPORAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lore_temporal.json')

@app.route('/api/lore-temporal')
def api_lore_temporal():
    """Curation temporelle du lore (durées de vie + relations datées) pour la cohérence.

    Vérité du temps côté Chronos ; sert de base au moteur d'impossibilités temporelles.
    """
    try:
        with open(_LORE_TEMPORAL, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return jsonify({'entities': {}, 'relations': []})
    return jsonify({'entities': data.get('entities', {}), 'relations': data.get('relations', [])})

# MONTHS
@app.route('/api/months')
def api_months():
    return jsonify(qall("SELECT * FROM months ORDER BY num"))

@app.route('/api/months/<int:num>', methods=['PUT'])
def api_update_month(num):
    d = request.json
    run("UPDATE months SET name=?,abbr=?,season=? WHERE num=?",
        (d['name'], d['abbr'], d.get('season') or None, num))
    return jsonify({'ok': True})

# SILENCE DAYS
@app.route('/api/silence')
def api_silence():
    return jsonify(qall("SELECT * FROM silence_days ORDER BY num"))

@app.route('/api/silence/<int:num>', methods=['PUT'])
def api_update_silence(num):
    d = request.json
    run("UPDATE silence_days SET name=?,sub=? WHERE num=?",
        (d['name'], d.get('sub',''), num))
    return jsonify(qone("SELECT * FROM silence_days WHERE num=?", (num,)))

# FACTIONS
@app.route('/api/factions')
def api_factions():
    return jsonify(qall("SELECT * FROM factions ORDER BY id"))

@app.route('/api/factions', methods=['POST'])
def api_create_faction():
    d = request.json
    fid = run("INSERT INTO factions (name,border_color,bg_color,text_color) VALUES (?,?,?,?)",
              (d['name'], d.get('border_color','#6b7280'),
               d.get('bg_color','rgba(31,41,55,0.4)'), d.get('text_color','#d1d5db')))
    return jsonify(qone("SELECT * FROM factions WHERE id=?", (fid,))), 201

@app.route('/api/factions/<int:fid>', methods=['PUT'])
def api_update_faction(fid):
    d = request.json
    run("UPDATE factions SET name=?,border_color=?,bg_color=?,text_color=? WHERE id=?",
        (d['name'], d['border_color'], d['bg_color'], d['text_color'], fid))
    return jsonify({'ok': True})

@app.route('/api/factions/<int:fid>', methods=['DELETE'])
def api_delete_faction(fid):
    run("DELETE FROM factions WHERE id=?", (fid,))
    return jsonify({'ok': True})

# EVENTS
_EVT_SELECT = """
    SELECT e.*, f.name AS faction_name, f.border_color, f.bg_color, f.text_color
    FROM events e LEFT JOIN factions f ON e.faction_id = f.id
"""

def _event_matches(e, an, month):
    """Check if an event is visible for a given an/month, accounting for recurrence."""
    if e['month'] != month and e['recurrence'] != 'monthly':
        return False
    r = e['recurrence'] or 'none'
    if r == 'annual' or e['is_annual']:
        return True
    if r == 'none':
        return e['an'] == an
    if r == 'decadal':
        n = e['recur_n'] or 10
        return e['an'] is not None and (an - e['an']) % n == 0 and an >= e['an']
    if r == 'monthly':
        return True
    if r == 'every_n_years':
        n = e['recur_n'] or 1
        return e['an'] is not None and (an - e['an']) % n == 0 and an >= e['an']
    return e['an'] == an

@app.route('/api/events/all')
def api_events_all():
    """All events unfiltered — for timeline and faction views."""
    rows = qall(_EVT_SELECT + " ORDER BY e.an, e.month, e.day")
    return jsonify(rows)

@app.route('/api/events/export')
def api_events_export():
    rows = qall(_EVT_SELECT + " ORDER BY e.an, e.month, e.day")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['name', 'description', 'faction', 'recurrence', 'recur_n', 'an', 'month', 'day'])
    for e in rows:
        writer.writerow([
            e['name'],
            e['description'] or '',
            e['faction_name'] or '',
            e['recurrence'] or 'none',
            e['recur_n'] or '',
            '' if e['an'] is None else e['an'],
            e['month'],
            e['day'],
        ])
    return app.response_class(output.getvalue(), mimetype='text/csv',
                               headers={'Content-Disposition': 'attachment; filename=calendrier-rectitude-events.csv'})

@app.route('/api/events/export-timeline')
def api_events_export_timeline():
    rows = qall(_EVT_SELECT + " ORDER BY e.an, e.month, e.day")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Title', 'Start Date', 'End Date', 'Description', 'Type', 'Tags', 'Calendar'])
    for e in rows:
        writer.writerow([
            e['name'],
            timeline_date_from_event(e),
            timeline_date_from_event(e),
            e['description'] or '',
            e['faction_name'] or 'Rectitude Event',
            ('recurrence:' + (e['recurrence'] or 'none')) if e['recurrence'] else 'none',
            'Rectitude'
        ])
    return app.response_class(output.getvalue(), mimetype='text/csv',
                               headers={'Content-Disposition': 'attachment; filename=calendrier-rectitude-timeline.csv'})

@app.route('/api/events/import', methods=['POST'])
def api_events_import():
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'Aucun fichier CSV reçu'}), 400
    text = file.stream.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    imported = 0
    errors = []
    for idx, raw in enumerate(reader, start=1):
        row = {k.strip().lower(): (v or '').strip() for k, v in raw.items() if k}
        name = row.get('name', '')
        if not name:
            errors.append(f'Ligne {idx}: nom manquant')
            continue
        month = resolve_month(row.get('month'))
        day = int(row.get('day') or 0)
        if month is None or day < 1:
            errors.append(f'Ligne {idx}: mois ou jour invalide')
            continue
        recurrence = (row.get('recurrence') or 'none').lower()
        if recurrence not in ('none', 'annual', 'monthly', 'decadal', 'every_n_years'):
            recurrence = 'none'
        recur_n = int(row.get('recur_n') or 0) or None
        an = None if recurrence == 'annual' or row.get('an', '') == '' else int(row.get('an'))
        if recurrence == 'every_n_years' and an is None:
            errors.append(f'Ligne {idx}: année requise pour recurrence every_n_years')
            continue
        is_annual = 1 if recurrence == 'annual' else 0
        faction_id = resolve_faction(row.get('faction') or row.get('faction_id'))
        get_db().execute(
            "INSERT INTO events (an,month,day,name,description,is_annual,recurrence,recur_n,faction_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (an, month, day, name, row.get('description') or None,
             is_annual, recurrence, recur_n, faction_id)
        )
        imported += 1
    get_db().commit()
    return jsonify({'imported': imported, 'errors': errors})

@app.route('/api/entities/import', methods=['POST'])
def api_entities_import():
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'Aucun fichier CSV reçu'}), 400
    text = file.stream.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    imported = 0
    errors = []
    for idx, raw in enumerate(reader, start=1):
        row = {k.strip().lower(): (v or '').strip() for k, v in raw.items() if k}
        name = row.get('name', '')
        if not name:
            errors.append(f'Ligne {idx}: nom manquant')
            continue
        entity_type = row.get('entity_type') or row.get('type') or row.get('category') or 'Personnage'
        faction_id = resolve_faction(row.get('faction') or row.get('faction_id'))
        run(
            "INSERT INTO entities (name,entity_type,description,faction_id) VALUES (?,?,?,?)",
            (name, entity_type, row.get('description') or None, faction_id)
        )
        imported += 1
    return jsonify({'imported': imported, 'errors': errors})

@app.route('/api/entities/import-timeline', methods=['POST'])
def api_entities_import_timeline():
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'Aucun fichier CSV reçu'}), 400
    text = file.stream.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    imported = 0
    errors = []
    for idx, raw in enumerate(reader, start=1):
        row = {k.strip().lower(): (v or '').strip() for k, v in raw.items() if k}
        name = row.get('title') or row.get('name')
        if not name:
            errors.append(f'Ligne {idx}: titre manquant')
            continue
        entity_type = row.get('type') or row.get('entity_type') or 'Personnage'
        faction_id = resolve_faction(row.get('tags') or row.get('faction') or row.get('series'))
        run(
            "INSERT INTO entities (name,entity_type,description,faction_id) VALUES (?,?,?,?)",
            (name, entity_type, row.get('description') or None, faction_id)
        )
        imported += 1
    return jsonify({'imported': imported, 'errors': errors})

@app.route('/api/relations/import', methods=['POST'])
def api_relations_import():
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'Aucun fichier CSV reçu'}), 400
    text = file.stream.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    imported = 0
    errors = []
    for idx, raw in enumerate(reader, start=1):
        row = {k.strip().lower(): (v or '').strip() for k, v in raw.items() if k}
        source = row.get('source') or row.get('source_name')
        target = row.get('target') or row.get('target_name')
        if not source or not target:
            errors.append(f'Ligne {idx}: source ou cible manquante')
            continue
        source_id = resolve_entity(source)
        target_id = resolve_entity(target)
        if not source_id or not target_id:
            errors.append(f'Ligne {idx}: source ou cible introuvable ({source} / {target})')
            continue
        alignment = (row.get('alignment') or row.get('relation_alignment') or 'neutral').lower()
        if alignment not in ('friend', 'enemy', 'neutral'):
            alignment = 'neutral'
        relation_type = row.get('relation_type') or row.get('type') or 'neutral'
        run(
            "INSERT INTO entity_relations (source_id,target_id,relation_alignment,relation_type,description) VALUES (?,?,?,?,?)",
            (source_id, target_id, alignment, relation_type, row.get('description') or None)
        )
        imported += 1
    return jsonify({'imported': imported, 'errors': errors})

@app.route('/api/relations/import-timeline', methods=['POST'])
def api_relations_import_timeline():
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'Aucun fichier CSV reçu'}), 400
    text = file.stream.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    imported = 0
    errors = []
    for idx, raw in enumerate(reader, start=1):
        row = {k.strip().lower(): (v or '').strip() for k, v in raw.items() if k}
        title = row.get('title') or row.get('name')
        source = row.get('source') or row.get('source_name')
        target = row.get('target') or row.get('target_name')
        if not source or not target:
            if title and '→' in title:
                parts = title.split('→')
                if len(parts) == 2:
                    source = parts[0].strip(); target = parts[1].strip()
        if not source or not target:
            errors.append(f'Ligne {idx}: source ou cible introuvable pour la relation')
            continue
        source_id = resolve_entity(source)
        target_id = resolve_entity(target)
        if not source_id or not target_id:
            errors.append(f'Ligne {idx}: entité introuvable ({source} / {target})')
            continue
        alignment = (row.get('tags') or row.get('alignment') or row.get('relation_alignment') or 'neutral').lower()
        if alignment not in ('friend', 'enemy', 'neutral'):
            alignment = 'neutral'
        relation_type = row.get('type') or row.get('relation_type') or 'neutral'
        run(
            "INSERT INTO entity_relations (source_id,target_id,relation_alignment,relation_type,description) VALUES (?,?,?,?,?)",
            (source_id, target_id, alignment, relation_type, row.get('description') or None)
        )
        imported += 1
    return jsonify({'imported': imported, 'errors': errors})

@app.route('/api/events/import-timeline', methods=['POST'])
def api_events_import_timeline():
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'Aucun fichier CSV reçu'}), 400
    text = file.stream.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    imported = 0
    errors = []
    for idx, raw in enumerate(reader, start=1):
        row = {k.strip().lower(): (v or '').strip() for k, v in raw.items() if k}
        title = row.get('title') or row.get('name')
        start_date = row.get('start date') or row.get('startdate') or row.get('start')
        if not title or not start_date:
            errors.append(f'Ligne {idx}: titre ou date de début manquant')
            continue
        parsed = parse_timeline_date(start_date)
        if parsed is None:
            errors.append(f'Ligne {idx}: date de début invalide ({start_date})')
            continue
        an, month, day = map_timeline_date_to_internal(*parsed)
        if month is None or day < 1 or day > 30:
            errors.append(f'Ligne {idx}: date impossible ({start_date})')
            continue
        faction_id = resolve_faction(row.get('type') or row.get('tags') or row.get('series') or row.get('faction'))
        get_db().execute(
            "INSERT INTO events (an,month,day,name,description,is_annual,recurrence,recur_n,faction_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (an, month, day, title, row.get('description') or None,
             0, 'none', None, faction_id)
        )
        imported += 1
    get_db().commit()
    return jsonify({'imported': imported, 'errors': errors})

@app.route('/api/events')
def api_events():
    an    = request.args.get('an',    type=int)
    month = request.args.get('month', type=int)
    if an is not None and month is not None:
        rows = qall(_EVT_SELECT + " ORDER BY e.an, e.month, e.day")
        rows = [r for r in rows if _event_matches(r, an, month)]
    else:
        rows = qall(_EVT_SELECT + " ORDER BY e.an, e.month, e.day")
    return jsonify(rows)

@app.route('/api/events', methods=['POST'])
def api_create_event():
    d = request.json
    r = d.get('recurrence','none')
    is_annual = 1 if (d.get('is_annual') or r == 'annual') else 0
    an = None if is_annual else d.get('an')
    eid = run(
        "INSERT INTO events (an,month,day,name,description,is_annual,recurrence,recur_n,faction_id,atlas_entity,atlas_relation_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (an, d['month'], d['day'], d['name'], d.get('description'),
         is_annual, r, d.get('recur_n'), d.get('faction_id') or None,
         d.get('atlas_entity') or None, d.get('atlas_relation_id') or None)
    )
    return jsonify(qone(_EVT_SELECT + " WHERE e.id=?", (eid,))), 201

@app.route('/api/events/<int:eid>', methods=['PUT'])
def api_update_event(eid):
    d = request.json
    r = d.get('recurrence','none')
    is_annual = 1 if (d.get('is_annual') or r == 'annual') else 0
    an = None if is_annual else d.get('an')
    run("UPDATE events SET an=?,month=?,day=?,name=?,description=?,is_annual=?,recurrence=?,recur_n=?,faction_id=?,atlas_entity=?,atlas_relation_id=? WHERE id=?",
        (an, d['month'], d['day'], d['name'], d.get('description'),
         is_annual, r, d.get('recur_n'), d.get('faction_id') or None,
         d.get('atlas_entity') or None, d.get('atlas_relation_id') or None, eid))
    return jsonify(qone(_EVT_SELECT + " WHERE e.id=?", (eid,)))

@app.route('/api/events/<int:eid>', methods=['DELETE'])
def api_delete_event(eid):
    run("DELETE FROM events WHERE id=?", (eid,))
    return jsonify({'ok': True})

# ── Entities / Relations ───────────────────────────────────────────────────────

@app.route('/api/entities')
def api_entities():
    return jsonify(qall("SELECT e.*, f.name AS faction_name FROM entities e LEFT JOIN factions f ON e.faction_id = f.id ORDER BY e.entity_type, e.name"))

@app.route('/api/entities', methods=['POST'])
def api_create_entity():
    d = request.json
    eid = run(
        "INSERT INTO entities (name,entity_type,description,faction_id) VALUES (?,?,?,?)",
        (d['name'], d['entity_type'], d.get('description'), d.get('faction_id') or None)
    )
    return jsonify(qone("SELECT e.*, f.name AS faction_name FROM entities e LEFT JOIN factions f ON e.faction_id = f.id WHERE e.id=?", (eid,))), 201

@app.route('/api/entities/<int:eid>', methods=['PUT'])
def api_update_entity(eid):
    d = request.json
    run("UPDATE entities SET name=?,entity_type=?,description=?,faction_id=? WHERE id=?",
        (d['name'], d['entity_type'], d.get('description'), d.get('faction_id') or None, eid))
    return jsonify({'ok': True})

@app.route('/api/entities/<int:eid>', methods=['DELETE'])
def api_delete_entity(eid):
    run("DELETE FROM entities WHERE id=?", (eid,))
    return jsonify({'ok': True})

@app.route('/api/relations')
def api_relations():
    rows = qall(
        "SELECT r.*, s.name AS source_name, t.name AS target_name, s.entity_type AS source_type, t.entity_type AS target_type "
        "FROM entity_relations r "
        "JOIN entities s ON r.source_id = s.id "
        "JOIN entities t ON r.target_id = t.id "
        "ORDER BY r.id"
    )
    return jsonify(rows)

@app.route('/api/relations', methods=['POST'])
def api_create_relation():
    d = request.json
    rid = run(
        "INSERT INTO entity_relations (source_id,target_id,relation_alignment,relation_type,description) VALUES (?,?,?,?,?)",
        (d['source_id'], d['target_id'], d.get('relation_alignment','neutral'), d.get('relation_type','neutral'), d.get('description'))
    )
    return jsonify(qone("SELECT * FROM entity_relations WHERE id=?", (rid,))), 201

@app.route('/api/relations/<int:rid>', methods=['PUT'])
def api_update_relation(rid):
    d = request.json
    run("UPDATE entity_relations SET source_id=?,target_id=?,relation_alignment=?,relation_type=?,description=? WHERE id=?",
        (d['source_id'], d['target_id'], d.get('relation_alignment','neutral'), d.get('relation_type','neutral'), d.get('description'), rid))
    return jsonify({'ok': True})

@app.route('/api/relations/<int:rid>', methods=['DELETE'])
def api_delete_relation(rid):
    run("DELETE FROM entity_relations WHERE id=?", (rid,))
    return jsonify({'ok': True})

@app.route('/api/relations/by-entity/<int:eid>')
def api_relations_by_entity(eid):
    rows = qall(
        "SELECT r.*, s.name AS source_name, t.name AS target_name, s.entity_type AS source_type, t.entity_type AS target_type "
        "FROM entity_relations r "
        "JOIN entities s ON r.source_id = s.id "
        "JOIN entities t ON r.target_id = t.id "
        "WHERE r.source_id=? OR r.target_id=? ORDER BY r.id",
        (eid, eid)
    )
    return jsonify(rows)

# ── Periods ───────────────────────────────────────────────────────────────────

@app.route('/api/periods')
def api_periods():
    return jsonify(qall("SELECT * FROM periods ORDER BY start_an, start_month, start_day"))

@app.route('/api/periods', methods=['POST'])
def api_create_period():
    d = request.json
    pid = run(
        "INSERT INTO periods (name,description,start_an,start_month,start_day,end_an,end_month,end_day) VALUES (?,?,?,?,?,?,?,?)",
        (d['name'], d.get('description'), d.get('start_an'), d['start_month'], d['start_day'], d.get('end_an'), d['end_month'], d['end_day'])
    )
    return jsonify(qone("SELECT * FROM periods WHERE id=?", (pid,))), 201

@app.route('/api/periods/<int:pid>', methods=['PUT'])
def api_update_period(pid):
    d = request.json
    run("UPDATE periods SET name=?,description=?,start_an=?,start_month=?,start_day=?,end_an=?,end_month=?,end_day=? WHERE id=?",
        (d['name'], d.get('description'), d.get('start_an'), d['start_month'], d['start_day'], d.get('end_an'), d['end_month'], d['end_day'], pid))
    return jsonify({'ok': True})

@app.route('/api/periods/<int:pid>', methods=['DELETE'])
def api_delete_period(pid):
    run("DELETE FROM periods WHERE id=?", (pid,))
    return jsonify({'ok': True})

@app.route('/api/entities/export')
def api_entities_export():
    rows = qall("SELECT e.*, f.name AS faction_name FROM entities e LEFT JOIN factions f ON e.faction_id = f.id ORDER BY e.entity_type, e.name")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['name', 'entity_type', 'description', 'faction'])
    for e in rows:
        writer.writerow([e['name'], e['entity_type'], e['description'] or '', e['faction_name'] or ''])
    return app.response_class(output.getvalue(), mimetype='text/csv',
                               headers={'Content-Disposition': 'attachment; filename=calendrier-rectitude-entities.csv'})

@app.route('/api/entities/export-timeline')
def api_entities_export_timeline():
    rows = qall("SELECT e.*, f.name AS faction_name FROM entities e LEFT JOIN factions f ON e.faction_id = f.id ORDER BY e.entity_type, e.name")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Title', 'Start Date', 'End Date', 'Description', 'Type', 'Tags', 'Calendar'])
    for e in rows:
        writer.writerow([
            e['name'],
            '2413-01-01',
            '2413-01-01',
            e['description'] or '',
            e['entity_type'],
            e['faction_name'] or 'entity',
            'Rectitude'
        ])
    return app.response_class(output.getvalue(), mimetype='text/csv',
                               headers={'Content-Disposition': 'attachment; filename=calendrier-rectitude-entities-timeline.csv'})

@app.route('/api/relations/export')
def api_relations_export():
    rows = qall(
        "SELECT r.*, s.name AS source_name, t.name AS target_name FROM entity_relations r "
        "JOIN entities s ON r.source_id = s.id "
        "JOIN entities t ON r.target_id = t.id ORDER BY r.id"
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['source', 'target', 'alignment', 'relation_type', 'description'])
    for r in rows:
        writer.writerow([r['source_name'], r['target_name'], r['relation_alignment'], r['relation_type'], r['description'] or ''])
    return app.response_class(output.getvalue(), mimetype='text/csv',
                               headers={'Content-Disposition': 'attachment; filename=calendrier-rectitude-relations.csv'})

@app.route('/api/relations/export-timeline')
def api_relations_export_timeline():
    rows = qall(
        "SELECT r.*, s.name AS source_name, t.name AS target_name FROM entity_relations r "
        "JOIN entities s ON r.source_id = s.id "
        "JOIN entities t ON r.target_id = t.id ORDER BY r.id"
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Title', 'Start Date', 'End Date', 'Description', 'Type', 'Tags', 'Calendar'])
    for r in rows:
        writer.writerow([
            f"{r['source_name']} → {r['target_name']}",
            '2413-01-01',
            '2413-01-01',
            r['description'] or '',
            r['relation_type'],
            ','.join([r['relation_alignment'], r['relation_type']]),
            'Rectitude'
        ])
    return app.response_class(output.getvalue(), mimetype='text/csv',
                               headers={'Content-Disposition': 'attachment; filename=calendrier-rectitude-relations-timeline.csv'})

@app.route('/api/events/<int:eid>/duplicate', methods=['POST'])
def api_duplicate_event(eid):
    e = qone("SELECT * FROM events WHERE id=?", (eid,))
    if not e:
        return jsonify({'error':'not found'}), 404
    new_id = run(
        "INSERT INTO events (an,month,day,name,description,is_annual,recurrence,recur_n,faction_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (e['an'], e['month'], e['day'], e['name']+' (copie)', e['description'],
         e['is_annual'], e['recurrence'], e['recur_n'], e['faction_id'])
    )
    return jsonify(qone(_EVT_SELECT + " WHERE e.id=?", (new_id,))), 201

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/changelog')
def changelog():
    return render_template('changelog.html')

# ── Run ───────────────────────────────────────────────────────────────────────

def find_free_port(start=5000, end=5010):
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    raise RuntimeError(f'No available port between {start} and {end}')

if __name__ == '__main__':
    init_db()
    port = find_free_port(5000, 5010)
    print(f'Launching Flask on port {port}')
    app.run(debug=True, port=port)
