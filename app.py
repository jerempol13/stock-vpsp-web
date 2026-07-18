import io
import os
from datetime import datetime

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
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{{ title }}</title>
<style>
:root{--bg:#f4f7fb;--panel:#fff;--text:#172033;--muted:#667085;--border:#d7deea;--blue:#175cd3;--green:#16804a;--red:#c4322e;--orange:#b54708}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:10;background:#102a43;color:#fff;padding:14px 16px}.wrap{max-width:1050px;margin:auto}
nav{display:flex;gap:7px;flex-wrap:wrap;margin-top:9px}nav a{color:#fff;text-decoration:none;border:1px solid #ffffff55;border-radius:9px;padding:8px 10px}
main{max-width:1050px;margin:auto;padding:16px}.panel{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:18px;margin-bottom:14px;box-shadow:0 3px 12px #102a4310}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:14px}
label{display:block;font-weight:750;margin:14px 0 5px}input,select{width:100%;padding:12px;border:1px solid var(--border);border-radius:9px;font-size:16px}
input[readonly]{background:#edf2f7}.btn,button{display:inline-block;border:0;border-radius:9px;padding:12px 15px;color:#fff;background:var(--blue);font-weight:780;text-decoration:none;cursor:pointer;font-size:15px}
.green{background:var(--green)}.red{background:var(--red)}.orange{background:var(--orange)}.gray{background:#52606d}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.actions>*{flex:1 1 130px;text-align:center}
.flash{padding:12px;border-radius:9px;margin-bottom:12px}.success{background:#dcfce7;color:#14532d}.error{background:#fee2e2;color:#7f1d1d}
.stock{font-size:28px;font-weight:850}.muted{color:var(--muted)}.badge{display:inline-block;padding:4px 8px;border-radius:999px;background:#e9eff8;font-weight:700}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--border)}
.qr{width:260px;max-width:100%}.hero{text-align:center;padding:22px}.hero .btn{font-size:18px;padding:15px 20px}
#reader{width:100%;max-width:620px;margin:auto}.scanner-status{text-align:center;font-weight:700;margin-top:12px}
.big-choice{display:grid;grid-template-columns:1fr 1fr;gap:12px}.big-choice button{min-height:78px;font-size:18px}
@media(max-width:650px){main{padding:11px}.panel{padding:14px}.big-choice{grid-template-columns:1fr}thead{display:none}table,tbody,tr,td{display:block}tr{padding:9px 0;border-bottom:1px solid var(--border)}td{border:0;padding:4px}}
</style>
</head>
<body>
<header><div class="wrap"><strong>Stock VPSP</strong><nav>
<a href="{{ url_for('home') }}">Armoire</a>
<a href="{{ url_for('mobile_home') }}">Réarmement mobile</a>
<a href="{{ url_for('bags') }}">Sacs</a>
<a href="{{ url_for('history') }}">Historique</a>
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
    response = requests.request(
        method,
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers(prefer),
        params=params,
        json=payload,
        timeout=20,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Erreur Supabase {response.status_code}: {response.text[:500]}")
    if not response.text:
        return []
    return response.json()

def rpc(function_name, payload):
    return api("POST", f"rpc/{function_name}", payload=payload)

def render_page(title, inner, **context):
    content = render_template_string(inner, **context)
    return render_template_string(BASE_HTML, title=title, content=content)

def product(product_id):
    rows = api("GET", "produits", params={
        "select": "id,nom,actif", "id": f"eq.{product_id}", "actif": "eq.true", "limit": "1"
    })
    return rows[0] if rows else None

def bag(bag_id):
    rows = api("GET", "sacs", params={
        "select": "id,nom,code,actif", "id": f"eq.{bag_id}", "actif": "eq.true", "limit": "1"
    })
    return rows[0] if rows else None

def armory_stocks():
    products = api("GET", "produits", params={"select": "id,nom", "actif": "eq.true", "order": "nom.asc", "limit": "1000"})
    moves = api("GET", "mouvements", params={"select": "produit_id,type,quantite"})
    stocks = {int(p["id"]): 0 for p in products}
    for m in moves:
        pid, qty = int(m["produit_id"]), int(m["quantite"])
        stocks[pid] = stocks.get(pid, 0) + (qty if m["type"] == "ENTREE" else -qty)
    return products, stocks

def stock_for(product_id):
    rows = api("GET", "mouvements", params={"select": "type,quantite", "produit_id": f"eq.{product_id}"})
    return sum(int(r["quantite"]) if r["type"] == "ENTREE" else -int(r["quantite"]) for r in rows)

def bag_stock_map(bag_id):
    rows = api("GET", "mouvements_sacs", params={
        "select": "produit_id,type,quantite", "sac_id": f"eq.{bag_id}", "limit": "10000"
    })
    stocks = {}
    for r in rows:
        pid, qty = int(r["produit_id"]), int(r["quantite"])
        positive = r["type"] in ("REARMEMENT", "AJUSTEMENT_PLUS")
        stocks[pid] = stocks.get(pid, 0) + (qty if positive else -qty)
    return stocks

@app.route("/")
def home():
    if request.args.get("produit"):
        try:
            return redirect(url_for("movement", action="sortie", product_id=int(request.args["produit"])))
        except ValueError:
            pass
    if not configured():
        return render_page("Configuration requise", """
        <section class="panel"><h1>Configuration Supabase requise</h1>
        <p>Ajoutez <code>SUPABASE_URL</code>, <code>SUPABASE_KEY</code> et <code>SECRET_KEY</code> dans Vercel.</p></section>
        """)
    try:
        products, stocks = armory_stocks()
        return render_page("Armoire", """
        <section class="panel"><h1>Stock de l’armoire</h1>
        <p class="muted">Le réarmement d’un sac diminue automatiquement ce stock.</p>
        <div class="actions"><a class="btn" href="{{ url_for('mobile_home') }}">📷 Ouvrir le réarmement mobile</a></div></section>
        <div class="grid">{% for p in products %}
        <section class="panel"><h2>{{ p.nom }}</h2><div class="stock">{{ stocks.get(p.id,0) }} unité(s)</div>
        <div class="actions">
        <a class="btn green" href="{{ url_for('movement', action='entree', product_id=p.id) }}">Entrée armoire</a>
        <a class="btn red" href="{{ url_for('movement', action='sortie', product_id=p.id) }}">Sortie armoire</a>
        <a class="btn gray" href="{{ url_for('qrcodes', product_id=p.id) }}">QR produit</a>
        </div></section>{% endfor %}</div>
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
                flash("La quantité doit être supérieure à zéro.", "error")
                return redirect(request.url)
            if action == "sortie" and quantity > current_stock:
                flash(f"Stock insuffisant : {current_stock} disponible(s).", "error")
                return redirect(request.url)
            payload = {
                "produit_id": product_id,
                "type": action.upper(),
                "quantite": quantity,
                "nom_secouriste": request.form.get("operator_name", "").strip(),
                "lot_vpsp": "Armoire",
                "numero_lot": request.form.get("numero_lot", "").strip() or None,
                "date_peremption": request.form.get("date_peremption", "").strip() or None,
                "date_mouvement": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
            api("POST", "mouvements", payload=payload, prefer="return=minimal")
            flash("Mouvement d’armoire enregistré.", "success")
            return redirect(url_for("home"))
        return render_page("Mouvement armoire", """
        <section class="panel"><h1>{{ "Entrée dans l’armoire" if action=="entree" else "Sortie de l’armoire" }}</h1>
        <form method="post"><label>Produit</label><input value="{{ p.nom }}" readonly>
        <p class="muted">Stock actuel : <strong>{{ current_stock }}</strong></p>
        <label>Quantité</label><input name="quantity" type="number" min="1" required autofocus>
        <label>Nom</label><input name="operator_name">
        {% if action=="entree" %}<label>Numéro de lot</label><input name="numero_lot">
        <label>Date de péremption</label><input name="date_peremption" type="date">{% endif %}
        <div class="actions"><button class="{{ 'green' if action=='entree' else 'red' }}">Valider</button>
        <a class="btn gray" href="{{ url_for('home') }}">Annuler</a></div></form></section>
        """, action=action, p=p, current_stock=current_stock)
    except Exception as exc:
        return render_page("Erreur", "<section class='panel'><h1>Erreur</h1><p>{{ error }}</p></section>", error=str(exc)), 500

@app.route("/mobile")
def mobile_home():
    try:
        sacs = api("GET", "sacs", params={"select": "id,nom,code", "actif": "eq.true", "order": "nom.asc"})
        return render_page("Réarmement mobile", """
        <section class="panel hero"><h1>Réarmement mobile</h1>
        <p>Choisissez un sac ou scannez directement son QR code.</p>
        <a class="btn" href="{{ url_for('scanner') }}">📷 Scanner un QR code</a></section>
        <div class="grid">{% for s in sacs %}<section class="panel"><h2>{{ s.nom }}</h2>
        <p class="muted">{{ s.code or "" }}</p><div class="actions">
        <a class="btn green" href="{{ url_for('bag_detail', bag_id=s.id) }}">S’occuper de ce sac</a>
        <a class="btn gray" href="{{ url_for('bag_qr', bag_id=s.id) }}">QR du sac</a>
        </div></section>{% else %}<section class="panel"><p>Aucun sac. Ajoutez-les dans Supabase.</p></section>{% endfor %}</div>
        """, sacs=sacs)
    except Exception as exc:
        return render_page("Erreur", "<section class='panel'><h1>Erreur</h1><p>{{ error }}</p></section>", error=str(exc)), 500

@app.route("/sacs")
def bags():
    return mobile_home()

@app.route("/sacs/<int:bag_id>")
def bag_detail(bag_id):
    try:
        s = bag(bag_id)
        if not s:
            return "Sac introuvable", 404
        products = api("GET", "produits", params={"select": "id,nom", "actif": "eq.true", "order": "nom.asc", "limit": "1000"})
        stock = bag_stock_map(bag_id)
        return render_page(s["nom"], """
        <section class="panel"><span class="badge">Sac sélectionné</span><h1>{{ s.nom }}</h1>
        <p>Scannez un produit, puis choisissez <strong>Produit utilisé</strong> ou <strong>Réarmement</strong>.</p>
        <div class="actions"><a class="btn" href="{{ url_for('scanner', sac_id=s.id) }}">📷 Scanner un produit</a>
        <a class="btn gray" href="{{ url_for('mobile_home') }}">Changer de sac</a></div></section>
        <section class="panel"><h2>Contenu actuel</h2><table><thead><tr><th>Produit</th><th>Qté</th><th>Action</th></tr></thead><tbody>
        {% for p in products if stock.get(p.id,0) != 0 %}<tr><td>{{ p.nom }}</td><td>{{ stock.get(p.id,0) }}</td>
        <td><a class="btn" href="{{ url_for('bag_product', bag_id=s.id, product_id=p.id) }}">Modifier</a></td></tr>
        {% else %}<tr><td colspan="3">Aucun contenu enregistré.</td></tr>{% endfor %}</tbody></table></section>
        """, s=s, products=products, stock=stock)
    except Exception as exc:
        return render_page("Erreur", "<section class='panel'><h1>Erreur</h1><p>{{ error }}</p></section>", error=str(exc)), 500

@app.route("/scanner")
def scanner():
    sac_id = request.args.get("sac_id", "")
    return render_page("Scanner", """
    <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
    <section class="panel"><h1>Scanner un QR code</h1>
    <p class="muted">{{ "Sac déjà choisi : scannez maintenant un produit." if sac_id else "Scannez d’abord le QR du sac, ou un QR produit." }}</p>
    <div id="reader"></div><div id="status" class="scanner-status">Autorisez l’accès à l’appareil photo.</div>
    <div class="actions"><a class="btn gray" href="{{ url_for('mobile_home') }}">Retour</a></div></section>
    <script>
    const selectedBag = {{ sac_id|tojson }};
    let locked = false;
    function onScanSuccess(decodedText) {
      if (locked) return;
      locked = true;
      document.getElementById("status").textContent = "QR reconnu…";
      try {
        const u = new URL(decodedText, window.location.origin);
        if (selectedBag && u.pathname.startsWith("/scan/produit/")) {
          u.searchParams.set("sac_id", selectedBag);
        }
        window.location.href = u.toString();
      } catch(e) {
        document.getElementById("status").textContent = "QR invalide.";
        locked = false;
      }
    }
    const scanner = new Html5QrcodeScanner("reader", {fps:10, qrbox:{width:250,height:250}, rememberLastUsedCamera:true}, false);
    scanner.render(onScanSuccess, () => {});
    </script>
    """, sac_id=sac_id)

@app.route("/scan/sac/<int:bag_id>")
def scan_bag(bag_id):
    if not bag(bag_id):
        return "Sac introuvable", 404
    return redirect(url_for("bag_detail", bag_id=bag_id))

@app.route("/scan/produit/<int:product_id>")
def scan_product(product_id):
    bag_id = request.args.get("sac_id", type=int)
    if not bag_id:
        flash("Choisissez d’abord le sac concerné.", "error")
        return redirect(url_for("mobile_home"))
    return redirect(url_for("bag_product", bag_id=bag_id, product_id=product_id))

@app.route("/sacs/<int:bag_id>/produits/<int:product_id>", methods=["GET", "POST"])
def bag_product(bag_id, product_id):
    try:
        s, p = bag(bag_id), product(product_id)
        if not s or not p:
            return "Sac ou produit introuvable", 404
        bag_qty = bag_stock_map(bag_id).get(product_id, 0)
        armory_qty = stock_for(product_id)
        if request.method == "POST":
            action = request.form.get("action")
            try:
                quantity = int(request.form.get("quantity", "0"))
                if quantity <= 0:
                    raise ValueError
            except ValueError:
                flash("Quantité invalide.", "error")
                return redirect(request.url)
            operator = request.form.get("operator_name", "").strip()
            if action == "utilisation":
                rpc("utiliser_produit_sac", {
                    "p_sac_id": bag_id, "p_produit_id": product_id,
                    "p_quantite": quantity, "p_secouriste": operator
                })
                flash(f"{quantity} produit(s) retiré(s) du sac.", "success")
            elif action == "rearmement":
                rpc("rearmer_produit_sac", {
                    "p_sac_id": bag_id, "p_produit_id": product_id,
                    "p_quantite": quantity, "p_secouriste": operator
                })
                flash(f"{quantity} produit(s) transféré(s) de l’armoire vers le sac.", "success")
            else:
                flash("Action inconnue.", "error")
                return redirect(request.url)
            return redirect(url_for("bag_detail", bag_id=bag_id))
        return render_page("Produit du sac", """
        <section class="panel"><span class="badge">{{ s.nom }}</span><h1>{{ p.nom }}</h1>
        <p>Dans le sac : <strong>{{ bag_qty }}</strong> — Dans l’armoire : <strong>{{ armory_qty }}</strong></p>
        <form method="post"><label>Quantité</label><input name="quantity" type="number" min="1" value="1" required autofocus>
        <label>Nom du secouriste</label><input name="operator_name" autocomplete="name">
        <div class="big-choice actions">
        <button class="red" name="action" value="utilisation">➖ Produit utilisé<br><small>Le sac diminue</small></button>
        <button class="green" name="action" value="rearmement">➕ Réarmement<br><small>Armoire → sac</small></button>
        </div></form>
        <div class="actions"><a class="btn" href="{{ url_for('scanner', sac_id=s.id) }}">Scanner le produit suivant</a>
        <a class="btn gray" href="{{ url_for('bag_detail', bag_id=s.id) }}">Retour au sac</a></div></section>
        """, s=s, p=p, bag_qty=bag_qty, armory_qty=armory_qty)
    except Exception as exc:
        return render_page("Erreur", "<section class='panel'><h1>Opération impossible</h1><p>{{ error }}</p><a class='btn gray' href='javascript:history.back()'>Retour</a></section>", error=str(exc)), 500

@app.route("/historique")
def history():
    try:
        rows = api("GET", "mouvements", params={
            "select": "id,date_mouvement,type,quantite,nom_secouriste,lot_vpsp,produits(nom)",
            "order": "date_mouvement.desc", "limit": "250"
        })
        bag_rows = api("GET", "mouvements_sacs", params={
            "select": "id,date_mouvement,type,quantite,nom_secouriste,sacs(nom),produits(nom)",
            "order": "date_mouvement.desc", "limit": "250"
        })
        combined = []
        for m in rows:
            combined.append({
                "date": m.get("date_mouvement"), "produit": (m.get("produits") or {}).get("nom", "Produit"),
                "type": m.get("type"), "quantite": m.get("quantite"), "secouriste": m.get("nom_secouriste") or "—",
                "emplacement": "Armoire"
            })
        for m in bag_rows:
            combined.append({
                "date": m.get("date_mouvement"), "produit": (m.get("produits") or {}).get("nom", "Produit"),
                "type": m.get("type"), "quantite": m.get("quantite"), "secouriste": m.get("nom_secouriste") or "—",
                "emplacement": (m.get("sacs") or {}).get("nom", "Sac")
            })
        combined.sort(key=lambda x: x["date"] or "", reverse=True)
        return render_page("Historique", """
        <section class="panel"><h1>Historique commun</h1><table><thead><tr><th>Date</th><th>Produit</th><th>Action</th><th>Qté</th><th>Emplacement</th><th>Secouriste</th></tr></thead>
        <tbody>{% for m in rows %}<tr><td>{{ m.date }}</td><td>{{ m.produit }}</td><td>{{ m.type }}</td>
        <td>{{ m.quantite }}</td><td>{{ m.emplacement }}</td><td>{{ m.secouriste }}</td></tr>{% endfor %}</tbody></table></section>
        """, rows=combined[:500])
    except Exception as exc:
        return render_page("Erreur", "<section class='panel'><h1>Erreur</h1><p>{{ error }}</p></section>", error=str(exc)), 500

@app.route("/qrcodes/<int:product_id>")
def qrcodes(product_id):
    p = product(product_id)
    if not p:
        return "Produit introuvable", 404
    return render_page("QR produit", """
    <section class="panel"><h1>{{ p.nom }}</h1><p>Ce QR identifie le produit. Dans le mode mobile, l’action est choisie après le scan.</p>
    <img class="qr" src="{{ url_for('qr_product_png', product_id=p.id) }}"></section>
    """, p=p)

@app.route("/qr/produit/<int:product_id>.png")
def qr_product_png(product_id):
    return qr_response(url_for("scan_product", product_id=product_id, _external=True))

@app.route("/qrcodes/sac/<int:bag_id>")
def bag_qr(bag_id):
    s = bag(bag_id)
    if not s:
        return "Sac introuvable", 404
    return render_page("QR sac", """
    <section class="panel"><h1>{{ s.nom }}</h1><p>Collez ce QR sur le sac.</p>
    <img class="qr" src="{{ url_for('qr_bag_png', bag_id=s.id) }}"></section>
    """, s=s)

@app.route("/qr/sac/<int:bag_id>.png")
def qr_bag_png(bag_id):
    return qr_response(url_for("scan_bag", bag_id=bag_id, _external=True))

@app.route("/qr/<action>/<int:product_id>.png")
def legacy_qr_png(action, product_id):
    if action not in ("entree", "sortie"):
        return "Action inconnue", 404
    return qr_response(url_for("movement", action=action, product_id=product_id, _external=True))

def qr_response(target):
    image = qrcode.make(target)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(buffer.getvalue(), mimetype="image/png")

