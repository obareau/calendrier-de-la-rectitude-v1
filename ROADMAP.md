# Roadmap

## Objectif principal
Créer une application temporelle claire, lisible et adaptée à l'univers de la Rectitude, avec une timeline dynamique, des événements proches/contigus visibles, et des outils d'import/export cohérents.

## Priorités immédiates
- Thème clair par défaut pour toutes les vues, avec contraste élevé et typographie lisible
- Timeline dynamique et scrollable en mode axe, avec points d'événements cliquer/voler
- Vue d'événements proches : regrouper les événements du même jour ou des jours adjacents
- Améliorer le rendu de la liste Timeline pour faciliter la lecture et la navigation

## Améliorations UX / UI
- Ajouter une bascule `Jour / Période` pour afficher les événements par jour ou par plage temporelle
- Ajouter une barre de recherche temporelle (intervalle dates) au-dessus de la timeline
- Ajouter des badges de priorité ou de phase pour les événements importants
- Ajouter un mode « focus » pour isoler un événement et ses relations directes
- Améliorer les contrastes des boutons et cartes pour lecture rapide

## Fonctions de timeline avancées
- Mettre en place un affichage en colonnes de dates rapprochées dans la timeline
- Ajouter la sélection de plage temporelle : jour, mois, année, ère
- Ajouter des zones et des périodes de temps partagées, communes à toutes les factions
- Afficher les événements sur plusieurs jours / périodes avec une visualisation de durée
- Ajouter un calcul automatique de proximité pour les événements proches dans le temps
- Ajouter la possibilité de filtrer par période (années, saisons, mois, silence)
- Permettre le glisser-déposer sur la timeline pour réordonnancer visuellement ou déplacer une date

## Données et import/export
- Normaliser les imports CSV/Timeline autour du format Rectitude
- Gérer les entités et relations Timeline comme objets natifs plutôt que conversions Aeon
- Ajouter un format d'export JSON structuré pour intégration externe
- Ajouter un import par lot depuis un fichier de relation/entité combiné

## Evolution features
- Ajouter une carte spatiale/chronologique des factions et entités liées à la timeline
- Ajouter un affichage des relations d'entités dans la vue Timeline (lignes ou traits entre événements)
- Ajouter une API publique pour synchroniser la timeline avec un autre outil externe
- Ajouter une gestion des thèmes personnalisables pour l'utilisateur
- Ajouter des notifications temporelles ou des rappels basés sur le calendrier

## Notes techniques
- Garder l'application légère et sans dépendances externes lourdes
- Favoriser le vanilla JS et des composants CSS simples
- Documenter chaque nouveau format d'import/export dans `README.md`
- Conserver la compatibilité SQLite pour une maintenance facile
