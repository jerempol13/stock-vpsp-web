import os
import io
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, abort
import qrcode

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
DATABASE = os.environ.get("DATABASE_PATH", "stock.db")


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            reference TEXT,
            stock INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            movement_type TEXT NOT NULL CHECK(movement_type IN ('entree', 'sortie')),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            operator_name TEXT,
            lot_number TEXT,
            expiry_date TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
        """)


@app.context_processor
def inject_now():
    return {"now": datetime.now()}


@app.route("/")
def index():
    with get_db() as conn:
        products = conn.execute(
            "SELECT * FROM products ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return render_template("index.html", products=products)


@app.route("/produits/ajouter", methods=["GET", "POST"])
def add_product():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        reference = request.form.get("reference", "").strip()
        initial_stock_raw = request.form.get("initial_stock", "0").strip()

        if not name:
            flash("Le nom du produit est obligatoire.", "error")
            return render_template("add_product.html")

        try:
            initial_stock = int(initial_stock_raw)
            if initial_stock < 0:
                raise ValueError
        except ValueError:
            flash("Le stock initial doit être un nombre entier positif.", "error")
            return render_template("add_product.html")

        try:
            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO products (name, reference, stock, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (name, reference, initial_stock, datetime.now().isoformat(timespec="seconds"))
                )
            flash("Produit ajouté.", "success")
            return redirect(url_for("index"))
        except sqlite3.IntegrityError:
            flash("Un produit avec ce nom existe déjà.", "error")

    return render_template("add_product.html")


@app.route("/entree")
def entree_without_product():
    return render_template(
        "movement.html",
        action="entree",
        title="Entrée de stock",
        product=None
    )


@app.route("/sortie")
def sortie_without_product():
    return render_template(
        "movement.html",
        action="sortie",
        title="Sortie de stock",
        product=None
    )


@app.route("/entree/<int:product_id>", methods=["GET", "POST"])
def entree(product_id):
    return handle_movement(product_id, "entree")


@app.route("/sortie/<int:product_id>", methods=["GET", "POST"])
def sortie(product_id):
    return handle_movement(product_id, "sortie")


def handle_movement(product_id, action):
    with get_db() as conn:
        product = conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()

    if not product:
        abort(404)

    if request.method == "POST":
        quantity_raw = request.form.get("quantity", "").strip()
        operator_name = request.form.get("operator_name", "").strip()
        lot_number = request.form.get("lot_number", "").strip()
        expiry_date = request.form.get("expiry_date", "").strip()

        try:
            quantity = int(quantity_raw)
            if quantity <= 0:
                raise ValueError
        except ValueError:
            flash("La quantité doit être un nombre entier supérieur à zéro.", "error")
            return render_template(
                "movement.html",
                action=action,
                title="Entrée de stock" if action == "entree" else "Sortie de stock",
                product=product
            )

        with get_db() as conn:
            current = conn.execute(
                "SELECT stock FROM products WHERE id = ?", (product_id,)
            ).fetchone()

            if action == "sortie" and quantity > current["stock"]:
                flash(
                    f"Stock insuffisant : seulement {current['stock']} unité(s) disponible(s).",
                    "error"
                )
                return render_template(
                    "movement.html",
                    action=action,
                    title="Sortie de stock",
                    product=product
                )

            new_stock = current["stock"] + quantity if action == "entree" else current["stock"] - quantity

            conn.execute(
                "UPDATE products SET stock = ? WHERE id = ?",
                (new_stock, product_id)
            )
            conn.execute(
                """
                INSERT INTO movements
                (product_id, movement_type, quantity, operator_name, lot_number, expiry_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_id,
                    action,
                    quantity,
                    operator_name,
                    lot_number,
                    expiry_date,
                    datetime.now().isoformat(timespec="seconds")
                )
            )

        label = "Entrée" if action == "entree" else "Sortie"
        flash(f"{label} enregistrée. Nouveau stock : {new_stock}.", "success")
        return redirect(url_for("index"))

    return render_template(
        "movement.html",
        action=action,
        title="Entrée de stock" if action == "entree" else "Sortie de stock",
        product=product
    )


@app.route("/historique")
def history():
    with get_db() as conn:
        movements = conn.execute("""
            SELECT m.*, p.name AS product_name, p.reference AS product_reference
            FROM movements m
            JOIN products p ON p.id = m.product_id
            ORDER BY m.created_at DESC, m.id DESC
            LIMIT 500
        """).fetchall()
    return render_template("history.html", movements=movements)


@app.route("/qr/<action>/<int:product_id>.png")
def qr_code(action, product_id):
    if action not in {"entree", "sortie"}:
        abort(404)

    with get_db() as conn:
        product = conn.execute(
            "SELECT id FROM products WHERE id = ?", (product_id,)
        ).fetchone()

    if not product:
        abort(404)

    target_url = url_for(action, product_id=product_id, _external=True)
    image = qrcode.make(target_url)
    output = io.BytesIO()
    image.save(output, format="PNG")
    output.seek(0)

    return send_file(
        output,
        mimetype="image/png",
        download_name=f"qr_{action}_{product_id}.png"
    )


@app.route("/produit/<int:product_id>/qrcodes")
def product_qrcodes(product_id):
    with get_db() as conn:
        product = conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()

    if not product:
        abort(404)

    return render_template("qrcodes.html", product=product)


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
