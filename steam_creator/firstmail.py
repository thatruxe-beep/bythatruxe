# -*- coding: utf-8 -*-
"""
firstmail.py
============
Автоматизация регистрации e-mail на firstmail.ltd через DrissionPage.

Поток:
    1. Открыть https://firstmail.ltd/
    2. Кликнуть кнопку регистрации.
    3. Заполнить логин, выбрать домен, ввести пароль и его подтверждение.
    4. Попытка пройти капчу (чекбокс reCAPTCHA), до 3 попыток.
    5. Отправить форму, проверить успех, вернуть адрес.

Также содержит вспомогательные функции для получения доступных доменов
и проверки входящих писем (используется модулем Steam).
"""

import logging
import random
import re
import time

from DrissionPage import ChromiumPage

logger = logging.getLogger(__name__)

FIRSTMAIL_HOME = 'https://firstmail.ltd/'

# Резервный список доменов, если парсинг страницы не удастся
DEFAULT_DOMAINS = ['firstmail.ltd']

# Селекторы (при изменении вёрстки сайта их нужно актуализировать)
SEL_SIGNUP_BUTTON = 'text=Регистрация'
SEL_USERNAME = 'input[name="username"]'
SEL_DOMAIN_SELECT = 'select[name="domain"]'
SEL_PASSWORD = 'input[name="password"]'
SEL_CONFIRM = 'input[name="confirm_password"]'
SEL_SUBMIT = 'button[type="submit"]'


# ---------------------------------------------------------------------- #
# Служебные функции
# ---------------------------------------------------------------------- #
def get_available_domains(browser: ChromiumPage = None, retries: int = 2) -> list:
    """
    Пытается получить список доступных доменов firstmail.ltd.
    Если не получилось — возвращает резервный список.

    :param browser: экземпляр ChromiumPage (опционально).
    :param retries: количество попыток.
    :return: список строк-доменов.
    """
    for _ in range(retries):
        try:
            if browser is None:
                from browser_setup import get_browser
                browser = get_browser()
                browser.get(FIRSTMAIL_HOME)
            # Ждём появления select с доменами
            if browser.ele(SEL_DOMAIN_SELECT, timeout=10):
                domains = [
                    opt.text.strip() for opt in
                    browser.ele(SEL_DOMAIN_SELECT).eles('tag:option')
                    if opt.text.strip()
                ]
                if domains:
                    logger.info("Получены домены: %s", domains)
                    return domains
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось получить домены: %s", exc)
        time.sleep(random.uniform(1, 2))
    logger.info("Используем резервный список доменов: %s", DEFAULT_DOMAINS)
    return list(DEFAULT_DOMAINS)


def _find_email_in_inbox(browser: ChromiumPage, sender_hint: str = 'steam',
                         timeout: int = 60, check_every: int = 5) -> str:
    """
    Ждёт письмо от заданного отправителя во входящих firstmail и возвращает
    его текст (сырой HTML/текст), чтобы извлечь ссылку подтверждения.

    :param browser:      экземпляр ChromiumPage.
    :param sender_hint:  фрагмент темы/отправителя (например 'steam').
    :param timeout:      максимальное время ожидания (сек).
    :param check_every:  интервал проверок (сек).
    :return: текст письма или '' при таймауте.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            browser.get(FIRSTMAIL_HOME)  # возврат на главную / обновление
            time.sleep(1)
            # Ищем элемент письма, содержащий подсказку отправителя
            mail_el = browser.ele(f'text={sender_hint}', timeout=4)
            if mail_el:
                # Кликаем на письмо
                mail_el.click()
                time.sleep(random.uniform(1, 2))
                body = browser.ele('tag:body', timeout=6)
                if body:
                    return body.html or ''
        except Exception as exc:  # noqa: BLE001
            logger.debug("Проверка почты: %s", exc)
        time.sleep(check_every)
    return ''


def extract_links_from_html(html: str) -> list:
    """
    Извлекает все URL-ссылки из HTML письма.

    :param html: HTML-содержимое письма.
    :return: список ссылок.
    """
    return re.findall(r'https?://[^\s"\'<>]+', html)


# ---------------------------------------------------------------------- #
# Регистрация
# ---------------------------------------------------------------------- #
class FirstMailRegistrator:
    """Регистрация аккаунта на firstmail.ltd."""

    def __init__(self, browser: ChromiumPage, domains: list) -> None:
        self.browser = browser
        self.domains = domains or DEFAULT_DOMAINS

    # -- Капча ---------------------------------------------------------- #
    def _try_solve_captcha(self, max_attempts: int = 3) -> bool:
        """
        Пытается пройти капчу (чекбокс reCAPTCHA), до max_attempts раз.

        :return: True, если капча успешно пройдена.
        """
        for attempt in range(1, max_attempts + 1):
            try:
                # Ждём появления iframe капчи (до 30 сек)
                iframe = self.browser.ele(
                    'css:iframe[src*="recaptcha"]', timeout=30
                )
                if not iframe:
                    logger.debug("Капча не обнаружена — продолжаем")
                    return True

                frame = iframe.get_frame()
                checkbox = frame.ele('css:.recaptcha-checkbox-border', timeout=10)
                if checkbox:
                    checkbox.click()
                    time.sleep(random.uniform(3, 5))

                # Ждём зелёную галочку (пройдено)
                checked = frame.ele('css:.recaptcha-checkbox-checked', timeout=10)
                if checked:
                    logger.info("Капча пройдена (попытка %d)", attempt)
                    return True
            except Exception as exc:  # noqa: BLE001
                logger.debug("Попытка капчи %d: %s", attempt, exc)
            logger.warning("Попытка капчи %d/%d не удалась", attempt, max_attempts)
        return False

    # -- Основной поток ------------------------------------------------- #
    def register(self, username: str, password: str) -> tuple:
        """
        Выполняет регистрацию аккаунта на firstmail.ltd.

        :param username: желаемый логин.
        :param password: пароль.
        :return: кортеж (success: bool, email: str|None)
        """
        try:
            self.browser.get(FIRSTMAIL_HOME)

            # 1. Клик по кнопке регистрации
            signup = self.browser.ele(SEL_SIGNUP_BUTTON, timeout=15)
            if not signup:
                logger.warning("Кнопка регистрации не найдена")
                return False, None
            signup.click()
            time.sleep(random.uniform(1, 2))

            # 2. Логин
            user_field = self.browser.ele(SEL_USERNAME, timeout=10)
            if user_field:
                user_field.input(username)

            # 3. Выбор случайного домена
            domain_select = self.browser.ele(SEL_DOMAIN_SELECT, timeout=10)
            if domain_select:
                domain = random.choice(self.domains)
                domain_select.select(domain)

            # 4-5. Пароль и подтверждение
            pwd = self.browser.ele(SEL_PASSWORD, timeout=10)
            if pwd:
                pwd.input(password)
            confirm = self.browser.ele(SEL_CONFIRM, timeout=10)
            if confirm:
                confirm.input(password)

            # 6. Капча
            if not self._try_solve_captcha():
                logger.error("FirstMail: капча не пройдена")
                return False, None

            # 7. Отправка формы
            submit = self.browser.ele(SEL_SUBMIT, timeout=10)
            if submit:
                submit.click()

            # 8. Проверка успеха (редирект или сообщение об успехе)
            time.sleep(random.uniform(4, 6))
            success = self._verify_success(username)
            if not success:
                logger.warning("FirstMail: не подтверждён успех регистрации")
                return False, None

            # 9. Формируем адрес
            domain = self._detect_chosen_domain() or random.choice(self.domains)
            email = f"{username}@{domain}"
            logger.info("Почта создана: %s", email)
            return True, email

        except Exception as exc:  # noqa: BLE001
            logger.error("FirstMail: исключение при регистрации: %s", exc)
            return False, None

    # -- Проверки ------------------------------------------------------- #
    def _verify_success(self, username: str, timeout: int = 15) -> bool:
        """
        Проверяет успешность регистрации по URL или содержимому страницы.

        :return: True при успехе.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                url = self.browser.url or ''
                page_text = self.browser.ele('tag:body').text or ''
                if username in page_text or 'успешн' in page_text.lower():
                    return True
                if 'inbox' in url or '/mail/' in url:
                    return True
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1)
        return False

    def _detect_chosen_domain(self) -> str:
        """Пытается определить выбранный домен из текущего URL/контекста."""
        try:
            url = self.browser.url or ''
            match = re.search(r'@([a-z0-9.-]+\.[a-z]{2,})', url)
            if match:
                return match.group(1)
        except Exception:  # noqa: BLE001
            pass
        return ''


# ---------------------------------------------------------------------- #
# Удобные функции для внешнего использования
# ---------------------------------------------------------------------- #
def register_email(browser: ChromiumPage, domains: list,
                   username: str, password: str) -> tuple:
    """
    Обёртка регистрации почты.

    :return: (success: bool, email: str|None)
    """
    reg = FirstMailRegistrator(browser, domains)
    return reg.register(username, password)


def wait_for_verification_email(browser: ChromiumPage, sender_hint: str,
                                timeout: int = 60) -> list:
    """
    Ждёт письмо и возвращает ссылки из него.

    :return: список ссылок (пустой при таймауте).
    """
    html = _find_email_in_inbox(browser, sender_hint, timeout)
    return extract_links_from_html(html)
