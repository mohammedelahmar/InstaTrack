# InstaTrack

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0-000?logo=flask)
![MongoDB](https://img.shields.io/badge/MongoDB-optional-success?logo=mongodb)

InstaTrack automatise la collecte des relations Instagram (followers / following) pour un ou plusieurs comptes cibles, enregistre l'historique dans MongoDB (ou `mongomock` en local) et expose une CLI ainsi qu'un dashboard Flask pour suivre les changements récents.

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Architecture rapide](#architecture-rapide)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration](#configuration)
- [Utilisation](#utilisation)
	- [CLI](#cli)
	- [Interface web](#interface-web)
	- [Planification quotidienne](#planification-quotidienne)
- [Assistant IA Gemini](#assistant-ia-gemini)
- [Données stockées](#données-stockées)
- [Tests](#tests)
- [Dépannage & bonnes pratiques](#dépannage--bonnes-pratiques)

## Fonctionnalités

- Authentification via compte observateur (instagrapi) avec session persistée pour éviter les challenges.
- Snapshots followers/following + détection automatique des ajouts/suppressions.
- Dashboard Flask (Chart.js) : sélecteur 7/14/30 jours, indicateurs "net", tops entrants/sortants, jauges réciprocité, comparaison followers/following, export CSV en un clic.
- Page Paramètres : gestion des comptes surveillés, cookie de session, intervalle de rafraîchissement automatique du dashboard.
- CLI unifiée : collecte ponctuelle, rapport texte/CSV, lancement du dashboard, ordonnanceur APScheduler.
- Journalisation centralisée et configuration par variables d'environnement `.env`.
- Assistant IA (Gemini) intégré pour questionner les listes en français.

## Architecture rapide

- **Entrée** : `main.py` expose les sous-commandes `run`, `report`, `web`, `schedule`.
- **Services** :
	- `TrackerService` orchestre la collecte et le diff.
	- `ReportService` fournit stats, historique, export CSV.
	- `SettingsService` gère la persistance des réglages `.env` et les vérifications de compte.
- **Persistance** : MongoDB (collections `snapshots` et `changes`), repli automatique vers `mongomock` si `USE_MOCK_DB=1` ou si Mongo est indisponible.
- **UI** : Flask (`web/app.py`), templates dans `web/templates`, assets dans `web/static` (Chart.js, settings.js).
- **Ordonnanceur** : APScheduler (`utils/scheduler.py`) pour les captures quotidiennes.
- **Logs** : `utils/logger.py` écrit dans `data/logs/instatrack.log` et respecte `LOG_LEVEL`.

## Prérequis

- Python 3.10+
- Accès à un compte Instagram observateur (doit suivre les comptes privés à surveiller).
- MongoDB optionnel (sinon `mongomock` est utilisé en local ou si `USE_MOCK_DB=1`).
- Clé Google AI Studio pour l'IA (optionnel) : `GEMINI_API_KEY`.

## Installation

```bash
git clone https://github.com/mohammedelahmar/InstaTrack.git
cd InstaTrack
python -m venv .venv
source .venv/bin/activate  # Sous Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

1. Copier `.env.example` (ou créer `.env`) à la racine et renseigner les variables clés :
	 - **Cibles & Instagram** : `TARGET_ACCOUNTS`, `INSTAGRAM_USERNAME`, `INSTAGRAM_PASSWORD` ou `INSTAGRAM_SESSIONID` (prioritaire), `INSTAGRAM_DISABLE_SESSION` (éviter de le mettre à 1 pour préserver la session), `INSTAGRAM_SESSION_PATH`.
	 - **Mongo** : `MONGO_URI`, `MONGO_DB_NAME`, `USE_MOCK_DB` pour forcer `mongomock`.
	 - **Ordonnancement** : `SCRAPE_HOUR_UTC`, `SCRAPE_MINUTE_UTC`.
	 - **Dashboard** : `AUTO_REFRESH_INTERVAL_SECONDS` (0 pour désactiver), `LOG_LEVEL`, `LOG_DIR`.
	 - **IA Gemini** (optionnel) : `GEMINI_API_KEY`, `GEMINI_MODEL_NAME`, `GEMINI_MAX_OUTPUT_TOKENS`, `GEMINI_TEMPERATURE`.
2. Le compte observateur doit suivre les comptes privés ciblés.
3. Les dossiers `data/cache` et `data/logs` sont créés automatiquement.

### Récupérer `INSTAGRAM_SESSIONID`

1. Connectez-vous à instagram.com dans votre navigateur.
2. Ouvrez les outils de développement → Application/Storage → Cookies → `https://www.instagram.com`.
3. Copiez la valeur `sessionid` puis placez-la dans `.env` :

```
INSTAGRAM_SESSIONID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Renouvelez le cookie si vous vous déconnectez ou s'il est invalidé.

## Utilisation

### CLI

```bash
python main.py run                 # Collecte immédiate (affiche le résumé JSON)
python main.py report --days 7     # Rapport texte + export CSV optionnel (--csv chemin/export.csv)
python main.py web --host 0.0.0.0 --port 5000 --debug  # Lancer le dashboard
python main.py schedule            # Lancer l'ordonnanceur quotidien (APScheduler)
```

### Interface web

Lancer `python main.py web` puis ouvrir `http://127.0.0.1:5000` (ou l'hôte choisi).

Vous y trouverez :
- Récap gains/pertes sur la période (7/14/30 jours).
- Graphiques followers/following (ajouts, suppressions, net) + jauges réciprocité/comparaison.
- Tableau des derniers changements, téléchargement CSV, actions rapides (capture immédiate, activation scheduler, masquage graphiques).
- Page Paramètres : gestion des comptes, session ID temporaire, intervalle d'auto-refresh (≥ 30 s), demandes de suivi pour comptes privés.

### Planification quotidienne

L'ordonnanceur intégré s'appuie sur `SCRAPE_HOUR_UTC` et `SCRAPE_MINUTE_UTC`.

```bash
python main.py schedule
```

Les exécutions sont journalisées dans `data/logs/instatrack.log`.

## Assistant IA Gemini

- Activer en ajoutant `GEMINI_API_KEY` dans `.env`.
- Paramètres facultatifs : `GEMINI_MODEL_NAME` (défaut `gemini-1.5-flash-latest` avec repli automatique), `GEMINI_MAX_OUTPUT_TOKENS`, `GEMINI_TEMPERATURE`.
- L'assistant reçoit les listes complètes followers/following + stats de réciprocité et répond en français en rappelant les limites du périmètre.

## Données stockées

- `snapshots` : `{ target_account, list_type, users[], collected_at }`
- `changes`   : `{ target_account, list_type, change_type, user, detected_at }`

## Tests

```bash
USE_MOCK_DB=1 pytest
```

Les tests couvrent le diff, le stockage Mongo (avec `mongomock`), les services et le client instagrapi stub.

## Dépannage & bonnes pratiques

- **Session Instagram** : laisser la persistance active (`INSTAGRAM_DISABLE_SESSION` à 0) pour éviter les challenges; conserver `data/cache/insta_session.json`.
- **Rate limiting** : ajuster `MIN_REQUEST_DELAY` / `MAX_REQUEST_DELAY`, `MAX_RETRIES`, `RETRY_BACKOFF_SECONDS` en cas de blocages.
- **Mongo indisponible** : définir `USE_MOCK_DB=1` pour forcer le mode embarqué.
- **Logs** : consulter `data/logs/instatrack.log` pour diagnostiquer les erreurs (niveau via `LOG_LEVEL`).
- **Sécurité** : ne jamais commiter `.env` ni les secrets; en production, chiffrer les variables et sécuriser l'instance MongoDB.

Bon suivi !
