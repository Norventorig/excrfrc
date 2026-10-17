from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data" / "extracted"
IMAGES_DIR = DATA_DIR / "images"

FILES = {
    "products": "Products_import.xlsx",
    "users": "Users_import.xlsx",
    "orders": "Orders_import.xlsx",
    "stocks": "Stock_Items_import.xlsx",
}

PRODUCT_COLUMNS = {
    "Категория": "category",
    "Подкатегория": "subcategory",
    "Изображение": "image",
    "Наименование товара": "name",
    "Производство": "manufactory",
    "Описание": "description",
    "Состав": "composition",
    "Цена": "price",
}

USER_COLUMNS = {
    "Фамилия": "surname",
    "Имя": "name",
    "Отчетсво": "patronymic",
    "Логин": "login",
    "Роль": "role",
}

ORDER_COLUMNS = {
    "Номер заказа": "order_id",
    "Дата заказа": "date",
    "Размер": "size",
    "Количество": "amount",
}

STOCK_COLUMNS = {
    "Размер": "size",
    "Количество доступное для заказа": "available_amount",
}


def validate_files() -> None:
    """Проверяет наличие всех необходимых исходных файлов."""
    missing_files = [
        filename
        for filename in FILES.values()
        if not (DATA_DIR / filename).is_file()
    ]

    if missing_files:
        missing = "\n".join(missing_files)
        raise FileNotFoundError(
            f"В директории {DATA_DIR} отсутствуют файлы:\n{missing}"
        )


def read_source(filename: str) -> pd.DataFrame:
    """Читает Excel-файл из директории с исходными данными."""
    path = DATA_DIR / filename

    if not path.is_file():
        raise FileNotFoundError(f"Файл не найден: {path}")

    return pd.read_excel(path)


def clean_strings(df: pd.DataFrame) -> pd.DataFrame:
    """Удаляет лишние пробелы и нормализует пробельные символы."""
    df = df.copy()

    string_columns = df.select_dtypes(
        include=["object", "string"]
    ).columns

    df[string_columns] = df[string_columns].apply(
        lambda col: col.str.replace(r"\s+", " ", regex=True).str.strip()
    )

    return df


def get_users() -> pd.DataFrame:
    """Возвращает обработанный справочник пользователей."""
    users = clean_strings(read_source(FILES["users"]))
    users.rename(columns=USER_COLUMNS, inplace=True)

    users = users.reset_index(drop=True)
    users["user_id"] = users.index

    return users


def get_products() -> pd.DataFrame:
    """Возвращает обработанный справочник товаров."""
    products = clean_strings(read_source(FILES["products"]))
    products.rename(columns=PRODUCT_COLUMNS, inplace=True)

    products = products.reset_index(drop=True)
    products["product_id"] = products.index

    products["image"] = (products["image"].apply(
        lambda image_name: str(IMAGES_DIR / image_name))
    )

    products.loc[
        products["name"] == "Черные туфли в классическом стиле — база для деловых образов",
        "name"
    ] = "Черные туфли в классическом стиле"

    return products


def get_orders() -> pd.DataFrame:
    """Возвращает pd.DataFrame обработанного Orders_import.xlsx"""

    orders = read_source(FILES["orders"])

    orders['Наименование товара'] = orders['Наименование товара'].str.replace(r'\s+', ' ', regex=True).str.strip()

    users = get_users()
    products = get_products()

    users['ФИО'] = (
            users['surname'] + ' ' +
            users['name'] + ' ' +
            users['patronymic']
    )

    orders = orders.merge(
        users[['ФИО', 'user_id']],
        on='ФИО',
        how='left'
    )

    orders = orders.merge(
        products[['name', 'product_id']],
        left_on='Наименование товара',
        right_on='name',
        how='left'
    )

    orders.drop(
        columns=['ФИО', 'Наименование товара', 'name', 'Категория', 'Производство', 'Цена за единицу'],
        inplace=True
    )

    orders['order_item_id'] = orders.groupby('Номер заказа').cumcount() + 1

    columns = {
        "Номер заказа": "order_id",
        "Дата заказа": "date",
        'Размер': "size",
        'Количество': "amount"
    }

    orders.rename(
        columns=columns,
        inplace=True,
    )

    return orders


def get_stocks() -> pd.DataFrame:
    """Возвращает остатки товаров с ID товаров."""
    stocks = clean_strings(read_source(FILES["stocks"]))

    stocks['Наименование товара'] = stocks['Наименование товара'].str.replace(r'\s+', ' ', regex=True).str.strip()

    products = get_products()

    stocks = stocks.merge(
        products[['name', 'product_id']],
        left_on='Наименование товара',
        right_on='name',
        how='left'
    )

    stocks.drop(
        columns=['Наименование товара', 'Производство'],
        inplace=True
    )

    columns = {
        'Размер': "size",
        'Количество доступное для заказа': "available_amount"
    }

    stocks.rename(
        columns=columns,
        inplace=True,
    )
    stocks = stocks.reset_index(drop=True)

    stocks['stock_id'] = stocks.index

    return stocks


if __name__ == "__main__":
    validate_files()
