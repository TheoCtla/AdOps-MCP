# AdOps-MCP

Serveurs MCP (Model Context Protocol) pour gérer des comptes Google Ads et Meta Ads via Claude.

## À quoi ça sert

Ce projet expose un ensemble complet de tools qui permettent à Claude de lire et d'agir sur des comptes Google Ads et Meta Ads en langage naturel. Au lieu de jongler entre les dashboards, d'ouvrir 10 onglets ou d'écrire des rapports custom, on demande directement à Claude :

- "Donne-moi les perfs des 15 derniers jours sur le client X, Google et Meta"
- "Quels mots-clés ont un Quality Score en dessous de 5 sur ce compte ?"
- "Ajoute 'définition' en négatif exact sur la campagne Search LMNP"
- "Compare le CPA Meta vs Google sur tous les clients ce mois-ci"
- "Pause la campagne Display de ce compte"

Claude identifie le bon tool, appelle l'API concernée, et répond en langage naturel avec des données en temps réel et la possibilité d'agir quand c'est nécessaire.

## Périmètre

Deux serveurs MCP, un par plateforme :

- **MCP Google Ads** — connecté au compte manager (MCC), accède à tous les comptes clients
- **MCP Meta Ads** — connecté au Business Manager, accède à tous les comptes publicitaires

Chaque serveur expose à la fois des tools de lecture (performances, annonces, mots-clés, search terms, audiences, budgets, etc.) et des tools d'écriture (pause/activation, ajout de négatifs, création d'annonces, modification de budgets, duplication d'ad sets, etc.). L'objectif est un accès total et conversationnel aux données et aux opérations publicitaires.

## État d'avancement

**Projet en cours.**

**Fait :**
- Authentification fonctionnelle sur les deux plateformes (Google Ads + Meta Ads)
- Architecture du serveur MCP en place et validée end-to-end via MCP Inspector et Claude Code
- 8 tools de lecture Google Ads opérationnels (comptes, performances campagnes/ad groups/mots-clés, daily, search terms, négatifs, annonces)

**À venir :**
- ~20 tools de lecture supplémentaires côté Google Ads (segmentation, configuration, analyses avancées)
- ~25 tools d'écriture côté Google Ads
- Côté Meta Ads : ~15 tools de lecture et ~25 tools d'écriture
- Déploiement sur VPS avec exposition HTTPS
- Documentation complète (installation, maintenance, troubleshooting)

## Stack

- Python 3.11+
- SDK MCP officiel Anthropic
- `google-ads` (lib officielle Google)
- `facebook-business` (lib officielle Meta)
