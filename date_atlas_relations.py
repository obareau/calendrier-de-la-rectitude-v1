#!/usr/bin/env python3
"""Chronos Phase D — applique les dates curées du lore aux relations de l'Atlas.

Lit `lore_temporal.json` (durées de vie + relations datées, curées depuis le lore
robotariis-writing) et écrit le champ `since` sur les relations correspondantes de
l'Atlas via son API HTTP (`PUT /api/relations/<id>`).

Chronos reste garant du temps ; l'Atlas reçoit le miroir année (`An<n>`) et redevient
garant de la cohérence. Idempotent : ré-exécutable sans effet de bord.

Usage:
  python date_atlas_relations.py --dry-run   # rapport sans écrire
  python date_atlas_relations.py             # applique
Config: ATLAS_URL (défaut http://localhost:5557).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ATLAS_URL = os.environ.get('ATLAS_URL', 'http://localhost:5557').rstrip('/')
HERE = os.path.dirname(os.path.abspath(__file__))
CURATION = os.path.join(HERE, 'lore_temporal.json')


def _get(path):
    with urllib.request.urlopen(ATLAS_URL + path, timeout=5) as r:
        return json.loads(r.read().decode('utf-8'))


def _put(path, payload):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(ATLAS_URL + path, data=data, method='PUT',
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode('utf-8'))


def main():
    ap = argparse.ArgumentParser(description="Date les relations Atlas depuis le lore curé.")
    ap.add_argument('--dry-run', action='store_true', help="rapport sans écrire dans l'Atlas")
    args = ap.parse_args()

    curation = json.load(open(CURATION, encoding='utf-8'))
    wanted = curation['relations']

    try:
        graph = _get('/api/graph')
    except (urllib.error.URLError, OSError) as e:
        print(f"✗ Atlas injoignable sur {ATLAS_URL} : {e}", file=sys.stderr)
        sys.exit(1)

    by_id = {r['id']: r for r in graph['relations']}
    labels = {n['id']: n['label'] for n in graph['nodes']}

    applied, skipped, missing, collisions = 0, 0, 0, []
    by_conf = {}  # répartition par indice de certitude
    # détection de collisions : plusieurs relations à la même date exacte
    seen_dates = {}

    print(f"Atlas: {ATLAS_URL} · {len(graph['relations'])} relations · curation: {len(wanted)} datées\n")
    for w in wanted:
        rid, since = w['id'], w['since']
        cur = by_id.get(rid)
        if cur is None:
            print(f"  ✗ relation id={rid} introuvable ({w['source']}→{w['target']}) — IGNORÉE")
            missing += 1
            continue
        # garde-fou : la relation ciblée doit correspondre à la curation
        if cur['source'] != w['source'] or cur['target'] != w['target'] or cur['rel_type'] != w['rel_type']:
            print(f"  ⚠ id={rid} ne correspond pas ({cur['source']}→{cur['target']}/{cur['rel_type']} "
                  f"vs {w['source']}→{w['target']}/{w['rel_type']}) — IGNORÉE")
            missing += 1
            continue
        seen_dates.setdefault(since, []).append(rid)
        conf = w.get('confidence', 'certain')
        by_conf[conf] = by_conf.get(conf, 0) + 1
        meta = dict(cur.get('metadata') or {})
        lbl = f"{labels.get(w['source'], w['source'])} —{w['rel_type']}→ {labels.get(w['target'], w['target'])}"
        if cur.get('since') == since and meta.get('since_confidence') == conf:
            print(f"  = {since:>6}  [{conf:>8}]  {lbl}  (déjà à jour)")
            skipped += 1
            continue
        print(f"  → {since:>6}  [{conf:>8}]  {lbl}   [{w['reason']}]")
        if not args.dry_run:
            meta['since_confidence'] = conf  # merge : préserve les autres métadonnées
            _put(f"/api/relations/{rid}", {'since': since, 'metadata': meta})
        applied += 1

    for since, ids in seen_dates.items():
        if len(ids) > 1:
            collisions.append((since, ids))

    conf_str = " · ".join(f"{n} {c}" for c, n in sorted(by_conf.items()))
    print(f"\nRésumé : {applied} {'à appliquer' if args.dry_run else 'appliquées'} · "
          f"{skipped} déjà à jour · {missing} ignorées")
    print(f"Certitude : {conf_str}")
    if collisions:
        print("Collisions de date (≥2 relations à la même date) — à vérifier côté cohérence :")
        for since, ids in collisions:
            print(f"  {since}: relations {ids}")
    if args.dry_run:
        print("\n(dry-run — aucune écriture. Relance sans --dry-run pour appliquer.)")


if __name__ == '__main__':
    main()
