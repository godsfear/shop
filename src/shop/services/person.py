"""Персоны — домен личности.

Поиска по имени/дате рождения сознательно НЕТ: это идентифицирующие данные
(см. память проекта — псевдонимизация); доступ только точечный, по id.
"""
from .. import tables
from .crud import CrudService


class PersonService(CrudService):
    table = tables.Person
