"""
Главный модуль Streamlit приложения для конвертации валют.
Связывает UI компоненты с модулями загрузки данных и конвертации.
"""
from __future__ import annotations

import streamlit as st

from data_fetcher import fetch_cbr_rates, DataFetchError, DataParseError
from converter import convert, get_supported_codes, ConversionError

# Настройка страницы: заголовок в браузере и центрированный layout
st.set_page_config(page_title="Конвертер валют (ЦБ РФ)", layout="centered")


@st.cache_data(ttl=60 * 60)
def load_rates():
    """
    Загружает курсы валют с кэшированием на 1 час (3600 секунд).
    @st.cache_data предотвращает повторные запросы к сайту ЦБ при каждом обновлении страницы.
    """
    return fetch_cbr_rates()


# Заголовок и подпись приложения
st.title("Конвертер валют (ЦБ РФ)")
st.caption("Источник курсов: cbr.ru/currency_base/daily/")

# Создаём две колонки: для кнопки обновления и пустое место
col_refresh, _ = st.columns([1, 3])
with col_refresh:
    # Кнопка принудительного обновления: очищает кэш и перезагружает страницу
    if st.button("Обновить курсы", use_container_width=True):
        try:
            load_rates.clear()  # Очищаем кэш Streamlit
        except Exception:
            pass
        st.rerun()  # Перезапускаем приложение для загрузки свежих данных

# Загружаем курсы валют с обработкой ошибок
try:
    rates = load_rates()  # Получаем DataFrame с курсами (кэшируется)
except DataFetchError as exc:
    # Ошибка сети или недоступность сайта ЦБ
    st.error(f"Ошибка загрузки данных ЦБ: {exc}")
    st.stop()  # Останавливаем выполнение приложения
except DataParseError as exc:
    # Ошибка парсинга HTML таблицы (изменилась структура страницы)
    st.error(f"Ошибка парсинга таблицы ЦБ: {exc}")
    st.stop()
except Exception as exc:
    # Любая другая непредвиденная ошибка
    st.error(f"Непредвиденная ошибка: {exc}")
    st.stop()

# Получаем список доступных валютных кодов для выпадающих списков
codes = get_supported_codes(rates)

# Создаём интерфейс выбора валют: две колонки рядом
left, right = st.columns(2)
with left:
    # Выбор исходной валюты: по умолчанию USD, если доступен
    default_from_idx = codes.index("USD") if "USD" in codes else 0
    code_from = st.selectbox("Исходная валюта", options=codes, index=default_from_idx)
with right:
    # Выбор целевой валюты: по умолчанию RUB (российский рубль)
    default_to_idx = codes.index("RUB") if "RUB" in codes else 0
    code_to = st.selectbox("Целевая валюта", options=codes, index=default_to_idx)

# Поле ввода суммы для конвертации: только положительные числа, по умолчанию 100
amount = st.number_input("Сумма для конвертации", min_value=0.0, value=100.0, step=1.0, format="%.2f")

# Кнопка запуска конвертации (тип "primary" делает её выделенной)
if st.button("Конвертировать", type="primary"):
    try:
        # Выполняем конвертацию: amount из code_from в code_to по курсам rates
        result = convert(amount, code_from, code_to, rates)
    except ConversionError as exc:
        # Ошибка валидации: неверная валюта, отрицательная сумма и т.д.
        st.error(str(exc))
    except Exception as exc:
        # Другие ошибки при конвертации
        st.error(f"Ошибка конвертации: {exc}")
    else:
        # Успешная конвертация: показываем результат зелёным сообщением
        st.success(f"{amount:.2f} {code_from} = {result:.4f} {code_to}")
        
        # Раскрывающаяся секция с деталями расчёта
        with st.expander("Детали расчёта"):
            # Извлекаем номиналы и курсы из таблицы для отображения
            nominal_from = float(rates.loc[code_from, "Nominal"]) if code_from in rates.index else None
            nominal_to = float(rates.loc[code_to, "Nominal"]) if code_to in rates.index else None
            value_from = float(rates.loc[code_from, "Value"]) if code_from in rates.index else None
            value_to = float(rates.loc[code_to, "Value"]) if code_to in rates.index else None
            # Показываем курсы ЦБ с указанием номиналов (например, "73.50 RUB за 1 USD")
            st.write(
                f"Курс ЦБ: {value_from} RUB за {int(nominal_from)} {code_from}; "
                f"{value_to} RUB за {int(nominal_to)} {code_to}"
            )


