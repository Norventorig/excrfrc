from pathlib import Path
import requests
from zipfile import ZipFile
import subprocess
import tempfile


SEVEN_ZIP = Path(r"C:\Program Files\7-Zip\7z.exe")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_ARCHIVE_PATH = DATA_DIR / "source_raw.zip"
RESULT_ARCHIVE_PATH = DATA_DIR / "result_archive.rar"
EXTRACT_DIR = DATA_DIR / "extracted"

ARCHIVE_URL = (
    "https://github.com/Assnova/Ucheb_Pr_Fin/raw/refs/heads/main/"
    "%D0%9F%D0%A0%D0%9E%D0%93%D0%95%D0%A0%D0%AB/"
    "%D0%9F%D1%80%D0%B8%D0%BB_%D0%9E%D0%97_"
    "%D0%9A%D0%98%D0%9C_09.02.07-2-2027.zip"
)

TARGET_MEMBER = (
    'ПА/Задание 1/Прил_2_ОЗ_КИМ_09.02.07-2-2027.rar'
)

def download_archive() -> None:
    """Скачать ZIP-архив."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Скачивание архива...")

    with requests.get(
        ARCHIVE_URL,
        stream=True,
        timeout=60,
    ) as response:
        response.raise_for_status()

        with RAW_ARCHIVE_PATH.open("wb") as file:
            file.write(response.content)

    print(f"Архив сохранён: {RAW_ARCHIVE_PATH}")


def extract_archive() -> None:
    """Извлечь вложенный RAR в папку extracted."""
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

    if not SEVEN_ZIP.exists():
        raise FileNotFoundError(
            f"Не найден 7-Zip: {SEVEN_ZIP}. "
            "Проверь путь к 7z.exe."
        )

    print("Чтение вложенного архива...")

    with ZipFile(RAW_ARCHIVE_PATH, "r") as archive:
        rar_bytes = archive.read(TARGET_MEMBER)

    with tempfile.TemporaryDirectory() as temp_dir:
        rar_path = Path(temp_dir) / "archive.rar"
        rar_path.write_bytes(rar_bytes)

        print("Распаковка RAR...")

        result = subprocess.run(
            [
                str(SEVEN_ZIP),
                "x",
                str(rar_path),
                f"-o{EXTRACT_DIR}",
                "-y",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Не удалось распаковать RAR.\n"
                f"Код ошибки: {result.returncode}\n"
                f"{result.stdout}\n{result.stderr}"
            )

    print(f"Архив распакован в: {EXTRACT_DIR}")


def main() -> None:
    download_archive()
    extract_archive()


if __name__ == "__main__":
    main()