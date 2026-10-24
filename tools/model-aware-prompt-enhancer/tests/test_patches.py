import pytest

from prompt_enhancer.patches import PatchConflict, apply, check_conflicts, unified_diff
from prompt_enhancer.schema import Patch


def P(id, op, start, end, new="", order=0, suffix=""):
    return Patch(id=id, rule_id="T", op=op, start=start, end=end, new=new, rationale="", order=order, suffix=suffix)


def test_insert_replace_wrap_ordering():
    text = "abc def"
    out = apply(text, [
        P("w", "wrap", 0, 7, "<", suffix=">"),
        P("i0", "insert", 0, 0, "[pre]", order=-10),
        P("r", "replace", 4, 7, "XYZ"),
        P("iend", "insert", 7, 7, "!", order=0),
        P("after", "insert", 7, 7, "#", order=5),
    ])
    assert out == "[pre]<abc XYZ!>#"


def test_overlapping_replacements_conflict():
    ps = [P("a", "replace", 0, 5, "x"), P("b", "replace", 3, 8, "y")]
    assert check_conflicts(ps, 10) == [("a", "b")]
    with pytest.raises(PatchConflict):
        apply("0123456789", ps)


def test_insert_inside_replacement_conflicts():
    with pytest.raises(PatchConflict):
        apply("0123456789", [P("a", "replace", 2, 6, "x"), P("b", "insert", 4, 4, "y")])


def test_out_of_range_patch_conflicts():
    with pytest.raises(PatchConflict):
        apply("abc", [P("a", "insert", 10, 10, "x")])


def test_unified_diff_reconstructs_change():
    d = unified_diff("one\ntwo\n", "one\n2\n")
    assert "-two" in d and "+2" in d and d.startswith("--- original")
    assert unified_diff("same", "same") == ""
