import re
from typing import List, AnyStr


class MtDocument:
    pattern_header: re.Pattern[AnyStr] = re.compile(r'({1:[a-zA-Z][0-9]{2}[\S\s]+?){4:\n')
    pattern_body: re.Pattern[AnyStr] = re.compile(r'{4:\n([\s\S]+?)-}')
    pattern_fields: re.Pattern[AnyStr] = re.compile(r':([0-9]{2}[a-zA-Z]?):((?:(?!:[0-9]{2}[a-zA-Z]?:)[\s\S])+)')

    def __init__(self, mt: str):
        self.header: List[str] = self.pattern_header.findall(mt)
        self.body: List[str] = self.pattern_body.findall(mt)
        self.fields: List[dict] = []
        for b in self.body:
            self.fields.append(dict((key, val.rstrip('\n')) for (key, val) in self.pattern_fields.findall(b)))

    def __repr__(self):
        return f"header: {self.header}\nbody: {self.body}\nfields: {self.fields}"


def main():
    with open('../../experiments/mt.txt', 'r', encoding='utf-8') as f:
        print(MtDocument(f.read()))


if __name__ == '__main__':
    main()
