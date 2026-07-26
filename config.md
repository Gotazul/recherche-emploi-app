# Spécifications — Application de recherche et suivi de véhicule

## 1. Contexte et objectif

Luc recherche un **véhicule spécifique** (marque/modèle/critères précis) et souhaite une application personnelle qui :

- Lance des recherches **manuellement**, sur demande, plutôt qu'en tâche de fond automatique.
- Interroge une liste de **sites pré-identifiés** (Leboncoin, La Centrale, AutoScout24, etc. — à lister par Luc).
- Applique des **critères de recherche** définis une fois et réutilisables.
- Récupère les annonces correspondantes, soit par **scraping direct**, soit via **Claude pour Chrome** lorsque le scraping direct n'est pas possible (site protégé, JS lourd, anti-bot).
- Permet de **suivre** les annonces trouvées dans le temps (nouvelles, prix modifié, vendues/disparues).

---

## 2. Périmètre fonctionnel

### 2.1 Gestion des critères de recherche

Un profil de recherche = un ensemble de critères réutilisables :

| Critère | Exemple |
|---|---|
| Marque / Modèle | Peugeot 3008, ou plusieurs modèles équivalents |
| Année (min/max) | 2019–2022 |
| Kilométrage max | 60 000 km |
| Prix (min/max) | 15 000 € – 22 000 € |
| Motorisation | Diesel, essence, hybride |
| Boîte de vitesse | Manuelle / automatique |
| Localisation | Rayon autour de Besançon (ex. 100 km) |
| Finition / options | GPS, toit ouvrant, etc. (optionnel) |
| Vendeur | Particulier / Professionnel / Les deux |

Luc doit pouvoir **créer plusieurs profils** (ex. "3008 principal", "Alternative Kodiaq") et les modifier à tout moment.

### 2.2 Gestion des sites sources

- Liste de sites configurable manuellement par Luc (nom, URL de base, méthode d'accès).
- Pour chaque site, un mode d'accès :
  - **Direct** : l'app construit l'URL de recherche avec les critères et scrape la page de résultats.
  - **Via Claude pour Chrome** : l'app délègue la recherche/navigation à l'extension quand le direct ne fonctionne pas (site avec forte protection anti-bot, captcha, contenu dynamique complexe).
- Un site peut être marqué actif/inactif sans être supprimé.

### 2.3 Lancement de la recherche

- Bouton **"Rechercher maintenant"** par profil de critères (pas d'automatisation programmée dans la v1, conformément à la demande de Luc).
- L'app :
  1. Parcourt les sites actifs du profil.
  2. Construit la requête adaptée à chaque site.
  3. Récupère les résultats (direct ou Claude pour Chrome).
  4. Normalise les données (titre, prix, année, km, localisation, lien, photo, date de publication).
  5. Dédoublonne par rapport aux annonces déjà connues.

### 2.4 Suivi des annonces

Pour chaque annonce détectée, l'app conserve un historique :

- **Statut** : Nouvelle / Vue / Intéressante / Contactée / Écartée / Disparue (probablement vendue).
- **Historique de prix** : détection des baisses/hausses entre deux recherches.
- **Notes personnelles** (texte libre) — utile pour usage collaboratif avec Anne-Marie si besoin.
- **Comparateur** : vue tableau pour comparer plusieurs annonces "Intéressantes" côte à côte.

### 2.5 Tableau de bord

- Vue synthèse : nombre de nouvelles annonces depuis la dernière recherche, par profil et par site.
- Filtres/tri (prix, km, date, statut).
- Export possible (CSV) pour partage ou archivage.

---

## 3. Architecture proposée

### 3.1 Vue d'ensemble

```
[Interface utilisateur (web app locale)]
        │
        ▼
[Moteur de recherche]
   ├── Connecteur "Direct" (scraping HTTP + parsing HTML)
   └── Connecteur "Claude pour Chrome" (délégation navigation)
        │
        ▼
[Base de données locale (annonces, historique, profils, sites)]
```

### 3.2 Choix technique (compatible Ubuntu)

- **Frontend** : application web locale (React ou HTML/JS simple), utilisable dans le navigateur.
- **Backend léger** : Node.js ou Python (FastAPI/Flask) pour :
  - héberger l'API locale,
  - exécuter le scraping direct (ex. `requests`/`BeautifulSoup` ou `playwright` si JS nécessaire),
  - stocker les données.
- **Base de données** : SQLite (simple, fichier local, pas de serveur à gérer) — suffisant pour un usage personnel.
- **Intégration Claude pour Chrome** : pour les sites où le scraping direct échoue, Luc déclenche manuellement une recherche guidée via l'extension, qui peut renvoyer les résultats copiés/structurés dans l'app (import manuel ou semi-automatique selon les capacités de l'extension).

### 3.3 Pourquoi ce découpage

- Séparer "Direct" et "Claude pour Chrome" permet d'ajouter facilement de nouveaux sites sans tout casser.
- SQLite évite d'installer un serveur de base de données pour un usage mono-utilisateur.
- Une architecture locale (pas de cloud) convient à un usage personnel et évite les questions de confidentialité des données de recherche.

---

## 4. Modèle de données (simplifié)

**SearchProfile**
- id, nom, critères (JSON), sites associés, date de création

**Site**
- id, nom, url_base, mode_acces (direct/claude_chrome), actif (bool)

**Listing (annonce)**
- id, site_id, profil_id, titre, prix, annee, kilometrage, localisation, url, photo_url, date_publication, date_premiere_detection, date_derniere_detection, statut, notes

**PriceHistory**
- listing_id, date, prix

---

## 5. Points à trancher avec Luc

Quelques décisions à confirmer avant de démarrer le développement :

1. **Liste des sites** ciblés et pour chacun, si le scraping direct est envisageable (souvent contre les CGU de certains sites — à vérifier).
2. **Nombre de véhicules/profils** suivis en parallèle (impact sur l'UI du tableau de bord).
3. **Usage partagé** avec Anne-Marie : accès simultané depuis un autre appareil, ou usage mono-poste suffisant ?
4. **Fréquence d'usage réelle** : recherche ponctuelle ou plusieurs fois par semaine (impact sur l'ergonomie du bouton "Rechercher").

---

## 6. Prochaines étapes suggérées

1. Valider ce document.
2. Lister précisément les sites sources et tester la faisabilité du scraping direct pour chacun.
3. Définir le premier profil de recherche (véhicule cible).
4. Développer une v1 minimale : 1 profil, 2-3 sites, tableau de bord basique, sans historique de prix (ajouté en v2).
