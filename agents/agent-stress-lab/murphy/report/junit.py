"""JUnit XML so CI systems show each persona × fault as a test case."""

from __future__ import annotations

from xml.etree import ElementTree as ET


def junit(data: dict) -> str:
    runs = data["runs"]
    failures = sum(1 for r in runs if not r["result"]["passed"])
    suite = ET.Element("testsuite", name=f"murphy.{data['project'].get('name', 'matrix')}", tests=str(len(runs)),
                       failures=str(failures), time=str(data["totals"]["wall_s"]))
    for run in runs:
        r = run["result"]
        case = ET.SubElement(suite, "testcase", classname=r["persona"], name=r["fault"], time=str(r["wall_s"]))
        if not r["passed"]:
            failed = [f"{c['id']}: {c['message']}" for c in r["checks"] if not c["passed"]]
            fail = ET.SubElement(case, "failure", message=", ".join(r["labels"]), type=r["labels"][0] if r["labels"] else "fail")
            fail.text = "\n".join([*failed, f"end: {r['end_reason']}", f"hint: {r['hint']}"])
    return ET.tostring(suite, encoding="unicode", xml_declaration=True)
