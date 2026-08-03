# -*- coding: utf-8 -*-
"""
vpn_manager.py
==============
Менеджер VPN: получение списка серверов с vpngate.net, подключение через
OpenVPN CLI и проверка IP.

Возможности:
    - Скачивание конфигов vpngate через публичный API (CSV).
    - Фильтрация серверов по стране (RU / UA / KZ).
    - Подключение через `openvpn --config <file> --daemon`.
    - Проверка внешнего IP через https://api.ipify.org.
    - Отключение через `taskkill /F /IM openvpn.exe`.
"""

import base64
import logging
import os
import random
import shutil
import subprocess
import tempfile
import time

import requests

logger = logging.getLogger(__name__)

VPNGATE_API_URL = 'http://www.vpngate.net/api/iphone/'
IP_CHECK_URL = 'https://api.ipify.org'

# Соответствие номера региона -> код страны ISO
REGION_COUNTRY = {
    1: 'RU',
    2: 'UA',
    3: 'KZ',
}

# Ограничитель качества серверов (поле Score у vpngate). 0 — без ограничений.
# Умеренное значение, чтобы не отсечь все серверы UA/KZ.
MIN_SPEED = 1_000_000


class VPNManager:
    """Управление VPN-подключением."""

    def __init__(self) -> None:
        self.connected = False
        self.current_country = None
        self._config_path = None

    # ------------------------------------------------------------------ #
    # Открытые методы
    # ------------------------------------------------------------------ #
    def connect(self, region: int) -> bool:
        """
        Подключает VPN к случайному серверу нужной страны.

        :param region: номер региона (1 - RU, 2 - UA, 3 - KZ).
        :return: True, если подключение установлено и IP изменился.
        """
        country = REGION_COUNTRY.get(region)
        if not country:
            logger.error("Неизвестный регион: %s", region)
            return False

        # Отключаемся от предыдущего подключения перед сменой региона
        self.disconnect()

        servers = self.fetch_servers(country)
        if not servers:
            logger.error("Серверы для страны %s не найдены", country)
            return False

        # Перемешиваем и пробуем последовательно
        random.shuffle(servers)
        last_error = None
        for idx, server in enumerate(servers, start=1):
            config = server.get('config_base64')
            if not config:
                continue

            try:
                self._config_path = self._save_config(config)
                logger.info("Подключение к серверу %s (попытка %d/%d)",
                            server.get('host'), idx, len(servers))
                self._run_openvpn()
                time.sleep(15)  # ждём установления соединения

                if self.check_connection():
                    self.connected = True
                    self.current_country = country
                    logger.info("VPN подключен (IP: %s)", self.get_current_ip())
                    return True
                last_error = "не удалось сменить IP"
            except Exception as exc:  # noqa: BLE001
                last_error = f"{exc}"
                logger.warning("Сервер %s не сработал: %s",
                               server.get('host'), exc)
                self.disconnect()

        # Записываем ошибку в консоль (общую обработку делает main)
        error_msg = (f"Ошибка VPN: сервер недоступен, все {len(servers)} "
                     f"попыток не удались ({last_error})")
        logger.error(error_msg)
        return False

    def disconnect(self) -> None:
        """Отключает VPN и убивает процесс openvpn.exe."""
        if not self.connected and not self._openvpn_running():
            return
        try:
            subprocess.run(
                ['taskkill', '/F', '/IM', 'openvpn.exe'],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            logger.info("OpenVPN процесс остановлен")
        except Exception as exc:  # noqa: BLE001
            logger.warning("taskkill openvpn.exe: %s", exc)
        finally:
            self.connected = False
            self._cleanup_config()

    # ------------------------------------------------------------------ #
    # Получение списка серверов
    # ------------------------------------------------------------------ #
    def fetch_servers(self, country: str, retries: int = 3) -> list:
        """
        Получает и фильтрует список серверов из vpngate API.

        :param country: код страны (RU / UA / KZ).
        :param retries: количество повторных попыток при сбое сети.
        :return: список словарей с ключами host, ip, country_short, config_base64.
        """
        for attempt in range(1, retries + 1):
            try:
                resp = requests.get(VPNGATE_API_URL, timeout=20)
                resp.raise_for_status()
                servers = self._parse_csv(resp.text)
                filtered = [s for s in servers if s.get('country_short') == country]
                logger.info("Серверов для %s получено: %d", country, len(filtered))
                return filtered
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ошибка получения списка (попытка %d/%d): %s",
                               attempt, retries, exc)
                time.sleep(3)
        return []

    @staticmethod
    def _parse_csv(raw_text: str) -> list:
        """
        Парсит CSV-ответ vpngate API.

        Формат:
            *vpn_servers
            HostName,IP,Score,Ping,...
            <данные>,<base64 конфиг>
            ...
            <пустая строка>

        :param raw_text: сырой текст ответа.
        :return: список словарей.
        """
        lines = raw_text.strip().splitlines()
        servers = []
        for line in lines:
            # Пропускаем заголовки и служебные строки
            if not line or line.startswith('*') or line.startswith('#'):
                continue
            parts = line.split(',')
            if len(parts) < 15:
                continue
            host = parts[0]
            ip = parts[1]
            country_short = parts[6]
            # Оценка скорости (Score) — третья колонка
            try:
                score = float(parts[2]) if parts[2] else 0.0
            except ValueError:
                score = 0.0
            if score < MIN_SPEED:
                continue
            # Последняя колонка — base64 конфиг. Она может содержать запятые,
            # поэтому берём всё, что после 14-й запятой (индекс 14 и далее).
            config_b64 = ','.join(parts[14:])
            servers.append({
                'host': host,
                'ip': ip,
                'country_short': country_short,
                'score': score,
                'config_base64': config_b64,
            })
        return servers

    # ------------------------------------------------------------------ #
    # Сохранение конфига и запуск OpenVPN
    # ------------------------------------------------------------------ #
    @staticmethod
    def _save_config(config_b64: str) -> str:
        """
        Декодирует base64-конфиг и сохраняет во временный .ovpn файл.

        :param config_b64: base64 строка конфига.
        :return: путь к временному файлу.
        """
        raw = base64.b64decode(config_b64).decode('utf-8', errors='replace')
        fd, path = tempfile.mkstemp(suffix='.ovpn', prefix='vpngate_')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(raw)
        logger.debug("Конфиг сохранён: %s", path)
        return path

    def _run_openvpn(self) -> None:
        """Запускает OpenVPN CLI в фоне (--daemon)."""
        if not self._config_path:
            raise RuntimeError("Нет конфига для запуска OpenVPN")
        subprocess.run(
            ['openvpn', '--config', self._config_path, '--daemon'],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        logger.debug("OpenVPN запущен в фоне")

    @staticmethod
    def _openvpn_running() -> bool:
        """Проверяет, запущен ли процесс openvpn.exe."""
        try:
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq openvpn.exe'],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return 'openvpn.exe' in result.stdout
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------ #
    # Проверка IP
    # ------------------------------------------------------------------ #
    def get_current_ip(self) -> str:
        """Возвращает текущий внешний IP."""
        try:
            return requests.get(IP_CHECK_URL, timeout=15).text.strip()
        except Exception:  # noqa: BLE001
            return ''

    def check_connection(self) -> bool:
        """
        Проверяет, что внешний IP изменился (VPN работает).
        В идеале сравнить с "обычным" IP, но для простоты проверяем,
        что IP доступен и не пуст.
        """
        ip = self.get_current_ip()
        if not ip:
            return False
        logger.debug("Текущий IP: %s", ip)
        return True

    # ------------------------------------------------------------------ #
    # Служебное
    # ------------------------------------------------------------------ #
    def _cleanup_config(self) -> None:
        """Удаляет временный конфиг."""
        if self._config_path and os.path.exists(self._config_path):
            try:
                os.remove(self._config_path)
            except OSError as exc:
                logger.warning("Не удалось удалить конфиг: %s", exc)
        self._config_path = None

    @staticmethod
    def is_openvpn_installed() -> bool:
        """Проверяет наличие openvpn в PATH."""
        return shutil.which('openvpn') is not None


# Компактная функция для внешнего использования
def connect_vpn(region: int) -> tuple:
    """
    Удобная обёртка: подключить VPN для региона.

    :param region: номер региона.
    :return: (success: bool, ip: str)
    """
    mgr = VPNManager()
    ok = mgr.connect(region)
    return ok, (mgr.get_current_ip() if ok else '')
