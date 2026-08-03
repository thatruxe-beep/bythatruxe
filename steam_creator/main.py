# -*- coding: utf-8 -*-
"""
main.py
=======
Точка входа. Главный цикл, консольный интерфейс на русском языке.

Порядок работы:
    1. Проверка версии Python.
    2. Проверка/установка OpenVPN.
    3. Установка недостающих Python-пакетов.
    4. Приветственный баннер, выбор региона и количества аккаунтов.
    5. Цикл создания аккаунтов (VPN -> FirstMail -> Steam).
    6. Сохранение данных в accounts.txt, ошибок в errors.txt.
"""

import logging
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# --- Настройка кодировки консоли (Windows) ------------------------------
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
        os.environ['PYTHONIOENCODING'] = 'utf-8'
    except Exception:  # noqa: BLE001
        pass

# --- Пути -----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / 'app.log'

# --- Логирование (DEBUG в консоль, INFO в файл) --------------------------
logger = logging.getLogger('steam_creator')
logger.setLevel(logging.DEBUG)
fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')

_console = logging.StreamHandler()
_console.setLevel(logging.DEBUG)
_console.setFormatter(fmt)
logger.addHandler(_console)

_file = logging.FileHandler(LOG_FILE, encoding='utf-8')
_file.setLevel(logging.INFO)
_file.setFormatter(fmt)
logger.addHandler(_file)

# --- Импорт модулей проекта (после настройки логов) -----------------------
from data_generator import generate_email_data, generate_password, generate_username  # noqa: E402
from file_manager import FileManager  # noqa: E402
from vpn_manager import VPNManager  # noqa: E402

MIN_PYTHON = (3, 10)

APP_VERSION = '1.0'

# --- Требуемые пакеты для pip ----------------------------------------------
REQUIRED_PACKAGES = ['DrissionPage', 'requests', 'undetected-chromedriver']


# ========================================================================= #
# Шаг 1. Проверка Python
# ========================================================================= #
def check_python() -> bool:
    """Проверяет версию Python. Требуется 3.10+."""
    current = (sys.version_info.major, sys.version_info.minor)
    if current < MIN_PYTHON:
        logger.error(
            "Требуется Python %d.%d+, установлена версия %d.%d.",
            MIN_PYTHON[0], MIN_PYTHON[1], current[0], current[1],
        )
        input("Нажмите Enter для выхода...")
        return False
    logger.info("Версия Python: %s (ОК)", sys.version.split()[0])
    return True


# ========================================================================= #
# Шаг 2. Установка Python-пакетов
# ========================================================================= #
def _pip_install(package: str) -> bool:
    """Устанавливает один пакет через pip, без вывода окон."""
    flags = []
    if sys.platform.startswith('win'):
        flags = ['--disable-pip-version-check']
    cmd = [sys.executable, '-m', 'pip', 'install', '--quiet', package, *flags]
    try:
        logger.info("Установка пакета: %s", package)
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
        )
        return result.returncode == 0
    except Exception as exc:  # noqa: BLE001
        logger.error("Ошибка установки %s: %s", package, exc)
        return False


def install_python_packages() -> None:
    """Проверяет и доустанавливает недостающие Python-пакеты."""
    for package in REQUIRED_PACKAGES:
        # Проверяем импортируемость
        try:
            __import__(package)
            logger.info("Пакет %s уже установлен", package)
        except ImportError:
            if not _pip_install(package):
                logger.warning(
                    "Не удалось установить %s автоматически. "
                    "Выполните: pip install -r requirements.txt", package
                )


# ========================================================================= #
# Шаг 3. OpenVPN: проверка и установка
# ========================================================================= #
OPENVPN_EXE_HINTS = [
    r"C:\Program Files\OpenVPN\bin\openvpn.exe",
    r"C:\Program Files (x86)\OpenVPN\bin\openvpn.exe",
]

OPENVPN_DOWNLOAD_PAGE = 'https://openvpn.net/community-downloads/'


def _find_openvpn() -> str:
    """Ищет исполняемый файл openvpn в PATH и стандартных каталогах."""
    exe = shutil.which('openvpn')
    if exe:
        return exe
    for hint in OPENVPN_EXE_HINTS:
        if os.path.exists(hint):
            return hint
    return ''


def _fetch_openvpn_installer_url() -> str:
    """
    Получает прямую ссылку на Windows-установщик OpenVPN со страницы загрузок.

    :return: URL или '' при неудаче.
    """
    try:
        import requests
        resp = requests.get(OPENVPN_DOWNLOAD_PAGE, timeout=30)
        resp.raise_for_status()
        # Ищем ссылку на amd64 .exe установщик
        patterns = [
            r'https?://[^\s"\'<>]+openvpn-install-[\w.\-]+-amd64\.exe',
            r'openvpn-install-[\w.\-]+-amd64\.exe',
        ]
        for pat in patterns:
            match = re.search(pat, resp.text)
            if match:
                url = match.group(0)
                if url.startswith('/'):
                    url = 'https://openvpn.net' + url
                return url
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось получить ссылку на установщик: %s", exc)
    return ''


def _download_file(url: str, dest: Path) -> bool:
    """Скачивает файл по URL в dest."""
    try:
        import requests
        logger.info("Скачивание установщика OpenVPN...")
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(dest, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return dest.exists() and dest.stat().st_size > 0
    except Exception as exc:  # noqa: BLE001
        logger.error("Ошибка скачивания: %s", exc)
        return False


def install_openvpn() -> bool:
    """
    Проверяет наличие OpenVPN. Если нет — скачивает и тихо устанавливает.

    :return: True, если OpenVPN доступен.
    """
    if _find_openvpn():
        logger.info("OpenVPN найден: %s", _find_openvpn())
        return True

    logger.info("OpenVPN не найден. Начинаю установку...")
    url = _fetch_openvpn_installer_url()
    if not url:
        logger.error("Не удалось определить ссылку на установщик OpenVPN.")
        return False

    installer = BASE_DIR / 'openvpn_installer.exe'
    if not _download_file(url, installer):
        logger.error("Не удалось скачать установщик OpenVPN.")
        return False

    # Тихая установка: /S — silent
    flags = [str(installer), '/S']
    try:
        logger.info("Тихая установка OpenVPN (/S)...")
        result = subprocess.run(
            flags, capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
            timeout=600,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Ошибка запуска установщика: %s", exc)
        return False
    finally:
        try:
            installer.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass

    # Проверка установки
    for _ in range(6):
        if _find_openvpn():
            logger.info("OpenVPN успешно установлен.")
            return True
        time.sleep(3)

    logger.error("OpenVPN не установился (проверьте вручную).")
    return False


# ========================================================================= #
# Шаг 4. Консольный интерфейс
# ========================================================================= #
def print_banner() -> None:
    """Выводит приветственный баннер."""
    print("=" * 50)
    print(f"🎮 Steam Account Creator v{APP_VERSION}")
    print("=" * 50)


def ask_region() -> int:
    """Запрашивает регион и возвращает его номер."""
    while True:
        print("Выберите регион:")
        print("1 - Россия 🇷🇺")
        print("2 - Украина 🇺🇦")
        print("3 - Казахстан 🇰🇿")
        try:
            choice = int(input("Ваш выбор (1-3): ").strip())
            if choice in (1, 2, 3):
                return choice
        except ValueError:
            pass
        print("❌ Некорректный ввод. Повторите.\n")


def ask_account_count() -> int:
    """Запрашивает количество аккаунтов."""
    while True:
        try:
            count = int(input("Введите количество аккаунтов для создания: ").strip())
            if count > 0:
                return count
            print("❌ Число должно быть больше 0.")
        except ValueError:
            print("❌ Некорректное число. Повторите.")


# ========================================================================= #
# Шаг 5. Создание одного аккаунта
# ========================================================================= #
def create_account(index, total, region, vpn, fm, domains, browser,
                   wait_links_func) -> bool:
    """
    Создаёт один аккаунт: VPN -> FirstMail -> Steam.

    :return: True при полном успехе.
    """
    print(f"\n[{index}/{total}] Создание аккаунта...")

    # 1. Подключаем VPN (если ещё не подключен к нужному региону)
    if not vpn.connected or vpn.current_country != vpn.REGION_COUNTRY.get(region):
        ok, ip = _connect_with_vpn(vpn, region)
        if not ok:
            fm.write_error(index, f"Ошибка VPN: подключение не удалось")
            return False
        print(f"  ✅ VPN подключен (IP: {ip})")

    # 2. Генерация данных (отдельные пароли для почты и Steam)
    username, mail_password, email = generate_email_data(domains, used=set())
    steam_password = generate_password()
    print(f"  📧 Генерация данных для аккаунта...")

    # 3. Регистрация почты на firstmail
    from firstmail import register_email
    time.sleep(random.uniform(5, 10))  # задержка перед регистрацией почты
    mail_ok, confirmed_email = register_email(
        browser, domains, username, mail_password
    )
    if not mail_ok or not confirmed_email:
        logger.error("Аккаунт #%d - Ошибка FirstMail", index)
        fm.write_error(index, "Ошибка FirstMail: регистрация не удалась")
        return False
    print(f"  ✅ Почта создана: {confirmed_email}")

    # 4. Регистрация Steam
    from steam_reg import register_steam
    time.sleep(random.uniform(5, 10))  # задержка между почтой и Steam
    steam_ok = register_steam(
        browser, region, confirmed_email,
        username, steam_password,
        wait_links_func=lambda: wait_links_func(browser),
    )
    if not steam_ok:
        logger.error("Аккаунт #%d - Ошибка Steam", index)
        fm.write_error(index, "Ошибка Steam: регистрация не удалась")
        return False
    print(f"  ✅ Steam аккаунт создан: {username}")

    # 5. Сохраняем в очередь (в файл запишется в конце):
    #    логин_steam-пароль_steam-логин_почты-пароль_почты
    fm.add_account(username, steam_password, username, mail_password)
    print("  ✅ Аккаунт сохранен!")
    return True


def _connect_with_vpn(vpn, region) -> tuple:
    """Подключает VPN и возвращает (ok, ip)."""
    ok = vpn.connect(region)
    ip = vpn.get_current_ip() if ok else ''
    return ok, ip


def wait_links_func(browser) -> list:
    """Ожидает письмо от Steam и возвращает ссылки подтверждения."""
    from firstmail import wait_for_verification_email
    return wait_for_verification_email(
        browser, sender_hint='steam', timeout=60
    )


# ========================================================================= #
# Главная функция
# ========================================================================= #
def main() -> None:
    """Основной цикл программы."""
    print_banner()

    # 1. Python
    if not check_python():
        return

    # 2. Python-пакеты
    install_python_packages()

    # 3. OpenVPN
    if not install_openvpn():
        logger.error("OpenVPN не установлен — продолжение невозможно.")
        input("Нажмите Enter для выхода...")
        return

    # 4. Ввод параметров
    region = ask_region()
    region_name = {1: 'Россия', 2: 'Украина', 3: 'Казахстан'}[region]
    count = ask_account_count()

    print("\n" + "=" * 50)
    print(f"📍 Регион: {region_name}")
    print(f"📊 Аккаунтов для создания: {count}")
    print("=" * 50 + "\n")

    fm = FileManager()
    vpn = VPNManager()
    browser = None
    created = 0
    failed = 0

    try:
        # Браузер и список доменов
        from browser_setup import get_browser
        browser = get_browser()

        from firstmail import get_available_domains
        domains = get_available_domains(browser)

        # VPN до старта
        print("🔌 Подключение VPN...")
        ok, ip = _connect_with_vpn(vpn, region)
        if not ok:
            print("❌ Не удалось подключить VPN. Проверьте интернет.")
            return
        print(f"  ✅ VPN подключен (IP: {ip})")

        # Цикл создания
        for i in range(1, count + 1):
            time.sleep(random.uniform(10, 20))  # задержка между аккаунтами
            success = create_account(
                i, count, region, vpn, fm, domains, browser,
                lambda b=browser: wait_links_func(b),
            )
            if success:
                created += 1
            else:
                failed += 1

    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем (Ctrl+C). Сохраняю данные...")
        fm.save_accounts()
        print("📁 Данные сохранены. Выход.")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("Критическая ошибка: %s", exc)
    finally:
        # Сохраняем все аккаунты в конце
        saved = fm.save_accounts()
        if saved:
            print(f"📁 Сохранено аккаунтов: {saved}")
        # Отключаем VPN
        vpn.disconnect()
        # Закрываем браузер
        if browser is not None:
            try:
                browser.quit()
            except Exception:  # noqa: BLE001
                pass

    # Итог
    print("\n" + "=" * 50)
    print(f"✅ Готово! Создано аккаунтов: {created}/{count}")
    print(f"❌ Ошибок: {failed}")
    print(f"📁 Данные сохранены в: accounts.txt")
    print(f"📁 Ошибки сохранены в: errors.txt")
    print("=" * 50)
    input("Нажмите Enter для выхода...")


if __name__ == '__main__':
    main()
