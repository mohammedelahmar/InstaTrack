# InstaTrack

InstaTrack est un outil Python qui automatise la récupération quotidienne des relations Instagram (followers / following) pour un ou plusieurs comptes cibles, conserve l'historique dans MongoDB et fournit une interface console + web pour visualiser les changements sur les 7 derniers jours.

## ✨ Fonctionnalités clés

- Authentification via un compte observateur (instagrapi) avec session persistée.
- Sauvegarde des snapshots followers/following dans MongoDB et détection automatique des ajouts / suppressions.
- Tableau de bord Flask avec graphiques (Chart.js) et export CSV des rapports.
- CLI unifiée pour lancer une collecte, afficher un rapport, démarrer l'UI ou planifier un suivi quotidien (APScheduler).
- Journalisation centralisée et configuration par variables d'environnement (`.env`).

## 🚀 Prise en main

1. **Cloner le dépôt** et créer un environnement virtuel Python 3.10+.
2. **Installer les dépendances** :

```bash
pip install -r requirements.txt
```

3. **Configurer l'environnement** :
	- Copier `.env.example` → `.env` et renseigner les identifiants du compte observateur, l'URI MongoDB et les comptes suivis (`TARGET_ACCOUNTS`).
	- Le compte observateur doit suivre les comptes privés à surveiller.
	- Astuce connexion: pour éviter les défis de sécurité Instagram, laissez la session se persister (ne mettez PAS `INSTAGRAM_DISABLE_SESSION=1`) ou renseignez `INSTAGRAM_SESSIONID` pour vous connecter via cookie.

4. **Lancer une collecte manuelle** :

```bash
python main.py run
```

Les résultats sont affichés en JSON et stockés automatiquement dans MongoDB (`snapshots`, `changes`).

## 🖥️ Interface web

Une interface Flask est fournie pour consulter les indicateurs et les derniers événements.

```bash
python main.py web --host 0.0.0.0 --port 5000
```

L'application affiche :

- Un récapitulatif des gains/pertes sur 7 jours.
- Un graphique (Chart.js) des variations quotidiennes.
- Un tableau des derniers changements (followers/following).

## ⏰ Planification quotidienne

Pour automatiser la collecte, utilisez l'ordonnanceur intégré (APScheduler) qui se base sur `SCRAPE_HOUR_UTC` / `SCRAPE_MINUTE_UTC`.

```bash
python main.py schedule
```

Le service tourne en tâche de fond et journalise toutes les exécutions dans `data/logs/instatrack.log`.

## 🛠️ CLI récapitulatif

```bash
python main.py run                 # Collecte immédiate
python main.py report --days 7     # Rapport texte (option --csv chemin/export.csv)
python main.py web                 # Dashboard Flask
python main.py schedule            # Suivi quotidien (APScheduler)
```

## 🧪 Tests

Des tests unitaires couvrent le diff des utilisateurs, le stockage Mongo (mongomock) et le service de tracking.

```bash
pytest
```

Activez `USE_MOCK_DB=1` pour exécuter les tests sans instance MongoDB.

## 🗄️ Modèle de données (MongoDB)

- `snapshots` : `{ target_account, list_type, users[], collected_at }`
- `changes` : `{ target_account, list_type, change_type, user, detected_at }`

## 🔒 Sécurité & bonnes pratiques

- Ne versionnez jamais `.env` ni les identifiants Instagram.
- Respectez le rate limiting d'Instagram (`MIN_REQUEST_DELAY` / `MAX_REQUEST_DELAY`).
- Surveillez les logs pour détecter les blocages ou les défis de sécurité Instagram.
- En production, chiffrer les secrets et utilisez une base MongoDB sécurisée.

### Connexion Instagram: éviter les blocages

- Par défaut, la session est persistée dans `data/cache/insta_session.json`. Évitez de définir `INSTAGRAM_DISABLE_SESSION=1` pour ne pas relancer une authentification complète à chaque exécution.
- Option avancée: utilisez un cookie de session pour vous connecter sans mot de passe.

Variables supportées:

- `INSTAGRAM_USERNAME`, `INSTAGRAM_PASSWORD`: identifiants classiques.
- `INSTAGRAM_SESSIONID`: cookie de session Instagram (prend le dessus si présent).

Comment récupérer `INSTAGRAM_SESSIONID`:

1. Connectez‑vous à instagram.com dans votre navigateur.
2. Ouvrez les outils de développement → Application/Storage → Cookies → `https://www.instagram.com`.
3. Copiez la valeur de la clé `sessionid` et collez‑la dans `.env`:

```
INSTAGRAM_SESSIONID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Remarque: changez ce cookie dès que vous vous déconnectez du navigateur ou si Instagram l’invalide.

## 🚧 Limitations actuelles

- Pas d'authentification multi-utilisateurs ni d'API publique.
- L'accès aux comptes privés exige que le compte observateur les suive.
- Les exports PDF / notifications push ne sont pas implémentés (faciles à ajouter via les services existants).

Bon suivi !
