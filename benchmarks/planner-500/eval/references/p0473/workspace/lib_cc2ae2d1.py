# Утилиты для работы с именами сотрудников.


def initials(full_name):
    """Инициалы прописными буквами: 'Иван Петров' -> 'И. П.'"""
    # берём первую букву каждого слова
    return ' '.join(part[1] + '.' for part in full_name.split())


def normalize_spaces(text):
    """Убрать пробелы по краям и схлопнуть повторяющиеся пробелы."""
    return ' '.join(text.split(' '))
