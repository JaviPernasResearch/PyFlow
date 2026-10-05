import pytest

from PyFlow import Item
from PyFlow.expressions import ExpressionError, compile_expression


def ev(expr, item=None, **labels):
    item = item or Item(0, labels=labels, item_id=1)
    names = dict(item.get_all_labels(), labels=item.get_all_labels(), item=item)
    return compile_expression(expr)(names)


@pytest.mark.parametrize("expr, expected", [
    ("1 + 2 * 3", 7),
    ("(1 + 2) * 3", 9),
    ("7 // 2 + 7 % 2", 4),
    ("2 ** 10", 1024),
    ("-a + +b", 1),
    ("a / b", 2 / 3),
    ("max(a, b, 10) - min(a, b)", 8),
    ("abs(-3) + round(2.6) + int('4') + float('0.5')", 10.5),
    ("a < b <= 3", True),
    ("a == 2 and b != 2", True),
    ("a > 5 or b", 3),
    ("not a", False),
    ("10 if a > 1 else 20", 10),
    ("labels['b'] * 2", 6),
    ("'x' in labels", False),
    ("item.get_label_value('a') + 1", 3),
    ("item.type == 'Default'", True),
    ("item.item_number", 1),
])
def test_allowed_syntax(expr, expected):
    assert ev(expr, a=2, b=3) == expected


@pytest.mark.parametrize("expr", [
    "__import__('os')",
    "item.__class__",
    "item.type.upper()",
    "item.labels.clear()",
    "item.set_label_value('a', 1)",
    "(lambda: 1)()",
    "[x for x in (1, 2)]",
    "open('f')",
    "a.real",
    "_secret",
    "max(a, key=abs)",
    "2 ** 100000",
])
def test_rejected(expr):
    with pytest.raises(ExpressionError):
        ev(expr, a=2)


def test_unknown_name():
    with pytest.raises(ExpressionError, match="unknown name 'z'"):
        ev("z + 1")


def test_syntax_error():
    with pytest.raises(ExpressionError, match="cannot parse"):
        compile_expression("a +* b")


def test_item_method_without_item():
    fn = compile_expression("item.get_label_value('a')")
    with pytest.raises(ExpressionError, match="needs an item"):
        fn({"item": None})
