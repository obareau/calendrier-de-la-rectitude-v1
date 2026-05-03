from flask import Flask, jsonify, request, render_template, g
import csv
import io
import os
import sqlite3

app = Flask(__name__)
DB      = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'calendrier.db')
VERSION = "1.4.0"

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
        """)

        # ── Migrate: add recurrence columns if missing ──
        cols = [r[1] for r in db.execute("PRAGMA table_info(events)").fetchall()]
        if 'recurrence' not in cols:
            db.execute("ALTER TABLE events ADD COLUMN recurrence TEXT NOT NULL DEFAULT 'none'")
        if 'recur_n' not in cols:
            db.execute("ALTER TABLE events ADD COLUMN recur_n INTEGER")

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
        "INSERT INTO events (an,month,day,name,description,is_annual,recurrence,recur_n,faction_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (an, d['month'], d['day'], d['name'], d.get('description'),
         is_annual, r, d.get('recur_n'), d.get('faction_id') or None)
    )
    return jsonify(qone(_EVT_SELECT + " WHERE e.id=?", (eid,))), 201

@app.route('/api/events/<int:eid>', methods=['PUT'])
def api_update_event(eid):
    d = request.json
    r = d.get('recurrence','none')
    is_annual = 1 if (d.get('is_annual') or r == 'annual') else 0
    an = None if is_annual else d.get('an')
    run("UPDATE events SET an=?,month=?,day=?,name=?,description=?,is_annual=?,recurrence=?,recur_n=?,faction_id=? WHERE id=?",
        (an, d['month'], d['day'], d['name'], d.get('description'),
         is_annual, r, d.get('recur_n'), d.get('faction_id') or None, eid))
    return jsonify(qone(_EVT_SELECT + " WHERE e.id=?", (eid,)))

@app.route('/api/events/<int:eid>', methods=['DELETE'])
def api_delete_event(eid):
    run("DELETE FROM events WHERE id=?", (eid,))
    return jsonify({'ok': True})

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

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
