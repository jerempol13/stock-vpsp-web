# Site mobile Stock VPSP

Ce dossier recrée la partie web supprimée.

## Fonctions

- anciens QR codes compatibles : `/?produit=7` ouvre une sortie ;
- nouveaux liens séparés : `/entree/7` et `/sortie/7` ;
- produit automatiquement prérempli ;
- choix du lot/emplacement ;
- contrôle du stock avant une sortie ;
- nom du secouriste obligatoire ;
- date de péremption pour les entrées ;
- historique ;
- génération d'un PDF contenant deux QR codes par produit.

## Test sur l'ordinateur

```bash
pip install -r requirements.txt
flask --app app run
```

Puis ouvrir `http://127.0.0.1:5000`.

## Mise en ligne sur Render

1. Décompresser ce dossier.
2. Le déposer dans un nouveau dépôt GitHub.
3. Dans Render, choisir **New > Blueprint**.
4. Sélectionner le dépôt : Render détectera `render.yaml`.
5. Une fois déployé, ouvrir `/qrcodes.pdf` pour obtenir les nouveaux QR codes.

## Important sur la synchronisation

Le site Render utilise sa propre copie persistante de la base SQLite. L'application Windows et le site ne se synchronisent pas automatiquement entre eux. Pour une synchronisation en temps réel, il faudra ensuite relier les deux applications à Supabase ou à une autre base en ligne.
