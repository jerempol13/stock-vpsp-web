# Gestion de stock par QR code

Application Flask simple pour gérer les entrées et sorties de stock.

## Fonctions

- Ajout de produits
- Stock actuel
- Entrée de stock
- Sortie de stock avec blocage si le stock est insuffisant
- Historique des mouvements
- Deux QR codes automatiques par produit :
  - Entrée
  - Sortie
- Numéro de lot et date de péremption pour les entrées

## Installation locale

```bash
python -m venv .venv
```

Sous Windows :

```bash
.venv\Scripts\activate
```

Sous Linux/macOS :

```bash
source .venv/bin/activate
```

Puis :

```bash
pip install -r requirements.txt
python app.py
```

Ouvrir ensuite :

```text
http://127.0.0.1:5000
```

## Déploiement sur Render

1. Mettre ce projet sur GitHub.
2. Dans Render, créer un nouveau Blueprint.
3. Sélectionner le dépôt.
4. Render utilisera automatiquement `render.yaml`.
5. Une fois le site en ligne, créer les produits.
6. Ouvrir la page « QR codes » de chaque produit puis imprimer les deux codes.

## Liens produits

L'application utilise des liens simples et fiables :

```text
/entree/1
/sortie/1
```

Le chiffre correspond à l'identifiant du produit. Le produit est donc toujours prérempli après le scan.
