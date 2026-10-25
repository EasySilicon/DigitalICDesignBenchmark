"""Current delivery-contract deductions, separate from historical score math."""
from __future__ import annotations

import copy

POLICY_ID = "delivery-contract-cap10-v1"
SINGLE_PENALTY = 5
MAX_PENALTY = 10
CONTRACT_ITEMS = {"rtl/", "rtl/files.f", "verif/", "run.sh", "results.json", "README.md"}


def assessment(missing=(), errors=()):
    """Keep missing items separate from adjudicated independent error roots.

    Error attribution is candidate, infrastructure, or pending. A replay or a
    downstream symptom must reuse its original root_cause, not create a root.
    """
    return {"missing_deliverables": list(missing), "errors": list(errors)}


def deduction(report):
    if not isinstance(report, dict):
        raise ValueError("delivery_assessment must be an object")
    missing = report.get("missing_deliverables", [])
    errors = report.get("errors", [])
    if not isinstance(missing, list) or any(not isinstance(x, str) or x not in CONTRACT_ITEMS for x in missing):
        raise ValueError("missing_deliverables must list contract item names")
    if not isinstance(errors, list):
        raise ValueError("delivery errors must be a list")
    roots, pending = set(), set()
    for error in errors:
        if not isinstance(error, dict) or not isinstance(error.get("root_cause"), str) or not error["root_cause"].strip():
            raise ValueError("each delivery error needs a root_cause")
        attribution = error.get("attribution")
        if attribution not in {"candidate", "infrastructure", "pending"}:
            raise ValueError("delivery error attribution must be candidate, infrastructure, or pending")
        if attribution == "candidate":
            roots.add(error["root_cause"])
        elif attribution == "pending":
            pending.add(error["root_cause"])
    missing = set(missing)
    if "rtl/" in missing:
        missing.discard("rtl/files.f")
    if len(missing) >= 2 or len(roots) >= 2 or (missing and roots):
        return MAX_PENALTY, None
    if pending:
        return None, "delivery_error_attribution_pending"
    return SINGLE_PENALTY if missing or roots else 0, None


def apply_to_score(scored, payload):
    result = copy.deepcopy(scored)
    report = payload.get("delivery_assessment")
    if report is None:
        # Compatibility for already-adjudicated independent root counts.
        count = payload.get("candidate_delivery_error_count", 0)
        if type(count) is not int or count < 0:
            raise ValueError("candidate_delivery_error_count must be a nonnegative integer")
        penalty, pending = min(MAX_PENALTY, SINGLE_PENALTY * count), None
    else:
        penalty, pending = deduction(report)
        result["delivery_assessment"] = copy.deepcopy(report)
        result["candidate_delivery_error_count"] = len(set(report.get("missing_deliverables", []))) + len({
            e["root_cause"] for e in report.get("errors", []) if e["attribution"] == "candidate"})
        result["delivery_qualified"] = scored["delivery_qualified"] and not report.get("missing_deliverables") and not any(
            e["attribution"] != "infrastructure" for e in report.get("errors", []))
    result.update(delivery_penalty_policy=POLICY_ID, candidate_delivery_penalty=penalty,
                  delivery_penalty_status="pending" if pending else "adjudicated")
    if pending:
        result.update(delivery_penalty_pending_reason=pending, display_score=None)
    else:
        result.pop("delivery_penalty_pending_reason", None)
        result["display_score"] = max(0, result["display_score_before_candidate_penalty"] - penalty)
    return result
