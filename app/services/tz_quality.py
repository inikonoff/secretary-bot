"""Automated quality checklist run before saving the final TZ (AI Specification v1.1 §29)."""

from __future__ import annotations

import re

from app.ai.schemas import FinalTZResult

REQUIRED_SECTION_TITLES = [
    "Название проекта",
    "Краткое описание",
    "Цель и решаемая проблема",
    "Целевая аудитория",
    "Сценарий использования",
    "Функциональные требования",
    "Логика работы системы",
    "Telegram-бот",
    "ИИ-функциональность",
    "Голосовые функции",
    "Интеграции и внешние сервисы",
    "Данные и хранение",
    "Административная часть",
    "Технические требования",
    "Предлагаемый стек технологий",
    "Безопасность",
    "Обработка ошибок",
    "Acceptance Criteria",
    "Что осталось неопределённым",
    "Рекомендации по реализации",
]

_FORBIDDEN_CODE_FENCES = re.compile(
    r"```(python|sql|javascript|js|typescript|ts|java|go|php|ruby|c\+\+|cpp|c#|csharp|bash|sh)\b",
    re.IGNORECASE,
)

_CYRILLIC = re.compile(r"[а-яА-ЯёЁ]")

_NON_ALNUM = re.compile(r"[^0-9a-zа-яё]+")


def _normalize(text: str) -> str:
    # Section-title matching must survive harmless formatting drift from the model
    # (a hyphen vs a space, "ИИ-функциональность" vs "ИИ функциональность", etc.) —
    # stripping everything but letters/digits before comparing avoids flagging a
    # section as "missing" when it's really just punctuated differently.
    return _NON_ALNUM.sub("", text.lower())


def check_tz_quality(result: FinalTZResult) -> list[str]:
    problems: list[str] = []
    md = result.technical_specification_markdown
    normalized_md = _normalize(md)

    for title in REQUIRED_SECTION_TITLES:
        if _normalize(title) not in normalized_md:
            problems.append(f"отсутствует раздел «{title}»")

    if len(_CYRILLIC.findall(md)) < 20:
        problems.append("документ не выглядит написанным на русском языке")

    if _FORBIDDEN_CODE_FENCES.search(md):
        problems.append("обнаружен фрагмент готового исходного кода в запрещённом языке")

    if "acceptance criteria" not in md.lower():
        problems.append("отсутствует Acceptance Criteria")

    if not result.technical_stack:
        problems.append("не указан технический стек")

    return problems
