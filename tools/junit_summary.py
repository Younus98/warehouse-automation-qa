"""
Turn a JUnit XML result file into a short Markdown summary.

GitHub shows this summary on the workflow run page, so anyone - a developer,
a product owner, a manager - sees the result without opening the report.

Usage: python tools/junit_summary.py reports/junit.xml
"""
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict


def main(path: str) -> None:
    root = ET.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")

    per_file = defaultdict(lambda: {"passed": 0, "failed": 0, "skipped": 0})
    failures = []
    for case in suite.iter("testcase"):
        module = case.get("classname", "").rsplit(".", 1)[-1]  # e.g. test_receiving
        if case.find("failure") is not None or case.find("error") is not None:
            per_file[module]["failed"] += 1
            problem = case.find("failure") if case.find("failure") is not None else case.find("error")
            first_line = (problem.get("message") or "").splitlines()[0][:150]
            failures.append(f"| `{module}` | `{case.get('name')}` | {first_line} |")
        elif case.find("skipped") is not None:
            per_file[module]["skipped"] += 1
        else:
            per_file[module]["passed"] += 1

    total_failed = sum(v["failed"] for v in per_file.values())
    total = sum(sum(v.values()) for v in per_file.values())
    verdict = "✅ All tests passed" if total_failed == 0 else f"❌ {total_failed} of {total} tests failed"

    print(f"## {verdict}\n")
    print(f"Ran {total} tests in {float(suite.get('time', 0)):.1f} s\n")
    print("| Test file | Passed | Failed | Skipped |")
    print("|---|---|---|---|")
    for module, counts in sorted(per_file.items()):
        print(f"| {module} | {counts['passed']} | {counts['failed']} | {counts['skipped']} |")
    if failures:
        print("\n### Failures\n")
        print("| File | Test | Reason |")
        print("|---|---|---|")
        print("\n".join(failures))


if __name__ == "__main__":
    main(sys.argv[1])
