import textwrap

from dead_code_reaper.edits import apply_removals, edit_source
from dead_code_reaper.model import Removal


def rm(kind, start, end, col=0, **kw):
    return Removal(key=f"k{start}", kind=kind, name="x", path="m.py", start=start, end=end, col=col, **kw)


SRC = textwrap.dedent('''\
    import os


    def a():
        return 1


    def b():
        return 2


    def c():
        return 3
''')


def test_delete_keeps_two_blank_lines():
    out = edit_source(SRC, [rm("function", 8, 9)])
    assert out == "import os\n\n\ndef a():\n    return 1\n\n\ndef c():\n    return 3\n"


def test_delete_at_end_leaves_no_trailing_blanks():
    out = edit_source(SRC, [rm("function", 12, 13)])
    assert out.endswith("def b():\n    return 2\n")


def test_empty_class_body_gets_pass():
    src = "class A:\n    def m(self):\n        pass\n"
    assert edit_source(src, [rm("method", 2, 3, col=4)]) == "class A:\n    pass\n"


def test_partial_import_rewrite():
    src = "from typing import Dict, List, Optional\nx: List[Optional[int]] = []\n"
    info = {"is_from": True, "module": "typing", "level": 0, "stmt_start": 1, "stmt_end": 1,
            "col": 0, "aliases": [["Dict", None], ["List", None], ["Optional", None]]}
    r = rm("import", 1, 1, import_info={**info, "drop": "Dict", "bound": "Dict"})
    assert edit_source(src, [r]).splitlines()[0] == "from typing import List, Optional"


def test_nested_removal_is_absorbed():
    src = "def f():\n    return 1\n    x = 2\n\n\ndef g():\n    pass\n"
    out = edit_source(src, [rm("function", 1, 3), rm("unreachable", 3, 3, col=4)])
    assert out == "def g():\n    pass\n"


def test_module_removal_deletes_file():
    assert apply_removals({"m.py": "x = 1\n"}, [rm("module", 1, 1)]) == {"m.py": None}
