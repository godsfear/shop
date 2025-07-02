import datetime
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Union

@dataclass
class SwiftMessage:
    block1: str
    block2: str
    block3: Optional[str]
    block5: Optional[str]
    fields: Dict[str, Union[str, List[str]]]
    mt_date: datetime.date
    mt_amount: float
    mt_currency: str

    def to_swift(self) -> str:
        """
        Собирает объект SwiftMessage обратно в текст SWIFT-сообщения.
        """
        # 1) Блоки 1, 2, 3
        parts = [f"{{1:{self.block1}}}", f"{{2:{self.block2}}}"]
        if self.block3 is not None:
            parts.append(f"{{3:{self.block3}}}")

        # 2) Блок 4: собираем поля
        # каждое поле tag:value, повторяющиеся теги идут на отдельных строках
        block4_lines = []
        for tag, val in self.fields.items():
            if isinstance(val, list):
                for item in val:
                    block4_lines.append(f":{tag}:{item}")
            else:
                block4_lines.append(f":{tag}:{val}")
        block4_text = '\n'.join(block4_lines)
        parts.append(f"{{4:\n{block4_text}-}}")

        # 3) Блок 5 (опционально)
        if self.block5 is not None:
            parts.append(f"{{5:{self.block5}}}")

        return ''.join(parts)

class SwiftParser:
    def __init__(self):
        self.raw_messages: List[str] = []
        self.messages: List[SwiftMessage] = []

    def load(self, filename: str):
        try:
            with open(filename, 'r', encoding="utf-8") as file:
                raw_text = file.read()
        except UnicodeDecodeError:
            with open(filename, 'r', encoding="cp1251") as file:
                raw_text = file.read()

        # 1) Разбить по маркеру "{1:"
        candidates = re.split(r'(?={1:)', raw_text, flags=re.DOTALL)
        candidates = [c.strip() for c in candidates if c.strip()]

        # 2) Валидация с опциональными блоками 3 и 5
        swift_re = re.compile(r'''
            ^{1:[^{}]+}
            {2:[^{}]+}
            (?:{3:(?:{[^{}]+})+})?
            {4:[\s\S]+?-}
            (?:{5:[^{}]*})?
            $''', re.VERBOSE)

        # 3) Фильтрация и парсинг
        for raw in candidates:
            if not swift_re.match(raw):
                continue
            self.raw_messages.append(raw)

            # Extract blocks
            b1 = re.search(r'^{1:([^}]+)}', raw).group(1)
            b2 = re.search(r'{2:([^}]+)}', raw).group(1)
            m3 = re.search(r'{3:(.*?)}(?={4:)', raw, flags=re.DOTALL)
            b3 = m3.group(1) if m3 else None
            m5 = re.search(r'{5:([^}]*)}', raw)
            b5 = m5.group(1) if m5 else None
            m4 = re.search(r'{4:(.*?)-}', raw, flags=re.DOTALL)
            block4 = m4.group(1).strip() if m4 else ''

            # Парсим поля блока 4, собирая повторяющиеся теги в списки
            field_pattern = re.compile(
                r':(?P<tag>\d{2}[A-Z]?):'           # тег
                r'(?P<value>.*?)(?=(?:\r?\n:\d{2}[A-Z]?:)|\Z)',
                re.DOTALL
            )
            fields: Dict[str, Union[str, List[str]]] = {}
            for mo in field_pattern.finditer(block4):
                tag = mo.group('tag')
                val = mo.group('value').strip().replace('\r\n', '\n')
                if tag in fields:
                    if isinstance(fields[tag], list):
                        fields[tag].append(val)
                    else:
                        fields[tag] = [fields[tag], val]
                else:
                    fields[tag] = val

            self.messages.append(
                SwiftMessage(block1=b1, block2=b2, block3=b3, block5=b5, fields=fields)
            )

    def build_all(self) -> List[str]:
        """
        Возвращает список строк — полностью сформированных SWIFT-сообщений
        из объектов SwiftMessage в self.messages.
        """
        return [msg.to_swift() for msg in self.messages]


parser = SwiftParser()
parser.load('../../experiments/mt-raw.txt')

# Список «сырых» валидных сообщений
print(parser.raw_messages)

# Список разобранных объектов SwiftMessage
for msg in parser.messages:
    print("Block1:", msg.block1)
    print("Block2:", msg.block2)
    print("Block3:", msg.block3)
    print("Fields from Block4:")
    for tag, val in msg.fields.items():
        print(f"  {tag} → {val}")
    print("-" * 30)

print("=" * 30)
rebuilt = parser.build_all()
for msg_text in rebuilt:
    print(msg_text)
    print("*" * 30)