"""
FSMMixin — миксин, превращающий обычный класс в объект с машиной состояний.

В отличие от отдельного StateMachine, здесь конфигурация живёт прямо в классе:

    class Document(FSMMixin):
        states        = ("draft", "review", "published", "archived")
        initial_state = "draft"
        transitions   = [
            {"event": "submit",  "source": "draft",  "dest": "review"},
            {"event": "approve", "source": "review", "dest": "published",
             "guard": "is_editor", "action": "notify"},
        ]

        def is_editor(self, *, actor_role="user", **_):   # guard  — метод объекта
            return actor_role == "editor"

        def notify(self, **_):                            # action — метод объекта
            ...

        def on_enter_published(self, **_):                # колбэк по соглашению
            ...

Что даёт миксин подмешавшему классу:
- свойство `state` (с ленивой инициализацией в initial_state);
- автоматически сгенерированные методы-события: doc.submit(), doc.approve(...);
- доступ через doc.trigger("submit", **kwargs) и проверки doc.can(...) / doc.available_events();
- guard / action — это методы самого объекта (по имени-строке) или любой callable;
- колбэки on_enter_<state> / on_exit_<state> — тоже методы объекта, ищутся по имени;
- хранение статуса по умолчанию в поле объекта (state_field), но _get_state / _set_state
  легко переопределяются на БД/внешнее хранилище (пример — внизу файла).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Union


class TransitionError(Exception):
    """Нет допустимого перехода для события из текущего состояния."""


# guard / action могут быть заданы именем метода (str) или прямым callable
GuardOrAction = Union[str, Callable, None]


@dataclass(frozen=True)
class _Rule:
    event: str
    source: tuple[str, ...]   # одно/несколько исходных состояний; "*" — любое
    dest: str
    guard: GuardOrAction = None
    action: GuardOrAction = None

    def matches(self, current: str) -> bool:
        return "*" in self.source or current in self.source


class FSMMixin:
    # ------------------------------------------------------------------ #
    #  Объявляется в подклассе
    # ------------------------------------------------------------------ #
    states: tuple[str, ...] = ()
    initial_state: str = ""
    transitions: list[dict] = []
    state_field: str = "_fsm_state"   # имя атрибута, где хранится текущий статус

    # ------------------------------------------------------------------ #
    #  Сборка машины на уровне класса (один раз при объявлении подкласса)
    # ------------------------------------------------------------------ #
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._build_machine()

    @classmethod
    def _build_machine(cls) -> None:
        states = tuple(cls.states)
        if not states:
            return  # промежуточный/абстрактный класс без состояний — пропускаем

        state_set = set(states)
        if cls.initial_state not in state_set:
            raise ValueError(
                f"{cls.__name__}: initial_state='{cls.initial_state}' "
                f"не входит в states {sorted(state_set)}"
            )

        rules: dict[str, list[_Rule]] = {}
        for spec in cls.transitions:
            event = spec["event"]
            src = spec["source"]
            sources = (src,) if isinstance(src, str) else tuple(src)
            for s in sources:
                if s != "*" and s not in state_set:
                    raise ValueError(f"{cls.__name__}: неизвестный source '{s}' (event '{event}')")
            dest = spec["dest"]
            if dest not in state_set:
                raise ValueError(f"{cls.__name__}: неизвестный dest '{dest}' (event '{event}')")

            rules.setdefault(event, []).append(
                _Rule(event, sources, dest, spec.get("guard"), spec.get("action"))
            )

        cls._state_set = state_set
        cls._rules = rules

        # генерируем методы-события (но не затираем уже существующие атрибуты/методы,
        # в т.ч. служебные state/trigger/can — они есть на миксине, hasattr их защитит)
        for event in rules:
            if not hasattr(cls, event):
                setattr(cls, event, cls._make_event_method(event))

    @staticmethod
    def _make_event_method(event: str) -> Callable:
        def _event(self, **kwargs):
            return self.trigger(event, **kwargs)

        _event.__name__ = event
        _event.__qualname__ = event
        _event.__doc__ = f"FSM-событие «{event}»: эквивалент self.trigger('{event}', **kwargs)."
        return _event

    # ------------------------------------------------------------------ #
    #  Текущее состояние и хранилище (переопределяй для БД)
    # ------------------------------------------------------------------ #
    @property
    def state(self) -> str:
        st = self._get_state()
        if st is None:                      # ленивая инициализация
            st = type(self).initial_state
            self._set_state(st)
        return st

    def _get_state(self) -> Optional[str]:
        return getattr(self, self.state_field, None)

    def _set_state(self, value: str) -> None:
        setattr(self, self.state_field, value)

    # ------------------------------------------------------------------ #
    #  Запросы и переходы
    # ------------------------------------------------------------------ #
    def can(self, event: str, **kwargs) -> bool:
        """Доступно ли событие сейчас (с учётом guard)."""
        return self._match(self.state, event, **kwargs) is not None

    def available_events(self) -> list[str]:
        """События, доступные из текущего состояния (guard не проверяется)."""
        current = self.state
        return sorted(
            ev for ev, rs in self._rules.items() if any(r.matches(current) for r in rs)
        )

    def trigger(self, event: str, **kwargs) -> str:
        """Выполнить переход по событию. Возвращает новое состояние."""
        current = self.state
        rule = self._match(current, event, **kwargs)
        if rule is None:
            raise TransitionError(
                f"Событие '{event}' недопустимо из состояния '{current}' "
                f"({type(self).__name__})"
            )

        # порядок: on_exit -> action -> запись статуса -> on_enter
        self._fire(f"on_exit_{current}", **kwargs)
        self._invoke(rule.action, **kwargs)
        self._set_state(rule.dest)
        self._fire(f"on_enter_{rule.dest}", **kwargs)
        return rule.dest

    # ------------------------------------------------------------------ #
    #  Внутреннее
    # ------------------------------------------------------------------ #
    def _match(self, current: str, event: str, **kwargs) -> Optional[_Rule]:
        for r in self._rules.get(event, []):
            if r.matches(current) and self._guard_ok(r.guard, **kwargs):
                return r
        return None

    def _guard_ok(self, guard: GuardOrAction, **kwargs) -> bool:
        return True if guard is None else bool(self._invoke(guard, **kwargs))

    def _invoke(self, fn: GuardOrAction, **kwargs):
        """Вызвать метод по имени (bound) или произвольный callable (с self)."""
        if fn is None:
            return None
        if isinstance(fn, str):
            return getattr(self, fn)(**kwargs)
        return fn(self, **kwargs)

    def _fire(self, hook_name: str, **kwargs) -> None:
        """Вызвать колбэк on_enter_<state> / on_exit_<state>, если он определён."""
        hook = getattr(self, hook_name, None)
        if callable(hook):
            hook(**kwargs)


# ========================================================================= #
#  Демонстрация
# ========================================================================= #
if __name__ == "__main__":
    # --- Пример 1: статус хранится в самом объекте --------------------- #
    class Document(FSMMixin):
        states = ("draft", "review", "published", "archived")
        initial_state = "draft"
        transitions = [
            {"event": "submit",  "source": "draft",                 "dest": "review"},
            {"event": "approve", "source": "review",                "dest": "published",
             "guard": "is_editor"},
            {"event": "reject",  "source": "review",                "dest": "draft"},
            {"event": "archive", "source": ["published", "draft"],  "dest": "archived",
             "action": "log_archive"},
        ]

        def __init__(self, title):
            self.title = title

        # guard — обычный метод объекта
        def is_editor(self, *, actor_role="user", **_):
            return actor_role == "editor"

        # action — метод объекта (вызовется на переходе archive)
        def log_archive(self, **_):
            print(f"  [action] '{self.title}' уходит в архив")

        # колбэк по соглашению on_enter_<state>
        def on_enter_published(self, **_):
            print(f"  [hook]  '{self.title}' опубликован")

    print("=== Document (статус в поле объекта) ===")
    doc = Document("Релиз 1.0")
    print("Старт:", doc.state)                                # draft
    print("Доступно:", doc.available_events())                # ['archive', 'submit']

    doc.submit()                                              # сгенерированный метод
    print("После submit:", doc.state)                         # review
    print("approve обычному юзеру?", doc.can("approve", actor_role="user"))    # False
    print("approve редактору?",    doc.can("approve", actor_role="editor"))   # True
    doc.approve(actor_role="editor")                          # published (+hook)
    doc.archive()                                             # archived (+action)
    print("Итог:", doc.state)

    try:
        doc.submit()
    except TransitionError as e:
        print("Ошибка (ожидаемо):", e)

    # --- Пример 2: статус во внешнем хранилище (≈ БД) ------------------ #
    FAKE_DB: dict[str, str] = {}   # имитация таблицы со статусами

    class Ticket(FSMMixin):
        states = ("open", "in_progress", "closed")
        initial_state = "open"
        transitions = [
            {"event": "start", "source": "open",                  "dest": "in_progress"},
            {"event": "close", "source": ["open", "in_progress"], "dest": "closed"},
        ]

        def __init__(self, ticket_id):
            self.id = ticket_id

        # переопределяем хранилище: теперь статус живёт в "БД", а не в объекте
        def _get_state(self):
            return FAKE_DB.get(self.id)

        def _set_state(self, value):
            FAKE_DB[self.id] = value

    print("\n=== Ticket (статус во внешнем хранилище) ===")
    t = Ticket("T-1")
    t.start()
    print("Статус T-1:", t.state, "| в БД:", FAKE_DB)         # in_progress

    # новый объект с тем же id восстанавливает состояние из "БД"
    same = Ticket("T-1")
    print("Другой объект того же тикета видит:", same.state)   # in_progress
    same.close()
    print("В БД после close:", FAKE_DB)                        # {'T-1': 'closed'}