import os
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask, abort, flash, g, redirect, render_template,
    request, session, url_for, send_file
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE = Path(os.environ.get("CHUDO_DB_PATH", BASE_DIR / "data" / "app.db"))
ICON = BASE_DIR / "data" / "extracted" / "Чудо Обувь.png"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-secret-key-for-local-use")
app.config["DATABASE"] = str(DATABASE)


@app.route("/product-image")
def product_image():
    """Return an absolute image path only when it is referenced by a product in the DB."""
    image_path = request.args.get("path", "").strip()
    if not image_path or not os.path.isabs(image_path):
        abort(404)

    # Do not let a URL be used to read arbitrary files from the server.
    registered_paths = get_db().execute(
        "SELECT image FROM products WHERE image IS NOT NULL AND TRIM(image) <> ''"
    ).fetchall()
    requested_key = os.path.normcase(os.path.normpath(image_path))
    allowed = {
        os.path.normcase(os.path.normpath(str(row["image"]).strip()))
        for row in registered_paths
        if row["image"] and os.path.isabs(str(row["image"]).strip())
    }
    if requested_key not in allowed or not os.path.isfile(image_path):
        abort(404)

    return send_file(image_path, conditional=True)


@app.route("/site-icon")
def site_icon():
    if not ICON.is_file():
        abort(404)

    return send_file(ICON, mimetype="image/png")


@app.route("/brand-icon")
def brand_icon():
    if not ICON.is_file():
        abort(404)

    return send_file(ICON, mimetype="image/png")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def table_columns(table):
    rows = get_db().execute(f'PRAGMA table_info("{table}")').fetchall()
    return {row["name"] for row in rows}


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_db().execute(
        "SELECT user_id, surname, name, patronymic, login, role FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


def roles_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None:
                flash("Сначала войдите в систему.", "warning")
                return redirect(url_for("login", next=request.path))
            role = str(user["role"]).strip().lower()
            aliases = {
                "администратор": "admin", "administrator": "admin", "admin": "admin",
                "менеджер": "manager", "manager": "manager",
                "авторизованный пользователь": "user", "пользователь": "user",
                "user": "user", "customer": "user",
            }
            normalized = aliases.get(role, role)
            if normalized not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def is_staff(user=None):
    user = user or current_user()
    if not user:
        return False
    role = str(user["role"]).strip().lower()
    return role in {
        "admin", "manager", "администратор", "менеджер", "administrator"
    }


def cart_from_session():
    # Ключ корзины: "product_id:size", значение: количество пар.
    return session.get("cart", {})


def get_cart_items():
    db = get_db()
    items = []
    total = 0
    for key, quantity in cart_from_session().items():
        try:
            product_id_str, size_str = key.split(":", 1)
            product_id, size = int(product_id_str), float(size_str)
            quantity = int(quantity)
        except (ValueError, TypeError):
            continue
        row = db.execute("""
            SELECT p.product_id, p.name, p.image, p.price, s.size,
                   s.available_amount
            FROM products p
            JOIN stocks s ON s.product_id = p.product_id
            WHERE p.product_id = ? AND s.size = ?
        """, (product_id, size)).fetchone()
        if row:
            item_total = int(row["price"]) * quantity
            items.append({
                "key": key, "product": row, "quantity": quantity,
                "item_total": item_total,
            })
            total += item_total
    return items, total


@app.route("/")
def catalog():
    db = get_db()
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    size = request.args.get("size", "").strip()
    sort = request.args.get("sort", "name")
    where, params = [], []
    if query:
        where.append("p.name LIKE ?")
        params.append(f"%{query}%")
    if category:
        where.append("p.category = ?")
        params.append(category)
    if size:
        try:
            float(size)
            where.append("EXISTS (SELECT 1 FROM stocks sx WHERE sx.product_id = p.product_id AND sx.size = ? AND sx.available_amount > 0)")
            params.append(float(size))
        except ValueError:
            flash("Укажите корректный размер.", "warning")

    order_by = {
        "name": "p.name COLLATE NOCASE",
        "price_asc": "p.price ASC",
        "price_desc": "p.price DESC",
    }.get(sort, "p.name COLLATE NOCASE")
    clause = " WHERE " + " AND ".join(where) if where else ""
    products = db.execute(f"""
        SELECT p.* FROM products p {clause}
        ORDER BY {order_by}
    """, params).fetchall()

    result = []
    for product in products:
        sizes = db.execute("""
            SELECT size, available_amount FROM stocks
            WHERE product_id = ? AND available_amount > 0
            ORDER BY size
        """, (product["product_id"],)).fetchall()
        result.append({"product": product, "sizes": sizes})

    categories = db.execute(
        "SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category"
    ).fetchall()
    return render_template(
        "catalog.html", products=result, categories=categories,
        q=query, selected_category=category, selected_size=size, sort=sort
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_value = request.form.get("login", "").strip()
        user = get_db().execute(
            "SELECT user_id, login, role FROM users WHERE login = ?",
            (login_value,),
        ).fetchone()
        if user:
            session.clear()
            session["user_id"] = user["user_id"]
            session["cart"] = {}
            flash("Вы вошли в систему.", "success")
            next_url = request.args.get("next", "")
            # Не перенаправляем на внешний сайт.
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("catalog"))
        flash("Такой логин не найден в списке пользователей.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("catalog"))


@app.route("/cart")
def cart():
    items, total = get_cart_items()
    return render_template("cart.html", items=items, total=total)


@app.route("/cart/add", methods=["POST"])
@roles_required("user", "manager", "admin")
def add_to_cart():
    try:
        product_id = int(request.form["product_id"])
        size = float(request.form["size"])
        quantity = int(request.form.get("quantity", "1"))
        if quantity < 1:
            raise ValueError
    except (KeyError, ValueError):
        flash("Проверьте размер и количество.", "danger")
        return redirect(url_for("catalog"))

    stock = get_db().execute("""
        SELECT available_amount FROM stocks
        WHERE product_id = ? AND size = ?
    """, (product_id, size)).fetchone()
    if stock is None or stock["available_amount"] < 1:
        flash("Этот размер сейчас недоступен.", "danger")
        return redirect(url_for("catalog"))

    cart_data = cart_from_session().copy()
    key = f"{product_id}:{size:g}"
    new_quantity = int(cart_data.get(key, 0)) + quantity
    if new_quantity > stock["available_amount"]:
        flash(f"Доступно пар: {stock['available_amount']}.", "warning")
        return redirect(url_for("catalog"))
    cart_data[key] = new_quantity
    session["cart"] = cart_data
    flash("Товар добавлен в корзину.", "success")
    return redirect(url_for("cart"))


@app.route("/cart/update", methods=["POST"])
@roles_required("user", "manager", "admin")
def update_cart():
    key = request.form.get("key", "")
    try:
        quantity = int(request.form.get("quantity", "1"))
        product_id_str, size_str = key.split(":", 1)
        product_id, size = int(product_id_str), float(size_str)
        if quantity < 1:
            raise ValueError
    except ValueError:
        flash("Количество должно быть целым числом больше нуля.", "danger")
        return redirect(url_for("cart"))

    stock = get_db().execute("""
        SELECT available_amount FROM stocks WHERE product_id = ? AND size = ?
    """, (product_id, size)).fetchone()
    if not stock or quantity > stock["available_amount"]:
        flash("Указанное количество превышает остаток.", "warning")
        return redirect(url_for("cart"))
    data = cart_from_session().copy()
    data[key] = quantity
    session["cart"] = data
    return redirect(url_for("cart"))


@app.route("/cart/remove", methods=["POST"])
@roles_required("user", "manager", "admin")
def remove_from_cart():
    key = request.form.get("key", "")
    data = cart_from_session().copy()
    data.pop(key, None)
    session["cart"] = data
    flash("Позиция удалена из корзины.", "info")
    return redirect(url_for("cart"))


@app.route("/checkout", methods=["POST"])
@roles_required("user", "manager", "admin")
def checkout():
    user = current_user()
    db = get_db()
    cart_data = cart_from_session()
    if not cart_data:
        flash("Корзина пуста.", "warning")
        return redirect(url_for("cart"))

    # Сохраняем все позиции и списываем остатки в одной транзакции.
    try:
        db.execute("BEGIN IMMEDIATE")
        order_id = db.execute(
            "SELECT COALESCE(MAX(order_id), 0) + 1 FROM orders"
        ).fetchone()[0]
        next_item_id = 1
        date_value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for key, raw_quantity in cart_data.items():
            product_id_str, size_str = key.split(":", 1)
            product_id, size = int(product_id_str), float(size_str)
            quantity = int(raw_quantity)
            stock = db.execute("""
                SELECT available_amount FROM stocks
                WHERE product_id = ? AND size = ?
            """, (product_id, size)).fetchone()
            if stock is None or quantity < 1 or quantity > stock["available_amount"]:
                raise ValueError("Остатки изменились. Проверьте корзину и попробуйте снова.")

            db.execute("""
                INSERT INTO orders
                    (order_id, date, size, amount, user_id, product_id, order_item_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (order_id, date_value, size, quantity, user["user_id"],
                  product_id, next_item_id))
            db.execute("""
                UPDATE stocks SET available_amount = available_amount - ?
                WHERE product_id = ? AND size = ?
            """, (quantity, product_id, size))
            next_item_id += 1

        db.commit()
        session["cart"] = {}
        flash(f"Заказ №{order_id} успешно оформлен.", "success")
        return redirect(url_for("orders"))
    except (ValueError, sqlite3.Error) as exc:
        db.rollback()
        flash(str(exc) or "Не удалось оформить заказ.", "danger")
        return redirect(url_for("cart"))


@app.route("/orders")
@roles_required("manager", "admin", "user")
def orders():
    user = current_user()
    db = get_db()
    if is_staff(user):
        rows = db.execute("""
            SELECT o.order_id, MIN(o.date) AS date, o.user_id,
                   u.surname, u.name, u.patronymic,
                   SUM(o.amount * p.price) AS total,
                   COUNT(*) AS positions
            FROM orders o
            JOIN users u ON u.user_id = o.user_id
            JOIN products p ON p.product_id = o.product_id
            GROUP BY o.order_id, o.user_id, u.surname, u.name, u.patronymic
            ORDER BY MIN(o.date) DESC, o.order_id DESC
        """).fetchall()
    else:
        rows = db.execute("""
            SELECT o.order_id, MIN(o.date) AS date, o.user_id,
                   u.surname, u.name, u.patronymic,
                   SUM(o.amount * p.price) AS total,
                   COUNT(*) AS positions
            FROM orders o
            JOIN users u ON u.user_id = o.user_id
            JOIN products p ON p.product_id = o.product_id
            WHERE o.user_id = ?
            GROUP BY o.order_id, o.user_id, u.surname, u.name, u.patronymic
            ORDER BY MIN(o.date) DESC, o.order_id DESC
        """, (user["user_id"],)).fetchall()
    return render_template("orders.html", orders=rows, staff=is_staff(user))


@app.route("/orders/<int:order_id>")
@roles_required("manager", "admin", "user")
def order_detail(order_id):
    user = current_user()
    db = get_db()
    order_user = db.execute(
        "SELECT user_id FROM orders WHERE order_id = ? LIMIT 1", (order_id,)
    ).fetchone()
    if not order_user:
        abort(404)
    if not is_staff(user) and order_user["user_id"] != user["user_id"]:
        abort(403)
    items = db.execute("""
        SELECT o.order_id, o.order_item_id, o.date, o.size, o.amount,
               p.product_id, p.name, p.price, p.image,
               (o.amount * p.price) AS line_total
        FROM orders o JOIN products p ON p.product_id = o.product_id
        WHERE o.order_id = ? ORDER BY o.order_item_id
    """, (order_id,)).fetchall()
    total = sum(row["line_total"] for row in items)
    return render_template(
        "order_detail.html", order_id=order_id, items=items,
        total=total, admin=str(user["role"]).strip().lower() in ("admin", "администратор", "administrator")
    )


@app.route("/orders/<int:order_id>/delete", methods=["POST"])
@roles_required("manager", "admin")
def delete_order(order_id):
    db = get_db()
    # Возвращаем удаляемые пары в остатки.
    rows = db.execute(
        "SELECT product_id, size, amount FROM orders WHERE order_id = ?",
        (order_id,),
    ).fetchall()
    if not rows:
        abort(404)
    try:
        db.execute("BEGIN IMMEDIATE")
        for row in rows:
            db.execute("""
                UPDATE stocks SET available_amount = available_amount + ?
                WHERE product_id = ? AND size = ?
            """, (row["amount"], row["product_id"], row["size"]))
        db.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
        db.commit()
        flash(f"Заказ №{order_id} удалён, остатки восстановлены.", "success")
    except sqlite3.Error:
        db.rollback()
        flash("Не удалось удалить заказ.", "danger")
    return redirect(url_for("orders"))


@app.route("/orders/<int:order_id>/edit", methods=["POST"])
@roles_required("admin")
def edit_order(order_id):
    """Администратор может изменить количество существующей позиции."""
    try:
        item_id = int(request.form["order_item_id"])
        new_amount = int(request.form["amount"])
        if new_amount < 1:
            raise ValueError
    except (KeyError, ValueError):
        flash("Количество должно быть целым числом больше нуля.", "danger")
        return redirect(url_for("order_detail", order_id=order_id))

    db = get_db()
    row = db.execute("""
        SELECT product_id, size, amount FROM orders
        WHERE order_id = ? AND order_item_id = ?
    """, (order_id, item_id)).fetchone()
    if row is None:
        abort(404)

    delta = new_amount - row["amount"]
    try:
        db.execute("BEGIN IMMEDIATE")
        if delta > 0:
            stock = db.execute("""
                SELECT available_amount FROM stocks
                WHERE product_id = ? AND size = ?
            """, (row["product_id"], row["size"])).fetchone()
            if not stock or stock["available_amount"] < delta:
                raise ValueError("На складе недостаточно товара для увеличения количества.")
            db.execute("""
                UPDATE stocks SET available_amount = available_amount - ?
                WHERE product_id = ? AND size = ?
            """, (delta, row["product_id"], row["size"]))
        elif delta < 0:
            db.execute("""
                UPDATE stocks SET available_amount = available_amount + ?
                WHERE product_id = ? AND size = ?
            """, (-delta, row["product_id"], row["size"]))
        db.execute("""
            UPDATE orders SET amount = ?
            WHERE order_id = ? AND order_item_id = ?
        """, (new_amount, order_id, item_id))
        db.commit()
        flash("Заказ обновлён.", "success")
    except (ValueError, sqlite3.Error) as exc:
        db.rollback()
        flash(str(exc) or "Не удалось обновить заказ.", "danger")
    return redirect(url_for("order_detail", order_id=order_id))


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403, message="Недостаточно прав для этого действия."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="Страница или заказ не найдены."), 404


if __name__ == "__main__":
    if not DATABASE.exists():
        print(f"ВНИМАНИЕ: файл базы данных не найден: {DATABASE}")
    app.run(debug=True)
