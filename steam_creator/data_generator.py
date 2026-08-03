# -*- coding: utf-8 -*-
"""
data_generator.py
=================
Генератор данных: пароли, логины (Steam), данные e-mail.
Не требует внешних API — используются встроенные словари.

Функции:
    generate_password() -> str
    generate_username() -> str
    generate_email_data(domains, used) -> tuple[str, str, str]
"""

import random
import string

# --- Словари для генерации логинов -----------------------------------------

ADJECTIVES = [
    'dark', 'fire', 'ice', 'steel', 'iron', 'night', 'wild', 'swift',
    'cold', 'storm', 'shadow', 'silver', 'black', 'red', 'blue', 'gold',
    'ghost', 'dead', 'cyber', 'neon',
]

NOUNS = [
    'wolf', 'eagle', 'tiger', 'dragon', 'blade', 'hawk', 'viper', 'fox',
    'bear', 'hunter', 'sniper', 'ghost', 'ninja', 'warrior', 'knight',
    'ranger', 'demon', 'angel', 'phoenix', 'raven',
]

# Множество уже использованных логинов (гарантия уникальности в рамках сессии)
_USED_USERNAMES = set()


def generate_password() -> str:
    """
    Генерация пароля формата `ckrss52221`:
        4-6 случайных строчных букв
        3-5 случайных цифр
        1-2 случайные строчные буквы
    Общая длина: 10-14 символов.

    Примеры: `mkpqt8834ls`, `xrvbn44219q`.

    :return: строка пароля.
    """
    # Ограничения компонентов могут давать минимум 4+3+1 = 8 символов,
    # поэтому перегенерируем пароль, пока общая длина не окажется в 10-14.
    while True:
        letters_part1 = ''.join(
            random.choice(string.ascii_lowercase)
            for _ in range(random.randint(4, 6))
        )
        digits_part = ''.join(
            random.choice(string.digits)
            for _ in range(random.randint(3, 5))
        )
        letters_part2 = ''.join(
            random.choice(string.ascii_lowercase)
            for _ in range(random.randint(1, 2))
        )
        password = letters_part1 + digits_part + letters_part2
        if 10 <= len(password) <= 14:
            return password


def generate_username() -> str:
    """
    Генерация надёжного логина Steam формата `[прилагательное][существительное][цифры]`.

    Примеры: `darkwolf47`, `firetiger823`, `iceblade9`.

    Гарантирует уникальность: повторные имена отбрасываются (множество _USED_USERNAMES).

    :return: строка логина.
    """
    while True:
        adj = random.choice(ADJECTIVES)
        noun = random.choice(NOUNS)
        numbers = ''.join(
            random.choice(string.digits) for _ in range(random.randint(2, 4))
        )
        username = adj + noun + numbers
        if username not in _USED_USERNAMES:
            _USED_USERNAMES.add(username)
            return username


def generate_email_data(domains: list, used: set) -> tuple:
    """
    Генерация данных e-mail: (логин, пароль, полный адрес).

    :param domains: список доступных доменов firstmail.ltd.
    :param used:    множество уже занятых e-mail адресов.
    :return:        кортеж (username, password, full_email).
    """
    username = generate_username()
    # Если адрес вдруг занят — генерируем логин заново
    while username in used:
        username = generate_username()

    password = generate_password()
    domain = random.choice(domains) if domains else 'firstmail.ltd'
    full_email = f"{username}@{domain}"
    used.add(username)
    return username, password, full_email


# Разрешаем ручной сброс множества (полезно для тестов)
def reset_used_usernames() -> None:
    """Очищает множество использованных логинов."""
    _USED_USERNAMES.clear()
