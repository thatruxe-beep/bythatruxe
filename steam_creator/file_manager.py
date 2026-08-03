# -*- coding: utf-8 -*-
"""
file_manager.py
===============
Управление файлами: accounts.txt и errors.txt.

Формат accounts.txt:
    loginsteam-passsteam-loginmail-passmail

Формат errors.txt:
    [2024-01-15 14:30:22] Аккаунт #2 - Ошибка FirstMail: капча не пройдена

Важно:
    - accounts.txt записывается ТОЛЬКО в конце программы (и при Ctrl+C).
    - errors.txt пишется в реальном времени.
    - Кодировка — UTF-8.
"""

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# Файлы лежат рядом со скриптом
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(BASE_DIR, 'accounts.txt')
ERRORS_FILE = os.path.join(BASE_DIR, 'errors.txt')


class FileManager:
    """Класс для работы с файлами вывода."""

    def __init__(self, accounts_file: str = ACCOUNTS_FILE,
                 errors_file: str = ERRORS_FILE) -> None:
        self.accounts_file = accounts_file
        self.errors_file = errors_file
        # Накопленные аккаунты (пишутся в конце)
        self._pending_accounts: list = []

    # ------------------------------------------------------------------ #
    # Аккаунты
    # ------------------------------------------------------------------ #
    def add_account(self, login_steam: str, pass_steam: str,
                    login_mail: str, pass_mail: str) -> None:
        """
        Добавляет аккаунт в очередь на запись.

        Строка: `loginsteam-passsteam-loginmail-passmail`
        """
        line = f"{login_steam}-{pass_steam}-{login_mail}-{pass_mail}"
        self._pending_accounts.append(line)
        logger.debug("Аккаунт добавлен в очередь: %s", login_steam)

    def save_accounts(self) -> int:
        """
        Сохраняет ВСЕ накопленные аккаунты в файл (append, UTF-8).

        :return: количество записанных аккаунтов.
        """
        if not self._pending_accounts:
            logger.info("Нет аккаунтов для сохранения.")
            return 0

        written = 0
        try:
            # mode='a' — дописываем, не перезаписываем
            with open(self.accounts_file, 'a', encoding='utf-8') as f:
                for line in self._pending_accounts:
                    f.write(line + '\n')
                    written += 1
            logger.info("Сохранено аккаунтов: %d -> %s", written, self.accounts_file)
        except OSError as exc:
            logger.error("Не удалось записать accounts.txt: %s", exc)

        self._pending_accounts.clear()
        return written

    # ------------------------------------------------------------------ #
    # Ошибки (пишутся сразу)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _timestamp() -> str:
        """Возвращает текущее время в формате [YYYY-MM-DD HH:MM:SS]."""
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def write_error(self, account_number: int, message: str) -> None:
        """
        Записывает ошибку в errors.txt в реальном времени (UTF-8).

        :param account_number: номер аккаунта (например 2).
        :param message:        текст ошибки.
        """
        line = f"[{self._timestamp()}] Аккаунт #{account_number} - {message}"
        try:
            with open(self.errors_file, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
            logger.warning("Ошибка записана в errors.txt: %s", message)
        except OSError as exc:
            logger.error("Не удалось записать errors.txt: %s", exc)
