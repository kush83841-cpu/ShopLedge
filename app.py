"""
ShopLedger - shop record book (bahi-khata)
No login - opens straight to the dashboard.
Two mirror-image sides:
  CUSTOMERS: people I sell to - their sales, payments, dues to me
  PURCHASES: people I buy from - my purchase records, payments, dues to them
"""

import os
import sqlite3
from datetime import date

from flask import (
    Flask, flash, g, redirect, render_template, request, url_for,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

DATABASE = os.path.join(app.instance_path, "shopledger.db")


# ---------- database ----------

def get_db():
    if "db" not in g:
        os.makedirs(app.instance_path, exist_ok=True)
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL DEFAULT '',
            address TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 1,
            amount REAL NOT NULL,
            paid REAL NOT NULL DEFAULT 0,
            date TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL DEFAULT '',
            address TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS purchase_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 1,
            amount REAL NOT NULL,
            paid REAL NOT NULL DEFAULT 0,
            date TEXT NOT NULL,
            FOREIGN KEY (purchase_id) REFERENCES purchases (id)
        )
        """
    )
    db.commit()


# ---------- dashboard ----------

@app.route("/")
def index():
    db = get_db()
    month = date.today().strftime("%Y-%m")

    sales_month = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM sales WHERE date LIKE ?",
        (month + "%",),
    ).fetchone()[0]

    purch_month = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM purchase_records WHERE date LIKE ?",
        (month + "%",),
    ).fetchone()[0]

    to_collect = db.execute(
        "SELECT COALESCE(SUM(amount - paid), 0) FROM sales"
    ).fetchone()[0]

    to_pay = db.execute(
        "SELECT COALESCE(SUM(amount - paid), 0) FROM purchase_records"
    ).fetchone()[0]

    debtors = db.execute(
        """
        SELECT c.id, c.name, COALESCE(SUM(s.amount - s.paid), 0) AS due
        FROM customers c JOIN sales s ON s.customer_id = c.id
        GROUP BY c.id HAVING due > 0
        ORDER BY due DESC LIMIT 5
        """
    ).fetchall()

    recent_sales = db.execute(
        """
        SELECT s.*, c.name AS customer_name FROM sales s
        JOIN customers c ON c.id = s.customer_id
        ORDER BY s.date DESC, s.id DESC LIMIT 5
        """
    ).fetchall()

    recent_purch = db.execute(
        """
        SELECT r.*, p.name AS purchase_name FROM purchase_records r
        JOIN purchases p ON p.id = r.purchase_id
        ORDER BY r.date DESC, r.id DESC LIMIT 5
        """
    ).fetchall()

    return render_template(
        "index.html",
        month=date.today().strftime("%B %Y"),
        sales_month=sales_month,
        purch_month=purch_month,
        profit=sales_month - purch_month,
        to_collect=to_collect,
        to_pay=to_pay,
        debtors=debtors,
        recent_sales=recent_sales,
        recent_purch=recent_purch,
    )


# ---------- customers ----------

@app.route("/customers")
def customers():
    db = get_db()
    q = request.args.get("q", "").strip()
    params = []
    query = """
        SELECT c.*, COALESCE(SUM(s.amount - s.paid), 0) AS due,
               COUNT(s.id) AS sales_count
        FROM customers c LEFT JOIN sales s ON s.customer_id = c.id
    """
    if q:
        query += " WHERE c.name LIKE ?"
        params.append("%" + q + "%")
    query += " GROUP BY c.id ORDER BY c.name"
    rows = db.execute(query, params).fetchall()
    return render_template("customers.html", customers=rows, q=q)


@app.route("/customers/add", methods=["POST"])
def add_customer():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    if name:
        db = get_db()
        db.execute(
            "INSERT INTO customers (name, phone, address) VALUES (?, ?, ?)",
            (name, phone, address),
        )
        db.commit()
        flash(f"Customer '{name}' added. ✅")
    return redirect(url_for("customers"))


@app.route("/customers/<int:customer_id>")
def customer_detail(customer_id):
    db = get_db()
    customer = db.execute(
        "SELECT * FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()
    if not customer:
        return redirect(url_for("customers"))
    sales = db.execute(
        "SELECT * FROM sales WHERE customer_id = ? ORDER BY date DESC, id DESC",
        (customer_id,),
    ).fetchall()
    total_due = sum(s["amount"] - s["paid"] for s in sales)
    total_bought = sum(s["amount"] for s in sales)
    return render_template(
        "customer_detail.html",
        customer=customer,
        sales=sales,
        total_due=total_due,
        total_bought=total_bought,
        today=date.today().isoformat(),
    )


@app.route("/customers/<int:customer_id>/delete", methods=["POST"])
def delete_customer(customer_id):
    db = get_db()
    db.execute("DELETE FROM sales WHERE customer_id = ?", (customer_id,))
    db.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    db.commit()
    flash("Customer deleted.")
    return redirect(url_for("customers"))


# ---------- sales ----------

@app.route("/sales/add", methods=["POST"])
def add_sale():
    customer_id = request.form.get("customer_id")
    item = request.form.get("item", "").strip()
    sale_date = request.form.get("date") or date.today().isoformat()
    try:
        quantity = float(request.form.get("quantity", 1) or 1)
        amount = float(request.form.get("amount", 0) or 0)
        paid = float(request.form.get("paid", 0) or 0)
    except ValueError:
        quantity, amount, paid = 1, 0, 0

    db = get_db()
    customer = db.execute(
        "SELECT id FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()
    if customer and item and amount > 0:
        paid = min(paid, amount)
        db.execute(
            """INSERT INTO sales (customer_id, item, quantity, amount, paid, date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (customer["id"], item, quantity, amount, paid, sale_date),
        )
        db.commit()
        flash("Sale recorded. ✅")
        return redirect(url_for("customer_detail", customer_id=customer["id"]))
    flash("Could not record sale — check the details.")
    return redirect(request.referrer or url_for("customers"))


@app.route("/sales/<int:sale_id>/pay", methods=["POST"])
def pay_sale(sale_id):
    """Record a payment received from a customer against one sale."""
    try:
        pay = float(request.form.get("pay", 0) or 0)
    except ValueError:
        pay = 0
    db = get_db()
    sale = db.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
    if sale and pay > 0:
        new_paid = min(sale["paid"] + pay, sale["amount"])
        db.execute("UPDATE sales SET paid = ? WHERE id = ?", (new_paid, sale_id))
        db.commit()
        flash(f"Payment of ₹{pay:.2f} recorded. ✅")
        return redirect(url_for("customer_detail", customer_id=sale["customer_id"]))
    return redirect(request.referrer or url_for("customers"))


@app.route("/sales/<int:sale_id>/delete", methods=["POST"])
def delete_sale(sale_id):
    db = get_db()
    sale = db.execute(
        "SELECT customer_id FROM sales WHERE id = ?", (sale_id,)
    ).fetchone()
    db.execute("DELETE FROM sales WHERE id = ?", (sale_id,))
    db.commit()
    if sale:
        return redirect(url_for("customer_detail", customer_id=sale["customer_id"]))
    return redirect(url_for("customers"))


# ---------- purchases (people I buy from) ----------

@app.route("/purchases")
def purchases():
    db = get_db()
    q = request.args.get("q", "").strip()
    params = []
    query = """
        SELECT p.*, COALESCE(SUM(r.amount - r.paid), 0) AS due,
               COUNT(r.id) AS records_count
        FROM purchases p LEFT JOIN purchase_records r ON r.purchase_id = p.id
    """
    if q:
        query += " WHERE p.name LIKE ?"
        params.append("%" + q + "%")
    query += " GROUP BY p.id ORDER BY p.name"
    rows = db.execute(query, params).fetchall()
    return render_template("purchases.html", purchases=rows, q=q)


@app.route("/purchases/add", methods=["POST"])
def add_purchase():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    if name:
        db = get_db()
        db.execute(
            "INSERT INTO purchases (name, phone, address) VALUES (?, ?, ?)",
            (name, phone, address),
        )
        db.commit()
        flash(f"Purchase '{name}' added. ✅")
    return redirect(url_for("purchases"))


@app.route("/purchases/<int:purchase_id>")
def purchase_detail(purchase_id):
    db = get_db()
    purchase = db.execute(
        "SELECT * FROM purchases WHERE id = ?", (purchase_id,)
    ).fetchone()
    if not purchase:
        return redirect(url_for("purchases"))
    records = db.execute(
        "SELECT * FROM purchase_records WHERE purchase_id = ? ORDER BY date DESC, id DESC",
        (purchase_id,),
    ).fetchall()
    total_due = sum(r["amount"] - r["paid"] for r in records)
    total_purchased = sum(r["amount"] for r in records)
    return render_template(
        "purchase_detail.html",
        purchase=purchase,
        records=records,
        total_due=total_due,
        total_purchased=total_purchased,
        today=date.today().isoformat(),
    )


@app.route("/purchases/<int:purchase_id>/delete", methods=["POST"])
def delete_purchase(purchase_id):
    db = get_db()
    db.execute("DELETE FROM purchase_records WHERE purchase_id = ?", (purchase_id,))
    db.execute("DELETE FROM purchases WHERE id = ?", (purchase_id,))
    db.commit()
    flash("Purchase deleted.")
    return redirect(url_for("purchases"))


# ---------- purchase records (each buying entry) ----------

@app.route("/purchase-records/add", methods=["POST"])
def add_purchase_record():
    purchase_id = request.form.get("purchase_id")
    item = request.form.get("item", "").strip()
    pur_date = request.form.get("date") or date.today().isoformat()
    try:
        quantity = float(request.form.get("quantity", 1) or 1)
        amount = float(request.form.get("amount", 0) or 0)
        paid = float(request.form.get("paid", 0) or 0)
    except ValueError:
        quantity, amount, paid = 1, 0, 0

    db = get_db()
    purchase = db.execute(
        "SELECT id FROM purchases WHERE id = ?", (purchase_id,)
    ).fetchone()
    if purchase and item and amount > 0:
        paid = min(paid, amount)
        db.execute(
            """INSERT INTO purchase_records (purchase_id, item, quantity, amount, paid, date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (purchase["id"], item, quantity, amount, paid, pur_date),
        )
        db.commit()
        flash("Purchase recorded. ✅")
        return redirect(url_for("purchase_detail", purchase_id=purchase["id"]))
    flash("Could not record purchase — check the details.")
    return redirect(request.referrer or url_for("purchases"))


@app.route("/purchase-records/<int:record_id>/pay", methods=["POST"])
def pay_purchase_record(record_id):
    """Record a payment I made against one purchase record."""
    try:
        pay = float(request.form.get("pay", 0) or 0)
    except ValueError:
        pay = 0
    db = get_db()
    record = db.execute(
        "SELECT * FROM purchase_records WHERE id = ?", (record_id,)
    ).fetchone()
    if record and pay > 0:
        new_paid = min(record["paid"] + pay, record["amount"])
        db.execute(
            "UPDATE purchase_records SET paid = ? WHERE id = ?", (new_paid, record_id)
        )
        db.commit()
        flash(f"Payment of ₹{pay:.2f} recorded. ✅")
        return redirect(url_for("purchase_detail", purchase_id=record["purchase_id"]))
    return redirect(request.referrer or url_for("purchases"))


@app.route("/purchase-records/<int:record_id>/delete", methods=["POST"])
def delete_purchase_record(record_id):
    db = get_db()
    record = db.execute(
        "SELECT purchase_id FROM purchase_records WHERE id = ?", (record_id,)
    ).fetchone()
    db.execute("DELETE FROM purchase_records WHERE id = ?", (record_id,))
    db.commit()
    if record:
        return redirect(url_for("purchase_detail", purchase_id=record["purchase_id"]))
    return redirect(url_for("purchases"))


# Run at import time too, so tables exist when Render/gunicorn imports the app
with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(debug=True)