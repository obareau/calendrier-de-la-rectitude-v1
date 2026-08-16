# Changelog

## [1.6.0] 2026-08-15
- Chronos : navigation complète de la frise — molette, Ctrl+molette (zoom centré
  sur le curseur), glisser-déplacer, flèches ↑↓ pour zoomer et ←→ pour défiler
  (Maj = pas large), Origine pour tout voir
- Chronos : zoom CONTINU au lieu de six crans en dur qui sautaient d'un facteur 3,5
- Chronos : 134 dates versées depuis le canon — 42 de la timeline canonique et 92
  du frontmatter des chapitres. La frise passe de 64 à 143 points datés, sur 56
  années couvertes (An -62 à An 729)
- Interface : largeur portée de 980 px fixes à min(2200px, 96vw) ; la frise suit
  désormais la place disponible et se redessine au redimensionnement
- Chronos : hauteur des voies portée de 44 à 96 px — les événements empilés sur
  quatre niveaux se chevauchaient
- Correctif : les raccourcis clavier et le redessin au redimensionnement testaient
  `S.view`, qui n'existe pas — c'est `S.currentView`. Aucun ne fonctionnait
- À propos : documentation des raccourcis et de l'origine des dates

## [1.4.2] 2026-05-03
- Sprint 2 commencé : Ajout des périodes temporelles avec dates de début et fin
- Sélecteurs de plages temporelles personnalisées dans la timeline (début/fin)
- Gestion des périodes dans l'interface réseau (entités/relations/périodes)
- API backend pour les périodes (CRUD complet)

## [1.4.1] 2026-05-03
- Sprint 1 finalisé : Timeline dynamique, axe scrollable et sélection de plage temporelle
- Thème clair par défaut, avec contraste élevé et rendu plus lisible
- Amélioration du mode liste Timeline et organisation par jour/mois/année/ère
- Nettoyage du branding Aeon et bascule complète vers Timeline Rectitude
- Correction de l'affichage : avant le 1er Ordium 413, les dates sont présentées selon le calendrier grégorien, en reconnaissant la coexistence des deux systèmes temporels
- Mise à jour des imports/exports Timeline pour entités et relations

## [1.4.0] 2026-05-03
- Ajout de l'export CSV d'événements
- Ajout de l'import CSV d'événements
- Ajout de l'export/import Timeline compatible, adapté au calendrier de la Rectitude
- Support amélioré des événements récurrents (`monthly`, `every_n_years`)
- Ajout de la gestion des entités : lieux, personnages, planètes et relations
- Ajout des imports CSV/Timeline pour les entités et les relations
- Ajout des pages `À propos` et `Changelog`
- Documentation projet : `README.md`, `ABOUT.md`, `CHANGELOG.md`
- Démarrage du dépôt Git local avec `.gitignore`

## [1.3.0] - version initiale
- Base du calendrier avec mois, factions, silence, événements et timeline
- Édition des entités et export PDF
