"""Gate decisions over explicit GitHub responses; not product or cloud QA."""
from copy import deepcopy

import pytest

from scripts.release_provenance import REQUIRED, GateError, verify

SHA = "a" * 40


def responses():
    data = {
        "branches/main": {"commit": {"sha": SHA}, "protected": True},
        "branches/main/protection": {
            "required_status_checks": {"strict": True, "contexts": [n for jobs in REQUIRED.values() for n in jobs]},
            "allow_force_pushes": {"enabled": False}, "allow_deletions": {"enabled": False},
        },
        "environments/production": {"protection_rules": [
            {"type": "required_reviewers", "prevent_self_review": True, "reviewers": [{"id": 1}]},
        ]},
    }
    runs = []
    for number, (name, jobs) in enumerate(REQUIRED.items(), 1):
        runs.append({"id": number, "name": name, "head_sha": SHA, "head_branch": "main", "event": "push",
                     "run_number": 1, "run_attempt": 1, "status": "completed", "conclusion": "success"})
        data[f"actions/runs/{number}/attempts/1/jobs?per_page=100&page=1"] = {"jobs": [
            {"name": job_name, "status": "completed", "conclusion": "success", "steps": [
                {"name": step, "conclusion": "success"} for step in steps
            ]} for job_name, steps in jobs.items()
        ]}
    data[f"actions/runs?event=push&head_sha={SHA}&per_page=100&page=1"] = {"workflow_runs": runs}
    return data


RUNS = f"actions/runs?event=push&head_sha={SHA}&per_page=100&page=1"
JOBS = "actions/runs/1/attempts/1/jobs?per_page=100&page=1"


def test_complete_evidence_passes():
    result = verify(responses().__getitem__, SHA)
    assert result["sha"] == SHA
    assert result["effectiveJobs"] == 10
    assert len(result["workflows"]) == 6


@pytest.mark.parametrize("defect", [
    "old_head", "unprotected", "non_strict", "missing_required_check", "force_push",
    "delete", "no_reviewer", "self_review", "wrong_sha", "pull_request", "wrong_branch",
    "pending_run", "failed_run", "missing_workflow", "missing_job", "skipped_job",
    "missing_step", "skipped_step", "newer_failed_attempt", "duplicate_job",
])
def test_incomplete_or_stale_evidence_blocks(defect):
    data = responses()
    run = data[RUNS]["workflow_runs"][0]
    jobs = data[JOBS]["jobs"]
    checks = data["branches/main/protection"]["required_status_checks"]
    reviewer = data["environments/production"]["protection_rules"][0]
    if defect == "old_head":
        data["branches/main"]["commit"]["sha"] = "b" * 40
    elif defect == "unprotected":
        data["branches/main"]["protected"] = False
    elif defect == "non_strict":
        checks["strict"] = False
    elif defect == "missing_required_check":
        checks["contexts"].pop()
    elif defect in {"force_push", "delete"}:
        data["branches/main/protection"]["allow_force_pushes" if defect == "force_push" else "allow_deletions"]["enabled"] = True
    elif defect == "no_reviewer":
        reviewer["reviewers"] = []
    elif defect == "self_review":
        reviewer["prevent_self_review"] = False
    elif defect == "wrong_sha":
        run["head_sha"] = "b" * 40
    elif defect == "pull_request":
        run["event"] = "pull_request"
    elif defect == "wrong_branch":
        run["head_branch"] = "other"
    elif defect == "pending_run":
        run["status"] = "in_progress"
    elif defect == "failed_run":
        run["conclusion"] = "failure"
    elif defect == "missing_workflow":
        data[RUNS]["workflow_runs"].pop()
    elif defect == "missing_job":
        jobs.pop()
    elif defect == "skipped_job":
        jobs[0]["conclusion"] = "skipped"
    elif defect == "missing_step":
        jobs[0]["steps"].pop()
    elif defect == "skipped_step":
        jobs[0]["steps"][0]["conclusion"] = "skipped"
    elif defect == "newer_failed_attempt":
        newer = deepcopy(run)
        newer.update(run_attempt=2, conclusion="failure")
        data[RUNS]["workflow_runs"].append(newer)
    elif defect == "duplicate_job":
        jobs.append(deepcopy(jobs[0]))
    with pytest.raises(GateError):
        verify(data.__getitem__, SHA)


def test_main_advancing_during_checks_blocks():
    data = responses()
    reads = 0

    def api(path):
        nonlocal reads
        if path == "branches/main":
            reads += 1
            if reads == 2:
                return {"commit": {"sha": "b" * 40}, "protected": True}
        return data[path]

    with pytest.raises(GateError, match="Main advanced"):
        verify(api, SHA)


def test_jobs_come_from_the_current_run_attempt():
    data = responses()
    run = data[RUNS]["workflow_runs"][0]
    run["run_attempt"] = 2
    data["actions/runs/1/attempts/2/jobs?per_page=100&page=1"] = data.pop(JOBS)
    assert verify(data.__getitem__, SHA)["workflows"][0]["attempt"] == 2


def test_workflow_pagination_is_not_truncated():
    data = responses()
    runs = data[RUNS]["workflow_runs"]
    data[RUNS] = {"workflow_runs": [{"name": "Unrelated"}] * 100}
    data[f"actions/runs?event=push&head_sha={SHA}&per_page=100&page=2"] = {"workflow_runs": runs}
    assert len(verify(data.__getitem__, SHA)["workflows"]) == 6
