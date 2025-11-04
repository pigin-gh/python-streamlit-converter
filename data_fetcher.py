"""
Модуль загрузки и парсинга курсов валют с сайта ЦБ РФ.
Загружает HTML страницу, извлекает таблицу курсов и нормализует данные.
"""
from __future__ import annotations

from io import StringIO
from typing import Optional, List

import pandas as pd
import requests

# URL страницы с ежедневными курсами валют ЦБ РФ
CBR_DAILY_URL = "https://cbr.ru/currency_base/daily/"


class DataFetchError(RuntimeError):
    """Исключение для ошибок загрузки данных с сайта ЦБ (сеть, timeout, HTTP ошибки)"""
    pass


class DataParseError(ValueError):
    """Исключение для ошибок парсинга HTML таблицы (изменилась структура страницы)"""
    pass


def _default_headers(user_agent: Optional[str] = None) -> dict:
    """
    Возвращает HTTP заголовки для запроса к сайту ЦБ.
    Использует User-Agent браузера, чтобы сайт не блокировал запрос как бота.
    
    Args:
        user_agent: Опциональный кастомный User-Agent (если None, используется дефолтный)
    
    Returns:
        Словарь с HTTP заголовками
    """
    return {
        "User-Agent": user_agent
        or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/118.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru,en;q=0.9",  # Предпочитаем русский язык
    }


def _select_cbr_table(tables: List[pd.DataFrame]) -> pd.DataFrame:
    """
    Выбирает нужную таблицу из списка всех таблиц на странице.
    Ищет таблицу по наличию ожидаемых столбцов с русскими названиями.
    
    Args:
        tables: Список всех DataFrame, найденных на странице
    
    Returns:
        DataFrame с таблицей курсов валют
    
    Raises:
        DataParseError: если таблица с нужными столбцами не найдена
    """
    # Ожидаемые столбцы таблицы курсов ЦБ на русском языке
    expected_cols = {"Цифр. код", "Букв. код", "Единиц", "Валюта", "Курс"}
    
    # Ищем таблицу, которая содержит все нужные столбцы
    for tb in tables:
        cols = set(map(str, tb.columns))
        if expected_cols.issubset(cols):
            return tb
    
    # Если не нашли - значит структура страницы изменилась
    raise DataParseError("Не удалось найти таблицу курсов в HTML странице ЦБ.")


def _normalize_rates(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Нормализует таблицу курсов: переименовывает столбцы, приводит типы данных,
    добавляет российский рубль как базовую валюту.
    
    Args:
        df_raw: Сырой DataFrame из парсинга HTML (русские названия столбцов)
    
    Returns:
        Нормализованный DataFrame с индексом CharCode и колонками: Nominal, Name, Value
    """
    # Оставляем только нужные столбцы и переименовываем на английские названия
    df = df_raw[["Букв. код", "Единиц", "Валюта", "Курс"]].rename(
        columns={
            "Букв. код": "CharCode",  # Код валюты (USD, EUR и т.д.)
            "Единиц": "Nominal",      # Номинал (сколько единиц валюты)
            "Валюта": "Name",          # Название валюты
            "Курс": "Value",           # Курс в RUB за номинал единиц
        }
    )

    # Нормализация столбца Nominal: приводим к целому числу
    # Удаляем неразрывные пробелы (\xa0) и обычные пробелы из строк
    df["Nominal"] = (
        df["Nominal"].astype(str).str.replace("\xa0", "", regex=False).str.replace(" ", "", regex=False)
    )
    # Преобразуем строку в число (downcast="integer" экономит память)
    df["Nominal"] = pd.to_numeric(df["Nominal"], errors="raise", downcast="integer")

    # Нормализация столбца Value: приводим к float
    # Сначала в строку, убираем пробелы
    value_series = df["Value"].astype(str)
    value_series = value_series.str.replace("\xa0", "", regex=False).str.replace(" ", "", regex=False)
    # Заменяем запятую на точку (российский формат -> международный)
    value_series = value_series.str.replace(",", ".", regex=False)
    # Преобразуем в число с плавающей точкой
    df["Value"] = pd.to_numeric(value_series, errors="raise")

    # Индексируем DataFrame по коду валюты для быстрого поиска
    # Приводим к верхнему регистру и убираем пробелы
    df["CharCode"] = df["CharCode"].astype(str).str.upper().str.strip()
    df = df.set_index("CharCode", drop=True)

    # Добавляем российский рубль как базовую валюту, если его нет
    # RUB имеет номинал 1 и курс 1.0 (1 RUB = 1 RUB)
    if "RUB" not in df.index:
        df.loc["RUB"] = {"Nominal": 1, "Name": "Российский рубль", "Value": 1.0}

    # Сортируем по коду валюты для удобства в UI (алфавитный порядок)
    df = df.sort_index()
    
    # Возвращаем только нужные колонки (индекс уже установлен)
    return df[["Nominal", "Name", "Value"]]


def fetch_cbr_rates(url: str = CBR_DAILY_URL, timeout: int = 15, user_agent: Optional[str] = None) -> pd.DataFrame:
    """
    Главная функция модуля: загружает курсы валют с сайта ЦБ РФ и возвращает нормализованный DataFrame.
    
    Процесс работы:
    1. Делает HTTP GET запрос к странице ЦБ
    2. Парсит HTML и извлекает все таблицы
    3. Находит таблицу с курсами валют
    4. Нормализует данные (типы, названия, добавляет RUB)
    
    Args:
        url: URL страницы с курсами (по умолчанию официальная страница ЦБ)
        timeout: Таймаут запроса в секундах (по умолчанию 15)
        user_agent: Опциональный User-Agent для запроса
    
    Returns:
        DataFrame с индексом CharCode (коды валют) и колонками:
        - Nominal (int): номинал валюты (сколько единиц)
        - Name (str): название валюты
        - Value (float): курс в RUB за номинал единиц
    
    Raises:
        DataFetchError: при ошибках сети или HTTP (timeout, недоступность сайта)
        DataParseError: при ошибках парсинга (изменилась структура страницы)
    """
    # Шаг 1: Загружаем HTML страницу с сайта ЦБ
    try:
        resp = requests.get(url, headers=_default_headers(user_agent), timeout=timeout)
    except requests.RequestException as exc:
        # Ошибка сети: timeout, DNS ошибка, соединение прервано и т.д.
        raise DataFetchError(f"Ошибка сети при обращении к ЦБ: {exc}") from exc

    # Проверяем HTTP статус ответа (200 = успешно)
    if resp.status_code != 200:
        raise DataFetchError(f"ЦБ вернул статус {resp.status_code}")

    html = resp.text

    # Шаг 2: Парсим HTML и извлекаем все таблицы
    try:
        # pandas.read_html автоматически находит все <table> в HTML
        # thousands=None и decimal="," нужны для правильного парсинга чисел с запятыми
        # StringIO оборачивает строку в файл-подобный объект (избегаем FutureWarning)
        tables = pd.read_html(StringIO(html), thousands=None, decimal=",")
    except (ValueError, ImportError) as exc:
        # Ошибка парсинга: возможно, нет библиотеки lxml или HTML некорректен
        raise DataParseError(f"Не удалось распарсить HTML таблицу: {exc}") from exc

    # Проверяем, что хотя бы одна таблица найдена
    if not tables:
        raise DataParseError("На странице отсутствуют таблицы.")

    # Шаг 3: Выбираем нужную таблицу (с курсами валют)
    table = _select_cbr_table(tables)
    
    # Шаг 4: Нормализуем данные и возвращаем готовый DataFrame
    return _normalize_rates(table)


__all__ = [
    "CBR_DAILY_URL",
    "DataFetchError",
    "DataParseError",
    "fetch_cbr_rates",
]


