#!/usr/bin/env python3
"""Verse les dates du CANON dans la table `events` de Chronos.

⚠️⚠️ POURQUOI (2026-08-15). Chronos affichait ~64 points datés : 55 relations
venues d'Atlas (3 % de ses 1732 liens, dérivées d'un `lore_temporal.json` curé
à la main le 5 juillet) et 9 événements en propre. Pendant ce temps le canon
porte 136 dates que rien ne lisait — 44 dans `01-MONDE/timeline.md`, la
timeline canonique, et 92 dans le frontmatter `date:` des chapitres.

La donnée existait, le tuyau n'avait jamais été branché.

ℹ️ Répartition assumée, conforme à ce que déclare app.py : « Chronos est garant
du temps ; l'Atlas est garant de la cohérence ». Les ÉVÉNEMENTS datés vivent
donc ici ; Atlas garde ses RELATIONS. On ne corrige pas Atlas, on cesse d'en
dépendre pour ce qu'il ne sait pas faire.

Idempotent : réexécutable sans doublon (clé = source + nom + année).
Usage : python import_canon_dates.py [--dry-run]
"""
import argparse
import os
import re
import sqlite3

VAULT = os.path.expanduser(os.environ.get("VAULT_PATH", "~/robotariis-writing"))
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calendrier.db")

MOIS = {"ordium": 1, "fervor": 2, "laboris": 3, "prudium": 4, "valoris": 5,
        "constium": 6, "septium": 7, "servium": 8, "fortium": 9, "decorum": 10,
        "rectium": 11, "finalis": 12}

# « | **An 421** (30 Finalis) | 2834 | Description… | »
RX_LIGNE = re.compile(
    r"^\|\s*\*\*An\s+(-?\d+)(?:[–-]\d+)?\*\*\s*(?:\((\d+)\s+(\w+)\))?\s*\|[^|]*\|\s*(.+?)\s*\|", re.M)
RX_DATE_CHAP = re.compile(r"^date:\s*[\"']?([^\"'\n]+)", re.M)
RX_TITRE = re.compile(r"^(?:name|title):\s*[\"']?([^\"'\n]+)", re.M)


def nettoie(s):
    s = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", s)
    s = re.sub(r"\[\[([^\]]+)\]\]", r"\1", s)
    return re.sub(r"[*⚠️ℹ️✅⭐]+", "", s).strip()


def depuis_timeline():
    p = os.path.join(VAULT, "01-MONDE", "timeline.md")
    if not os.path.exists(p):
        return []
    out = []
    for an, jour, mois, desc in RX_LIGNE.findall(open(p, encoding="utf-8").read()):
        d = nettoie(desc)
        if not d:
            continue
        titre = re.split(r"\s+[—:.]\s+|\.\s", d)[0][:90]
        out.append({"an": int(an), "month": MOIS.get((mois or "").lower(), 1),
                    "day": int(jour) if jour else 1, "name": titre,
                    "description": d[:400], "src": "canon:timeline"})
    return out


def depuis_chapitres():
    d = os.path.join(VAULT, "06-RECITS")
    out = []
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not fn.endswith(".md"):
            continue
        txt = open(os.path.join(d, fn), encoding="utf-8").read()
        m = RX_DATE_CHAP.search(txt)
        if not m:
            continue
        a = re.search(r"An\s+(-?\d+)", m.group(1))
        if not a:
            continue
        jm = re.search(r"(\d+)\s+(\w+)", m.group(1))
        t = RX_TITRE.search(txt)
        out.append({"an": int(a.group(1)),
                    "month": MOIS.get(jm.group(2).lower(), 1) if jm else 1,
                    "day": int(jm.group(1)) if jm else 1,
                    "name": nettoie(t.group(1))[:90] if t else fn[:-3],
                    "description": f"Chapitre — {fn[:-3]}", "src": "canon:recits"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    lots = depuis_timeline() + depuis_chapitres()
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    cols = {r[1] for r in c.execute("PRAGMA table_info(events)")}
    if "src" not in cols:
        # ⚠️ La colonne doit exister AVANT la lecture d'idempotence, y compris en
        # simulation — sinon le --dry-run échoue sur une base vierge.
        c.execute("ALTER TABLE events ADD COLUMN src TEXT")
        conn.commit()
        cols.add("src")
    existants = {(r[0], r[1], r[2]) for r in
                 c.execute("SELECT an, name, coalesce(src,'') FROM events")}
    neufs = [e for e in lots if (e["an"], e["name"], e["src"]) not in existants]
    print(f"  timeline.md : {len(depuis_timeline())} · chapitres : {len(depuis_chapitres())}")
    print(f"  déjà présents : {len(lots) - len(neufs)} · à insérer : {len(neufs)}")
    for e in neufs[:5]:
        print(f"    An {e['an']:>4} m{e['month']:02d}j{e['day']:02d}  {e['name'][:58]}")
    if a.dry_run:
        print("  (simulation — rien écrit)")
        return
    c.executemany(
        "INSERT INTO events (an, month, day, name, description, is_annual, recurrence, src) "
        "VALUES (?,?,?,?,?,0,'none',?)",
        [(e["an"], e["month"], e["day"], e["name"], e["description"], e["src"]) for e in neufs])
    conn.commit()
    print(f"  ✅ {len(neufs)} événements versés · total table : "
          f"{c.execute('SELECT count(*) FROM events').fetchone()[0]}")


if __name__ == "__main__":
    main()
