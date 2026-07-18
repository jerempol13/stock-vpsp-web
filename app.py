import io
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import qrcode
from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "stock_vpsp_initial.db"
DB_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "stock_vpsp.db"))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")

LOTS = [
    "Armoire", "VPSP", "Lot A – Premiers secours", "Lot A Malle",
    "Lot B – Premiers secours", "Lot C – Premiers secours",
    "Lot A – Oxygénothérapie", "Lot C – Oxygénothérapie", "Kits"
]


def ensure_database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        if DEFAULT_DB.exists():
            shutil.copy2(DEFAULT_DB, DB_PATH)
        else:
            raise RuntimeError("Base initiale introuvable")

    with sqlite3.connect(DB_PATH) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(mouvements)")}
        if "secouriste" not in columns:
            conn.execute("ALTER TABLE mouvements ADD COLUMN secouriste TEXT")
        if "date_peremption" not in columns:
            conn.execute("ALTER TABLE mouvements ADD COLUMN date_peremption TEXT")
        conn.commit()


def db():
    ensure_database()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_product(product_id):
    with db() as conn:
        return conn.execute(
            "SELECT id, nom, lot, quantite_min FROM produits WHERE id=? AND COALESCE(actif,1)=1",
            (product_id,),
        ).fetchone()


def current_stock(product_id, lot):
    with db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(quantite),0) AS total FROM stocks WHERE produit_id=? AND COALESCE(lot_vpsp,'Aucun')=?",
            (product_id, lot),
        ).fetchone()
    return int(row["total"] or 0)


@app.route("/")
def home():
    product_id = request.args.get("produit", type=int)
    if product_id:
        return redirect(url_for("sortie", product_id=product_id))

    with db() as conn:
        products = conn.execute(
            """
            SELECT p.id, p.nom, p.lot, p.quantite_min,
                   COALESCE(SUM(s.quantite),0) AS stock_total
            FROM produits p
            LEFT JOIN stocks s ON s.produit_id=p.id
            WHERE COALESCE(p.actif,1)=1
            GROUP BY p.id, p.nom, p.lot, p.quantite_min
            ORDER BY p.nom COLLATE NOCASE
            """
        ).fetchall()
    return render_template("home.html", products=products)


@app.route("/entree")
def entree_query():
    product_id = request.args.get("produit", type=int)
    if not product_id:
        flash("Le QR code ne contient pas l'identifiant du produit.", "error")
        return redirect(url_for("home"))
    return redirect(url_for("entree", product_id=product_id))


@app.route("/sortie")
def sortie_query():
    product_id = request.args.get("produit", type=int)
    if not product_id:
        flash("Le QR code ne contient pas l'identifiant du produit.", "error")
        return redirect(url_for("home"))
    return redirect(url_for("sortie", product_id=product_id))


@app.route("/entree/<int:product_id>", methods=["GET", "POST"])
def entree(product_id):
    return movement(product_id, "ENTREE")


@app.route("/sortie/<int:product_id>", methods=["GET", "POST"])
def sortie(product_id):
    return movement(product_id, "SORTIE")


def movement(product_id, movement_type):
    product = get_product(product_id)
    if not product:
        abort(404)

    selected_lot = request.form.get("lot_vpsp") or product["lot"] or "Armoire"
    stock = current_stock(product_id, selected_lot)

    if request.method == "POST":
        try:
            quantity = int(request.form.get("quantite", "0"))
        except ValueError:
            quantity = 0
        secouriste = request.form.get("secouriste", "").strip()
        expiry = request.form.get("date_peremption", "").strip() or None

        if quantity <= 0:
            flash("La quantité doit être supérieure à zéro.", "error")
        elif not secouriste:
            flash("Le nom du secouriste est obligatoire.", "error")
        elif movement_type == "SORTIE" and quantity > stock:
            flash(f"Stock insuffisant dans {selected_lot} : {stock} disponible(s).", "error")
        else:
            signed_quantity = quantity if movement_type == "ENTREE" else -quantity
            comment = f"Saisie mobile QR — {secouriste}"
            with db() as conn:
                conn.execute(
                    "INSERT INTO stocks(produit_id, lot_vpsp, quantite, date_peremption) VALUES(?,?,?,?)",
                    (product_id, selected_lot, signed_quantity, expiry if movement_type == "ENTREE" else None),
                )
                conn.execute(
                    """
                    INSERT INTO mouvements(produit_id, lot_vpsp, type, quantite, commentaire, secouriste, date_peremption)
                    VALUES(?,?,?,?,?,?,?)
                    """,
                    (product_id, selected_lot, movement_type, quantity, comment, secouriste, expiry),
                )
                conn.commit()
            new_stock = stock + signed_quantity
            action = "Entrée" if movement_type == "ENTREE" else "Sortie"
            flash(f"{action} validée. Nouveau stock dans {selected_lot} : {new_stock}.", "success")
            return redirect(url_for("success", product_id=product_id, movement_type=movement_type.lower(), lot=selected_lot))

    return render_template(
        "movement.html",
        product=product,
        movement_type=movement_type,
        lots=LOTS,
        selected_lot=selected_lot,
        stock=stock,
    )


@app.route("/succes")
def success():
    product = get_product(request.args.get("product_id", type=int))
    return render_template(
        "success.html",
        product=product,
        movement_type=request.args.get("movement_type", ""),
        lot=request.args.get("lot", ""),
    )


@app.route("/historique")
def history():
    with db() as conn:
        rows = conn.execute(
            """
            SELECT m.date_mouvement, m.type, m.quantite, m.lot_vpsp,
                   COALESCE(m.secouriste,'') AS secouriste,
                   COALESCE(m.date_peremption,'') AS date_peremption,
                   p.nom AS produit
            FROM mouvements m
            LEFT JOIN produits p ON p.id=m.produit_id
            ORDER BY m.id DESC LIMIT 300
            """
        ).fetchall()
    return render_template("history.html", rows=rows)


@app.route("/qr/<action>/<int:product_id>.png")
def qr_png(action, product_id):
    if action not in {"entree", "sortie"} or not get_product(product_id):
        abort(404)
    target = url_for(action, product_id=product_id, _external=True)
    image = qrcode.make(target)
    data = io.BytesIO()
    image.save(data, "PNG")
    data.seek(0)
    return send_file(data, mimetype="image/png", download_name=f"{action}_{product_id}.png")


@app.route("/qrcodes/<int:product_id>")
def qrcodes(product_id):
    product = get_product(product_id)
    if not product:
        abort(404)
    return render_template("qrcodes.html", product=product)


@app.route("/qrcodes.pdf")
def qrcodes_pdf():
    with db() as conn:
        products = conn.execute(
            "SELECT id, nom FROM produits WHERE COALESCE(actif,1)=1 ORDER BY nom COLLATE NOCASE"
        ).fetchall()

    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    width, height = A4
    margin = 12 * mm
    col_width = (width - 2 * margin) / 2
    block_height = 63 * mm
    qr_size = 34 * mm
    x_positions = [margin, margin + col_width]
    y = height - margin - block_height
    col = 0

    for product in products:
        if y < margin:
            pdf.showPage()
            y = height - margin - block_height
            col = 0
        x = x_positions[col]
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawCentredString(x + col_width / 2, y + 57 * mm, product["nom"][:46])

        for idx, action in enumerate(("entree", "sortie")):
            target = url_for(action, product_id=product["id"], _external=True)
            img = qrcode.make(target)
            img_io = io.BytesIO()
            img.save(img_io, "PNG")
            img_io.seek(0)
            from reportlab.lib.utils import ImageReader
            qr_x = x + (8 if idx == 0 else 49) * mm
            pdf.drawImage(ImageReader(img_io), qr_x, y + 16 * mm, qr_size, qr_size)
            pdf.setFont("Helvetica-Bold", 8)
            pdf.drawCentredString(qr_x + qr_size / 2, y + 11 * mm, "ENTRÉE" if action == "entree" else "SORTIE")
        pdf.setFont("Helvetica", 7)
        pdf.drawCentredString(x + col_width / 2, y + 5 * mm, f"Produit ID {product['id']}")

        col += 1
        if col == 2:
            col = 0
            y -= block_height

    pdf.save()
    output.seek(0)
    return send_file(output, mimetype="application/pdf", download_name="QR_Entrees_Sorties_VPSP.pdf")


@app.route("/health")
def health():
    return {"status": "ok", "database": str(DB_PATH)}


ensure_database()
