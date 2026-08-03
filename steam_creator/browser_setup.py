# -*- coding: utf-8 -*-
"""
browser_setup.py
================
Настройка DrissionPage с анти-детект параметрами.

Функция get_browser() возвращает настроенный экземпляр ChromiumPage.
Все параметры можно переопределить через переменные окружения
(DRISSION_PROXY_PORT и т.п.) — на случай прокси-обвязки.
"""

import logging
import os

from DrissionPage import ChromiumOptions, ChromiumPage

logger = logging.getLogger(__name__)

# Каталог пользовательских данных браузера (отдельный профиль)
_PROFILE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '.chrome_profile'
)


def build_options() -> ChromiumOptions:
    """
    Собирает ChromiumOptions с анти-детект аргументами.

    :return: объект ChromiumOptions.
    """
    options = ChromiumOptions()

    # Скрываем признаки автоматизации
    options.set_argument('--disable-blink-features=AutomationControlled')
    options.set_argument('--no-sandbox')
    options.set_argument('--disable-dev-shm-usage')
    options.set_argument('--disable-extensions')
    options.set_argument('--disable-infobars')

    # User-Agent (Windows 10)
    options.set_user_agent(
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )

    # Visible browser для попыток ручного решения капчи
    options.headless(False)

    # Профиль для стабильности
    options.set_user_data_path(_PROFILE_DIR)

    logger.debug("ChromiumOptions собраны")
    return options


def get_browser() -> ChromiumPage:
    """
    Создаёт и возвращает настроенный экземпляр ChromiumPage.

    :return: ChromiumPage.
    """
    options = build_options()
    browser = ChromiumPage(options)
    logger.info("Браузер запущен")
    return browser


def close_browser(browser: ChromiumPage) -> None:
    """
    Корректно закрывает браузер (если он был открыт).

    :param browser: экземпляр ChromiumPage.
    """
    try:
        if browser:
            browser.quit()
            logger.info("Браузер закрыт")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ошибка при закрытии браузера: %s", exc)
