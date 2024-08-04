import asyncio
from typing import List


def allowed_sym(text: str, symbols: List[str], include: bool) -> str:
    lib: dict = {
        "sym": "!\"#$%&'()*+,-./:;<=>?@^{}|\\`№_[]~",
        "num": "0123456789",
        "eng": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        "rus": "абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ",
        "kaz": "аәбвгғдеёжзийкқлмнңоөпрстуұүфхһцчшщъыіьэюяАӘБВГҒДЕЁЖЗИЙКҚЛМНҢОӨПРСТУҰҮФХҺЦЧШЩЪЫІЬЭЮЯ",
    }
    chars: str = ''.join([val for key, val in lib.items()]) if symbols is None else (
        ''.join([val if key in symbols else '' for key, val in lib.items()])
    )
    return (
        ''.join([c if c in chars else '' for c in text]) if include else (
            ''.join([c if c not in chars else '' for c in text]))
    )


async def main():
    print(allowed_sym('qwe√345', ['sym', 'num', 'eng'], False))


if __name__ == '__main__':
    asyncio.run(main())
