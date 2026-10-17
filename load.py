import sqlite3
from pathlib import Path
import pandas as pd

from transform import (
    get_products,
    get_users,
    get_orders,
    get_stocks,
)


DB_PATH = Path(__file__).resolve().parent / "data" / "app.db"

DATAFRAMES = {
    "products": get_products,
    "users": get_users,
    "orders": get_orders,
    "stocks": get_stocks,
}

TABLES_SQL = {
    "products": """
        CREATE TABLE IF NOT EXISTS products (
            "category" TEXT NOT NULL,
            "subcategory" TEXT NOT NULL,
            "image" TEXT NOT NULL,
            "name" TEXT NOT NULL,
            "manufactory" TEXT NOT NULL,
            "description" TEXT NOT NULL,
            "composition" TEXT NOT NULL,
            "price" INTEGER NOT NULL,
            "product_id" INTEGER NOT NULL PRIMARY KEY
        );
    """,

    "users": """
        CREATE TABLE IF NOT EXISTS users (
            "surname" TEXT,
            "name" TEXT,
            "patronymic" TEXT,
            "login" TEXT NOT NULL UNIQUE,
            "role" TEXT NOT NULL,
            "user_id" INTEGER NOT NULL PRIMARY KEY
        );
    """,

    "orders": """
        CREATE TABLE IF NOT EXISTS orders (
            "order_id" INTEGER NOT NULL,
            "date" TEXT NOT NULL,
            "size" INTEGER NOT NULL,
            "amount" INTEGER NOT NULL,
            "user_id" INTEGER NOT NULL,
            "product_id" INTEGER NOT NULL,
            "order_item_id" INTEGER NOT NULL,

            PRIMARY KEY ("order_id", "order_item_id"),

            FOREIGN KEY ("user_id")
                REFERENCES users ("user_id"),

            FOREIGN KEY ("product_id")
                REFERENCES products ("product_id")
        );
    """,

    "stocks": """
        CREATE TABLE IF NOT EXISTS stocks (
            "size" REAL NOT NULL,
            "available_amount" INTEGER NOT NULL,
            "name" TEXT NOT NULL,
            "product_id" INTEGER NOT NULL,
            "stock_id" INTEGER NOT NULL PRIMARY KEY,

            FOREIGN KEY ("product_id")
                REFERENCES products ("product_id")
        );
    """
}


def main() -> None:
    """Создаёт таблицы и загружает в них данные из DataFrame."""

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as connection:
        for table_name, df in DATAFRAMES.items():
            df = df()

            connection.execute(
                f'DROP TABLE IF EXISTS "{table_name}"'
            )

            connection.execute(
                TABLES_SQL[table_name]
            )

            df.to_sql(
                table_name,
                connection,
                if_exists="append",
                index=False,
            )

            print(f"{table_name}: загружено {len(df)} строк")


if __name__ == "__main__":
    main()
