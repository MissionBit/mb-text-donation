"""Parse dollar amount-like expressions

"""
import re
from typing import Optional

__all__ = ['parse_cents']

DOLLAR_RE = re.compile(r'^\s*\$?([1-9]\d*)((?:,\d\d\d)*)(?:\.(\d\d))?\s*$')

def parse_cents(s: str) -> Optional[int]:
    """Parse non-zero positive dollar amount expressions into cents or None

    >>> parse_cents('$1')
    100

    >>> parse_cents('1.50')
    150

    >>> parse_cents('200')
    20000

    >>> parse_cents('1,234')
    123400

    >>> parse_cents('12,345')
    1234500

    >>> parse_cents('123,456')
    12345600

    >>> parse_cents('$123,456.78')
    12345678

    >>> parse_cents('   20   ')
    2000

    >>> parse_cents('')
    >>> parse_cents('01234')
    >>> parse_cents('-$100')
    >>> parse_cents('100.0')
    >>> parse_cents('100.')
    >>> parse_cents('not a dollar amount')
    """
    m = DOLLAR_RE.match(s)
    if m is None:
        return None
    (leading_digits, comma_groups, cents) = m.groups()
    return int(leading_digits + comma_groups.replace(',', '') + (cents or '00'))

if __name__ == '__main__':
    import doctest
    doctest.testmod()