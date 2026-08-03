# -*- coding: utf-8 -*-
"""
steam_reg.py
============
Автоматизация регистрации аккаунта Steam через DrissionPage.

Поток:
    1. Открыть https://store.steampowered.com/join/
    2. Ввести e-mail (первыйmail) и подтвердить его.
    3. Отметить чекбокс возраста/согласия, нажать Continue.
    4. Попытка пройти reCAPTCHA (до 3 попыток).
    5. Дождаться письма от Steam на firstmail, извлечь ссылку, кликнуть.
    6. Заполнить логин/пароль, выбрать страну по региону.
    7. Проверить успешное создание аккаунта.
"""

import logging
import random
import time

from DrissionPage import ChromiumPage

logger = logging.getLogger(__name__)

STEAM_JOIN_URL = 'https://store.steampowered.com/join/'

# Страны по регионам (для выпадающего списка страны)
REGION_COUNTRY_NAME = {
    1: 'Россия',
    2: 'Украина',
    3: 'Казахстан',
}

# Селекторы (могут меняться; при необходимости актуализировать)
SEL_EMAIL = 'input[name="email"]'
SEL_EMAIL_CONFIRM = 'input[name="reenter_email"]'
SEL_CONTINUE = 'button#createAccountButton, button[type="submit"]'
SEL_AGE_CHECKBOX = 'input[type="checkbox"]'
SEL_CAPTCHA_IFRAME = 'css:iframe[src*="recaptcha"]'

# Элементы на странице создания аккаунта (после подтверждения e-mail)
SEL_STEAM_USERNAME = 'input[name="username"]'
SEL_STEAM_PASSWORD = 'input[name="password"]'
SEL_STEAM_PASSWORD_CONFIRM = 'input[name="reenter_password"]'
SEL_COUNTRY_SELECT = 'select#country, select[name="country"]'
SEL_CREATE_BUTTON = 'button[type="submit"], button#createAccountButton'


class SteamRegistrator:
    """Регистрация аккаунта Steam."""

    def __init__(self, browser: ChromiumPage, region: int,
                 email: str) -> None:
        self.browser = browser
        self.region = region
        self.email = email

    # -- Капча ---------------------------------------------------------- #
    def _try_solve_captcha(self, max_attempts: int = 3,
                           wait_seconds: int = 45) -> bool:
        """
        Пытается пройти reCAPTCHA на Steam, до max_attempts раз.

        :return: True при успехе.
        """
        for attempt in range(1, max_attempts + 1):
            try:
                iframe = self.browser.ele(SEL_CAPTCHA_IFRAME, timeout=10)
                if not iframe:
                    logger.debug("reCAPTCHA не обнаружена на Steam")
                    return True
                frame = iframe.get_frame()
                checkbox = frame.ele('css:.recaptcha-checkbox-border', timeout=10)
                if checkbox:
                    checkbox.click()
                    time.sleep(random.uniform(3, 5))
                checked = frame.ele('css:.recaptcha-checkbox-checked',
                                    timeout=wait_seconds)
                if checked:
                    logger.info("Steam reCAPTCHA пройдена (попытка %d)", attempt)
                    return True
            except Exception as exc:  # noqa: BLE001
                logger.debug("Steam капча попытка %d: %s", attempt, exc)
            logger.warning("Steam капча: попытка %d/%d не удалась",
                           attempt, max_attempts)
        return False

    # -- Этап 1: ввод e-mail -------------------------------------------- #
    def _enter_email(self) -> bool:
        """Заполняет поля e-mail и жмёт Continue."""
        try:
            self.browser.get(STEAM_JOIN_URL)
            time.sleep(random.uniform(2, 3))

            email_field = self.browser.ele(SEL_EMAIL, timeout=20)
            if not email_field:
                logger.warning("Поле e-mail не найдено на Steam")
                return False
            email_field.input(self.email)

            confirm_field = self.browser.ele(SEL_EMAIL_CONFIRM, timeout=10)
            if confirm_field:
                confirm_field.input(self.email)

            # Чекбокс возраста/согласия, если есть
            age_box = self.browser.ele(SEL_AGE_CHECKBOX, timeout=3)
            if age_box:
                try:
                    age_box.click()
                except Exception:  # noqa: BLE001
                    pass

            continue_btn = self.browser.ele(SEL_CONTINUE, timeout=10)
            if continue_btn:
                continue_btn.click()
                return True
            logger.warning("Кнопка Continue не найдена")
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("Steam: ошибка ввода e-mail: %s", exc)
            return False

    # -- Этап 2: создание аккаунта -------------------------------------- #
    def _create_account(self, username: str, password: str) -> bool:
        """Заполняет логин/пароль/страну и создаёт аккаунт."""
        try:
            time.sleep(random.uniform(2, 4))
            user_field = self.browser.ele(SEL_STEAM_USERNAME, timeout=15)
            if user_field:
                user_field.input(username)
            else:
                logger.warning("Поле логина Steam не найдено")
                return False

            pwd = self.browser.ele(SEL_STEAM_PASSWORD, timeout=10)
            if pwd:
                pwd.input(password)
            pwd2 = self.browser.ele(SEL_STEAM_PASSWORD_CONFIRM, timeout=10)
            if pwd2:
                pwd2.input(password)

            # Выбор страны по региону
            country = REGION_COUNTRY_NAME.get(self.region, 'Россия')
            country_select = self.browser.ele(SEL_COUNTRY_SELECT, timeout=10)
            if country_select:
                country_select.select(country)

            create_btn = self.browser.ele(SEL_CREATE_BUTTON, timeout=10)
            if create_btn:
                create_btn.click()
                time.sleep(random.uniform(4, 6))
                return self._verify_account()
            logger.warning("Кнопка создания аккаунта не найдена")
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("Steam: ошибка создания аккаунта: %s", exc)
            return False

    # -- Этап 3: проверка ------------------------------------------------ #
    def _verify_account(self, timeout: int = 15) -> bool:
        """Проверяет успешное создание аккаунта."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                page_text = self.browser.ele('tag:body').text or ''
                if 'спасибо' in page_text.lower() or 'thank you' in page_text.lower():
                    return True
                # Редирект в профиль / аккаунт
                if 'steamcommunity.com' in (self.browser.url or '') and \
                   '/profiles/' not in (self.browser.url or ''):
                    return True
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1)
        return False

    # -- Полный поток --------------------------------------------------- #
    def register(self, username: str, password: str,
                 wait_links_func=None, **kwargs) -> bool:
        """
        Полная регистрация Steam-аккаунта.

        :param username:        логин Steam.
        :param password:        пароль Steam.
        :param wait_links_func: функция ожидания письма; должна вернуть
                                список ссылок из письма.
        :return: True при успехе.
        """
        # Этап 1: e-mail + капча
        if not self._enter_email():
            return False
        if not self._try_solve_captcha():
            logger.error("Steam: капча не пройдена (3 попытки)")
            return False

        # Этап 2: ждём письмо с подтверждением (до 60 сек)
        links = []
        if wait_links_func is not None:
            links = wait_links_func() or []
            if not links:
                logger.error("Steam: письмо не получено (timeout 60s)")
                return False
            # Кликаем первую подходящую ссылку подтверждения
            clicked = self._open_verification_link(links)
            if not clicked:
                logger.error("Steam: ссылка подтверждения не открыта")
                return False

        # Этап 3: создание аккаунта
        return self._create_account(username, password)

    def _open_verification_link(self, links: list) -> bool:
        """Открывает ссылку подтверждения почты Steam."""
        for link in links:
            try:
                if 'store.steampowered.com' in link or 'steampowered.com' in link:
                    self.browser.get(link)
                    time.sleep(random.uniform(3, 5))
                    return True
            except Exception as exc:  # noqa: BLE001
                logger.debug("Ссылка не открылась: %s", exc)
        return False


# ---------------------------------------------------------------------- #
# Удобная функция для main
# ---------------------------------------------------------------------- #
def register_steam(browser: ChromiumPage, region: int, email: str,
                   username: str, password: str, wait_links_func=None) -> bool:
    """
    Обёртка регистрации Steam.

    :return: True при успехе.
    """
    reg = SteamRegistrator(browser, region, email)
    return reg.register(username, password, wait_links_func=wait_links_func)
