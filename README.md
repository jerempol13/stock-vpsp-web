# Stock VPSP — version Vercel

Cette version n'utilise pas SQLite pour les données en ligne. Vercel exécute l'application dans une fonction dont le disque local n'est pas persistant. Les produits et mouvements sont donc stockés dans Supabase.

## Contenu

- `app.py` : application Flask complète, avec pages HTML intégrées
- `requirements.txt` : dépendances Python
- `schema_supabase.sql` : tables et règles Supabase
- `produits.csv` : 290 produits uniques extraits de l'ancienne base
- `.python-version` : version Python utilisée par Vercel

## Mise en place

### 1. Supabase

1. Créer ou ouvrir un projet Supabase.
2. Ouvrir **SQL Editor**.
3. Copier-coller tout le contenu de `schema_supabase.sql`, puis exécuter.
4. Ouvrir **Table Editor > produits > Insert > Import data from CSV**.
5. Importer `produits.csv`.

### 2. GitHub

Envoyer ces fichiers à la racine du dépôt. Aucun dossier `templates` ou `static` n'est nécessaire.

### 3. Vercel

1. Importer le dépôt GitHub dans Vercel.
2. Ne pas renseigner de Build Command ni d'Output Directory.
3. Ajouter ces variables d'environnement :
   - `SUPABASE_URL` : URL du projet Supabase
   - `SUPABASE_KEY` : clé `anon` du projet Supabase
   - `SECRET_KEY` : une longue valeur aléatoire
4. Cliquer sur **Deploy**.

Les anciens QR codes `/?produit=7` restent compatibles et ouvrent une sortie de stock.
