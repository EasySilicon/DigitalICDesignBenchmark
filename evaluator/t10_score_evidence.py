"""Independent evidence gate for the T10 systolic diagnostic score.

Overall numerical qualification remains a separate prerequisite for PPA.
Arithmetic failures in another group must not erase a passing systolic group.
"""

import re


def systolic_passed(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    structure = result.get("structure")
    if result.get("task_id") != "T10" or result.get("phase") != "run" or \
            not isinstance(structure, dict) or structure.get("passed") is not True or \
            result.get("reset_probe_passed") is not True:
        return False
    cases = result.get("cases")
    groups = result.get("groups")
    failures = result.get("failures")
    if type(cases) is not int or cases <= 0 or not isinstance(groups, dict) or \
            not isinstance(failures, list):
        return False
    stream_line = result.get("stream_line")
    if not isinstance(stream_line, str):
        return False
    marker = re.fullmatch(r"MM_STREAM input_bubble_phases=([01]{14}) finished=(\d+)",
                          stream_line)
    if marker is None or marker[1] != "0" * 14 or int(marker[2]) != cases:
        return False
    deficits = {}
    for name, row in groups.items():
        if not isinstance(row, dict):
            return False
        passed, total = row.get("cases_passed"), row.get("cases_total")
        if type(passed) is not int or type(total) is not int or \
                total <= 0 or not 0 <= passed <= total or \
                row.get("safety_violation", False) is not False:
            return False
        deficits[name] = total - passed
    # The asynchronous reset probe contributes one additional protocol case.
    if sum(row["cases_total"] for row in groups.values()) != cases + 1 or \
            "MM-SYSTOLIC" not in deficits or deficits["MM-SYSTOLIC"]:
        return False
    seen = set()
    for failure in failures:
        if not isinstance(failure, dict):
            return False
        group, case = failure.get("group"), failure.get("case")
        if group not in deficits or group == "MM-SYSTOLIC" or \
                type(case) is not int or not 0 <= case < cases or case in seen or \
                any(failure.get(flag) is not True
                    for flag in ("protocol", "timing", "output")) or \
                not isinstance(failure.get("errors"), list) or not failure["errors"] or \
                not all(isinstance(error, str) and error for error in failure["errors"]):
            return False
        seen.add(case)
        deficits[group] -= 1
    # Runner diagnostics may truncate failure details. Unknown failures cannot
    # be classified as arithmetic or charged to the candidate's systolic score.
    if any(value > 0 for value in deficits.values()):
        raise ValueError("incomplete T10 failure evidence; replay the original simulation log")
    return not any(deficits.values())
