# Recherche Voiture

Application web locale pour surveiller et comparer des annonces automobiles sur plusieurs sites (Leboncoin, La Centrale, AutoScout24, Hess Automobile…).

- Crée des **profils de recherche** avec tes critères (marque, modèle, année, km, prix, carburant, boîte, localisation)
- Lance les recherches **manuellement** en un clic
- Suit les annonces dans le temps : nouvelles, prix modifiés, disparues
- Compare plusieurs annonces côte à côte
- Exporte en CSV

---

## Prérequis

| Outil | Version minimale |
|---|---|
| Python | 3.11+ |
| Google Chrome | toute version récente |
| OS | Linux, macOS ou Windows (WSL recommandé) |

> **Chrome est requis** uniquement pour La Centrale, qui protège ses pages avec DataDome. L'app ouvre un onglet Chrome pour récupérer le cookie anti-bot, puis fait la requête automatiquement.

---

## Installation

```bash
# 1. Cloner le dépôt
git clone git@github.com:Gotazul/recherche-voiture-app.git
cd recherche-voiture-app

# 2. Lancer l'app (crée le venv et installe les dépendances automatiquement)
chmod +x start.sh
./start.sh
```

Ouvre ensuite **http://localhost:8000** dans ton navigateur.

### Installation manuelle (si start.sh ne convient pas)

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

---

## Premiers pas

### 1. Créer un profil de recherche

Va dans l'onglet **Profils** → **Nouveau profil**.

Renseigne tes critères :

| Champ | Exemple | Notes |
|---|---|---|
| Marque | `BMW` | |
| Modèle | `SERIE 2 U06 ACTIVE TOURER` | Nom complet ou partiel |
| Année min/max | `2021` / `2024` | |
| Kilométrage max | `80000` | |
| Prix min/max | `18000` / `28000` | |
| Carburant | `Diesel`, `Essence`, `Hybride`… | |
| Boîte | `Automatique` / `Manuelle` | |
| Code postal + rayon | `25000` + `150` km | Optionnel |

Tu peux créer **plusieurs profils** pour suivre différents modèles en parallèle.

### 2. Lancer une recherche

Va dans l'onglet **Recherche**, sélectionne un profil, et clique sur **Rechercher**.

L'app interroge tous les sites actifs et affiche le nombre d'annonces trouvées par site. Les nouvelles annonces sont marquées **Nouvelle** dans la liste.

> Pour La Centrale, une fenêtre Chrome s'ouvre brièvement (4 secondes) pour contourner la protection anti-bot — c'est normal.

### 3. Consulter les annonces

L'onglet **Annonces** liste toutes les annonces avec filtres (statut, prix, année, carburant, profil).

Chaque annonce peut être marquée :

| Statut | Signification |
|---|---|
| Nouvelle | Détectée pour la première fois |
| Vue | Tu l'as consultée |
| Intéressante | À garder en tête |
| Contactée | Tu as contacté le vendeur |
| Écartée | À ne plus voir |
| Disparue | N'apparaît plus sur le site |

### 4. Comparer des annonces

Sélectionne plusieurs annonces (cases à cocher) et clique sur **Comparer** pour les afficher côte à côte.

---

## Sites supportés

| Site | Scraping | Notes |
|---|---|---|
| Leboncoin | Direct | |
| La Centrale | Direct | Nécessite Chrome pour le cookie DataDome |
| AutoScout24 | Direct | |
| Hess Automobile | Direct | |
| ParuVendu | Manuel | Site en JavaScript pur — l'URL est générée mais la recherche doit être faite manuellement |

Pour ajouter un site non listé, va dans l'onglet **Sites** → **Nouveau site**. Si aucun scraper n'est disponible pour ce site, l'URL de recherche sera tout de même construite pour un accès manuel.

---

## Structure du projet

```
recherche-voiture-app/
├── app.py              # API FastAPI (routes)
├── database.py         # Accès SQLite (profils, annonces, sites)
├── filters.py          # Filtrage post-scraping (modèle, localisation…)
├── scrapers/
│   ├── base.py         # Classe de base commune
│   ├── lacentrale.py
│   ├── leboncoin.py
│   ├── autoscout24.py
│   ├── paruvendu.py
│   └── hessautomobile.py
├── static/
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── requirements.txt
└── start.sh
```

La base de données `voiture.db` est créée automatiquement au premier lancement (SQLite, fichier local).

---

## Dépendances principales

- [FastAPI](https://fastapi.tiangolo.com/) — API backend
- [Uvicorn](https://www.uvicorn.org/) — serveur ASGI
- [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) + lxml — parsing HTML
- [requests](https://docs.python-requests.org/) — requêtes HTTP
- [rookiepy](https://github.com/thewh1teagle/rookiepy) — lecture des cookies Chrome (pour La Centrale)

---

## Problèmes fréquents

**La Centrale renvoie une erreur HTTP 403**
→ Chrome doit être installé et accessible (`google-chrome` ou `chromium-browser` dans le PATH). L'app ouvre automatiquement un onglet pour récupérer le cookie DataDome.

**Aucune annonce trouvée alors que le site en a**
→ Le filtre post-scraping peut être trop strict. Vérifie que le champ **Modèle** dans le profil correspond bien au nom utilisé par le site (ex. `SERIE 2` plutôt que `Série 2 Active Tourer`).

**`rookiepy` échoue au démarrage**
→ Sur Linux, rookiepy peut nécessiter `libsecret` : `sudo apt install libsecret-1-dev`. La recherche fonctionnera quand même, mais La Centrale sera bloquée.

---

## Licence

Usage personnel — pas de licence open source définie.
