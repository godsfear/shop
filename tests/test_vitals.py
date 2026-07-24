import pytest

from shop.medical_seed import VITAL_VALIDATION
from shop.vitals import VitalValueError, normalize_vital_value


@pytest.mark.parametrize(('code', 'raw', 'expected'), [
    ('temperature', '37', '37.0'),
    ('temperature', '37,2', '37.2'),
    ('blood_pressure', ' 120 / 80 ', '120/80'),
    ('pulse', '72', '72'),
    ('height', '181,5', '181.5'),
    ('weight', '70.0', '70.0'),
    ('glucose', '5,6', '5.6'),
])
def test_normalize_vital_value(code, raw, expected):
    assert normalize_vital_value(code, raw) == expected


@pytest.mark.parametrize(('code', 'raw', 'reason'), [
    ('temperature', '37.25', 'format'),
    ('temperature', '46.0', 'range'),
    ('blood_pressure', '120', 'format'),
    ('blood_pressure', '80/120', 'order'),
    ('blood_pressure', '301/100', 'range'),
    ('pulse', '72.5', 'format'),
    ('height', '301', 'range'),
    ('weight', '0.1', 'range'),
    ('glucose', '60.1', 'range'),
    ('unknown', '1', 'unknown'),
])
def test_reject_invalid_vital_value(code, raw, reason):
    with pytest.raises(VitalValueError) as exc:
        normalize_vital_value(code, raw)
    assert exc.value.reason == reason


def test_every_seeded_vital_has_a_rule():
    assert set(VITAL_VALIDATION) == {
        'height', 'weight', 'blood_pressure', 'pulse', 'temperature', 'glucose',
    }
