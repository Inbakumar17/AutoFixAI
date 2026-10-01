import pytest

from autofixai.edits import OverlapError, apply_edits, select_non_overlapping
from autofixai.models import Fix, TextEdit


def test_replace_exact_range_only():
    src = 'x = "foo"\nfoo = 1\n'
    # Replace only the identifier on line 2; the string on line 1 must be untouched.
    out = apply_edits(src, [TextEdit(2, 0, 2, 3, "bar")])
    assert out == 'x = "foo"\nbar = 1\n'


def test_insertion_and_deletion():
    src = "a\nb\nc\n"
    out = apply_edits(src, [TextEdit(2, 0, 3, 0, ""), TextEdit(1, 0, 1, 0, "# hi\n")])
    assert out == "# hi\na\nc\n"


def test_columns_are_utf8_bytes():
    src = 'é = 1; y = 2\n'  # 'é' is 2 bytes in UTF-8
    start = src.encode().index(b"y")
    out = apply_edits(src, [TextEdit(1, start, 1, start + 1, "z")])
    assert out == "é = 1; z = 2\n"


def test_overlap_is_rejected():
    with pytest.raises(OverlapError):
        apply_edits("abcdef", [TextEdit(1, 0, 1, 4, "X"), TextEdit(1, 2, 1, 5, "Y")])


def test_select_non_overlapping_defers_collisions():
    src = "abcdef\n"
    f1 = Fix("r", "d", 1, [TextEdit(1, 0, 1, 3, "X")], 0.9, "")
    f2 = Fix("r", "d", 1, [TextEdit(1, 2, 1, 5, "Y")], 0.8, "")
    f3 = Fix("r", "d", 1, [TextEdit(1, 5, 1, 6, "Z")], 0.7, "")
    accepted, deferred = select_non_overlapping(src, [f1, f2, f3])
    assert accepted == [f1, f3] and deferred == [f2]
