import io
import os
from datetime import datetime
from urllib.parse import quote

import qrcode
import requests
from flask import Flask, Response, flash, redirect, render_template_string, request, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "a-remplacer-dans-vercel")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

BASE_HTML = """
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }}</title>
<style>
:root{--bg:#f4f7fb;--panel:#fff;--text:#172033;--muted:#667085;--border:#d7deea;--blue:#175cd3;--green:#16804a;--red:#c4322e}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
header{background:#102a43;color:#fff;padding:16px}.wrap{max-width:980px;margin:auto}nav{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
nav a{color:#fff;text-decoration:none;border:1px solid #ffffff55;border-radius:8px;padding:8px 10px}
main{max-width:980px;margin:auto;padding:16px}.panel{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:18px;margin-bottom:14px;box-shadow:0 3px 12px #102a4310}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}
label{display:block;font-weight:700;margin:14px 0 5px}input,select{width:100%;padding:12px;border:1px solid var(--border);border-radius:9px;font-size:16px}
input[readonly]{background:#edf2f7}.btn,button{display:inline-block;border:0;border-radius:9px;padding:11px 14px;color:#fff;background:var(--blue);font-weight:750;text-decoration:none;cursor:pointer}
.green{background:var(--green)}.red{background:var(--red)}.gray{background:#52606d}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.flash{padding:12px;border-radius:9px;margin-bottom:12px}.success{background:#dcfce7;color:#14532d}.error{background:#fee2e2;color:#7f1d1d}
.stock{font-size:28px;font-weight:850}.muted{color:var(--muted)}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--border)}
.qr{width:260px;max-width:100%}@media(max-width:650px){thead{display:none}table,tbody,tr,td{display:block}tr{padding:9px 0;border-bottom:1px solid var(--border)}td{border:0;padding:4px}}
</style>
</head>
<body>
<header><div class="wrap"><strong>Stock VPSP — QR codes</strong><nav>
<a href="{{ url_for('home') }}">Stock</a><a href="{{ url_for('history') }}">Historique</a>
</nav></div></header>
<main>
{% with messages = get_flashed_messages(with_categories=true) %}
{% for category,message in messages %}<div class="flash {{ category }}">{{ message }}</div>{% endfor %}
{% endwith %}
{{ content|safe }}
</main></body></html>
"""

def configured():
    return bool(SUPABASE_URL and SUPABASE_KEY)

def headers(prefer=None):
    result = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        result["Prefer"] = prefer
    return result

def api(method, table, params=None, payload=None, prefer=None):
    if not configured():
        raise RuntimeError("Supabase n'est pas configuré.")
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    response = requests.request(
        method, url, headers=headers(prefer), params=params, json=payload, timeout=15
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Erreur Supabase {response.status_code}: {response.text[:250]}")
    if not response.text:
        return []
    return response.json()

def render_page(title, inner, **context):
    content = render_template_string(inner, **context)
    return render_template_string(BASE_HTML, title=title, content=content)

def product(product_id):
    items = api("GET", "produits", params={
        "select": "id,nom,actif",
        "id": f"eq.{product_id}",
        "actif": "eq.true",
        "limit": "1",
    })
    return items[0] if items else None

def stock_for(product_id):
    rows = api("GET", "mouvements", params={
        "select": "type,quantite",
        "produit_id": f"eq.{product_id}",
    })
    total = 0
    for row in rows:
        qty = int(row.get("quantite") or 0)
        total += qty if row.get("type") == "ENTREE" else -qty
    return total

@app.route("/")
def home():
    if not configured():
        return render_page("Configuration requise", """
        <section class="panel"><h1>Configuration Supabase requise</h1>
        <p>Le site est bien lancé, mais il faut ajouter <code>SUPABASE_URL</code>,
        <code>SUPABASE_KEY</code> et <code>SECRET_KEY</code> dans les variables d'environnement Vercel.</p></section>
        """)
    try:
        products = api("GET", "produits", params={
            "select": "id,nom",
            "actif": "eq.true",
            "order": "nom.asc",
            "limit": "1000",
        })
        movements = api("GET", "mouvements", params={"select": "produit_id,type,quantite"})
        stocks = {}
        for m in movements:
            pid = int(m["produit_id"])
            qty = int(m["quantite"])
            stocks[pid] = stocks.get(pid, 0) + (qty if m["type"] == "ENTREE" else -qty)
        return render_page("Stock", """
        <section class="panel"><h1>Stock actuel</h1>
        <p class="muted">Chaque produit possède un QR code d'entrée et un QR code de sortie.</p></section>
        <div class="grid">
        {% for p in products %}
        <section class="panel"><h2>{{ p.nom }}</h2><div class="stock">{{ stocks.get(p.id,0) }} unité(s)</div>
        <div class="actions">
        <a class="btn green" href="{{ url_for('movement', action='entree', product_id=p.id) }}">Entrée</a>
        <a class="btn red" href="{{ url_for('movement', action='sortie', product_id=p.id) }}">Sortie</a>
        <a class="btn gray" href="{{ url_for('qrcodes', product_id=p.id) }}">QR codes</a>
        </div></section>
        {% endfor %}
        </div>
        """, products=products, stocks=stocks)
    except Exception as exc:
        return render_page("Erreur", "<section class='panel'><h1>Erreur</h1><p>{{ error }}</p></section>", error=str(exc)), 500

@app.route("/<action>/<int:product_id>", methods=["GET", "POST"])
def movement(action, product_id):
    if action not in ("entree", "sortie"):
        return "Action inconnue", 404
    try:
        p = product(product_id)
        if not p:
            return "Produit introuvable", 404
        current_stock = stock_for(product_id)

        if request.method == "POST":
            try:
                quantity = int(request.form.get("quantity", "0"))
                if quantity <= 0:
                    raise ValueError
            except ValueError:
                flash("La quantité doit être un entier supérieur à zéro.", "error")
                return redirect(request.url)

            if action == "sortie" and quantity > current_stock:
                flash(f"Stock insuffisant : {current_stock} disponible(s).", "error")
                return redirect(request.url)

            payload = {
                "produit_id": product_id,
                "type": action.upper(),
                "quantite": quantity,
                "nom_secouriste": request.form.get("operator_name", "").strip(),
                "lot_vpsp": request.form.get("lot_vpsp", "").strip(),
                "numero_lot": request.form.get("numero_lot", "").strip() or None,
                "date_peremption": request.form.get("date_peremption", "").strip() or None,
                "date_mouvement": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
            api("POST", "mouvements", payload=payload, prefer="return=minimal")
            flash(f"{'Entrée' if action == 'entree' else 'Sortie'} enregistrée.", "success")
            return redirect(url_for("home"))

        return render_page("Entrée" if action == "entree" else "Sortie", """
        <section class="panel"><h1>{{ "Entrée de stock" if action=="entree" else "Sortie de stock" }}</h1>
        <form method="post">
        <label>Produit</label><input value="{{ p.nom }}" readonly>
        <p class="muted">Stock actuel : <strong>{{ current_stock }}</strong></p>
        <label for="quantity">Quantité</label><input id="quantity" name="quantity" type="number" min="1" required autofocus>
        <label for="operator_name">Nom du secouriste</label><input id="operator_name" name="operator_name">
        <label for="lot_vpsp">Emplacement / lot VPSP</label>
        <select id="lot_vpsp" name="lot_vpsp"><option>Armoire</option><option>VPSP</option><option>Lot A</option><option>Lot B</option><option>Lot C</option><option>Kits</option></select>
        {% if action=="entree" %}
        <label for="numero_lot">Numéro de lot fabricant</label><input id="numero_lot" name="numero_lot">
        <label for="date_peremption">Date de péremption</label><input id="date_peremption" name="date_peremption" type="date">
        {% endif %}
        <div class="actions"><button class="{{ 'green' if action=='entree' else 'red' }}" type="submit">Valider</button>
        <a class="btn gray" href="{{ url_for('home') }}">Annuler</a></div>
        </form></section>
        """, action=action, p=p, current_stock=current_stock)
    except Exception as exc:
        return render_page("Erreur", "<section class='panel'><h1>Erreur</h1><p>{{ error }}</p></section>", error=str(exc)), 500

@app.route("/historique")
def history():
    try:
        rows = api("GET", "mouvements", params={
            "select": "id,date_mouvement,type,quantite,nom_secouriste,lot_vpsp,numero_lot,date_peremption,produits(nom)",
            "order": "date_mouvement.desc",
            "limit": "500",
        })
        return render_page("Historique", """
        <section class="panel"><h1>Historique</h1>
        <table><thead><tr><th>Date</th><th>Produit</th><th>Type</th><th>Qté</th><th>Secouriste</th><th>Lot</th></tr></thead>
        <tbody>{% for m in rows %}<tr>
        <td>{{ m.date_mouvement or "" }}</td><td>{{ m.produits.nom if m.produits else "Produit" }}</td>
        <td>{{ m.type }}</td><td>{{ m.quantite }}</td><td>{{ m.nom_secouriste or "—" }}</td>
        <td>{{ m.lot_vpsp or "—" }}{% if m.numero_lot %}<br>N° {{ m.numero_lot }}{% endif %}{% if m.date_peremption %}<br>{{ m.date_peremption }}{% endif %}</td>
        </tr>{% endfor %}</tbody></table></section>
        """, rows=rows)
    except Exception as exc:
        return render_page("Erreur", "<section class='panel'><h1>Erreur</h1><p>{{ error }}</p></section>", error=str(exc)), 500

@app.route("/qrcodes/<int:product_id>")
def qrcodes(product_id):
    try:
        p = product(product_id)
        if not p:
            return "Produit introuvable", 404
        return render_page("QR codes", """
        <section class="panel"><h1>{{ p.nom }}</h1><p>Imprimez les deux codes.</p></section>
        <div class="grid">
        <section class="panel"><h2>Entrée</h2><img class="qr" src="{{ url_for('qr_png', action='entree', product_id=p.id) }}"></section>
        <section class="panel"><h2>Sortie</h2><img class="qr" src="{{ url_for('qr_png', action='sortie', product_id=p.id) }}"></section>
        </div>
        """, p=p)
    except Exception as exc:
        return str(exc), 500

@app.route("/qr/<action>/<int:product_id>.png")
def qr_png(action, product_id):
    if action not in ("entree", "sortie"):
        return "Action inconnue", 404
    target = url_for("movement", action=action, product_id=product_id, _external=True)
    image = qrcode.make(target)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(buffer.getvalue(), mimetype="image/png")

# Compatibilité avec les anciens QR codes : /?produit=7 ouvre une sortie.
@app.before_request
def legacy_qr():
    if request.path == "/" and request.args.get("produit"):
        try:
            product_id = int(request.args["produit"])
            return redirect(url_for("movement", action="sortie", product_id=product_id))
        except ValueError:
            pass
