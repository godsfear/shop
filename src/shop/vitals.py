"""Нормализация пользовательского ввода медицинских показателей.

Диапазоны здесь технические, не диагностические: опасное, но возможное
значение сохраняется; отсекаются неверный формат и очевидные опечатки.
"""
import re
from decimal import Decimal, InvalidOperation

from .medical_seed import VITAL_VALIDATION


class VitalValueError(ValueError):
    """reason: format | range | order | unknown."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def normalize_vital_value(code: str, raw: object) -> str:
    rule = VITAL_VALIDATION.get(code)
    if rule is None:
        raise VitalValueError('unknown')
    text = str(raw).strip()

    if rule['kind'] == 'blood_pressure':
        match = re.fullmatch(r'(\d{2,3})\s*/\s*(\d{2,3})', text)
        if match is None:
            raise VitalValueError('format')
        systolic, diastolic = map(int, match.groups())
        if not (rule['systolic_min'] <= systolic <= rule['systolic_max']
                and rule['diastolic_min'] <= diastolic <= rule['diastolic_max']):
            raise VitalValueError('range')
        if systolic <= diastolic:
            raise VitalValueError('order')
        return f'{systolic}/{diastolic}'

    decimals = rule['decimals']
    pattern = r'\d+' if decimals == 0 else rf'\d+(?:[.,]\d{{1,{decimals}}})?'
    if re.fullmatch(pattern, text) is None:
        raise VitalValueError('format')
    try:
        number = Decimal(text.replace(',', '.'))
    except InvalidOperation as exc:
        raise VitalValueError('format') from exc
    if not (Decimal(str(rule['min'])) <= number <= Decimal(str(rule['max']))):
        raise VitalValueError('range')
    return f'{number:.{decimals}f}'
