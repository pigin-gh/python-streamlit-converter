"""
Модуль конвертации валют.
Содержит логику преобразования сумм между валютами с учётом номинала (единиц) валюты.
"""
from __future__ import annotations

from typing import Iterable, List

import pandas as pd


class ConversionError(ValueError):
    """Исключение для ошибок конвертации (неверная валюта, отрицательная сумма и т.д.)"""
    pass


def get_supported_codes(rates: pd.DataFrame) -> List[str]:
    """
    Извлекает список доступных валютных кодов из таблицы курсов.
    
    Args:
        rates: DataFrame с курсами валют (индекс = CharCode)
    
    Returns:
        Список строковых кодов валют (например, ['USD', 'EUR', 'RUB', ...])
    
    Raises:
        ConversionError: если таблица не содержит нужных столбцов
    """
    # Проверяем, что таблица имеет правильную структуру
    if not isinstance(rates, pd.DataFrame) or "Value" not in rates or "Nominal" not in rates:
        raise ConversionError("Некорректная таблица курсов: отсутствуют столбцы Value/Nominal.")
    # Возвращаем список индексов DataFrame (коды валют)
    return list(map(str, rates.index))


def _rate_to_rub(rates: pd.DataFrame, code: str) -> float:
    """
    Вычисляет стоимость 1 единицы валюты в российских рублях.
    
    Важно: ЦБ публикует курс за N единиц валюты (номинал).
    Например, если номинал = 10, а курс = 750, то 10 единиц стоят 750 RUB,
    значит 1 единица = 750/10 = 75 RUB.
    
    Args:
        rates: DataFrame с курсами (индекс = CharCode, колонки: Nominal, Value)
        code: Код валюты (например, 'USD', 'EUR')
    
    Returns:
        Стоимость 1 единицы валюты в RUB (float)
    
    Raises:
        ConversionError: если валюта не найдена или номинал некорректен
    """
    # Нормализуем код валюты: верхний регистр, без пробелов
    code = str(code).upper().strip()
    if code not in rates.index:
        raise ConversionError(f"Валюта '{code}' отсутствует в таблице курсов.")
    
    # Извлекаем номинал (сколько единиц валюты) и курс (сколько RUB за эти единицы)
    nominal = float(rates.loc[code, "Nominal"])  # количество единиц (например, 1 для USD, 10 для HUF)
    value = float(rates.loc[code, "Value"])      # курс в RUB за `nominal` единиц
    
    if nominal <= 0:
        raise ConversionError(f"Некорректный номинал для {code}: {nominal}")
    
    # Возвращаем цену одной единицы: курс делим на номинал
    return value / nominal


def convert(amount: float, code_from: str, code_to: str, rates: pd.DataFrame) -> float:
    """
    Конвертирует сумму из одной валюты в другую по курсам ЦБ РФ.
    
    Алгоритм конвертации:
    1. Переводим сумму из исходной валюты в рубли: amount * курс_исходной_к_RUB
    2. Переводим рубли в целевую валюту: рубли / курс_целевой_к_RUB
    3. Итого: amount * (курс_исходной_к_RUB) / (курс_целевой_к_RUB)
    
    Args:
        amount: Сумма для конвертации (неотрицательное число)
        code_from: Код исходной валюты (например, 'USD')
        code_to: Код целевой валюты (например, 'EUR')
        rates: DataFrame с курсами ЦБ (индекс = CharCode, колонки: Nominal, Value)
    
    Returns:
        Результат конвертации (float)
    
    Raises:
        ConversionError: при ошибках валидации или отсутствии валют
    """
    # Валидация суммы: должна быть числом и неотрицательной
    try:
        amount_value = float(amount)
    except (TypeError, ValueError) as exc:
        raise ConversionError("Сумма должна быть числом.") from exc
    if amount_value < 0:
        raise ConversionError("Сумма должна быть неотрицательной.")

    # Нормализуем коды валют
    src = str(code_from).upper().strip()
    dst = str(code_to).upper().strip()
    
    # Если конвертируем валюту саму в себя, просто возвращаем сумму
    if src == dst:
        return amount_value

    # Получаем курсы обеих валют к рублю (цена 1 единицы в RUB)
    rate_src_rub = _rate_to_rub(rates, src)  # Например, 1 USD = 75 RUB
    rate_dst_rub = _rate_to_rub(rates, dst)  # Например, 1 EUR = 80 RUB
    
    if rate_dst_rub == 0:
        raise ConversionError(f"Нулевой курс для {dst} недопустим.")

    # Формула конвертации через рубли как промежуточную валюту:
    # amount * (цена_исходной_в_RUB) / (цена_целевой_в_RUB)
    # Пример: 100 USD * (75 RUB/USD) / (80 RUB/EUR) = 93.75 EUR
    return amount_value * rate_src_rub / rate_dst_rub


__all__ = ["ConversionError", "get_supported_codes", "convert"]


