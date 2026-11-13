"""Read-only release gate. Provider access failures fail closed; never deploys."""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request

REQUIRED = {
    "S4P validation": {
        "Frontend SAP regressions": ["Run npm run typecheck", "Run npm run lint", "Run npm test -- --run", "Production build"],
        "Backend transaction regressions": ["Lint", "Python compile", "Tests with real PostgreSQL"],
    },
    "S4P authenticated browser critical journeys": {
        f"Browser + PostgreSQL + private evidence E2E ({suite})": [
            "Verify that no Playwright spec is omitted from the two suites",
            "Execute end-to-end project, financial, accessibility and browser scenarios",
        ] for suite in ("functional", "visual")
    },
    "S4P corporate identity audit": {"identity": ["Verify S4P branding and compatibility exclusions"]},
    "S4P secret leakage guard": {"Scan introduced changes for secrets": ["Check introduced code changes for exposed secrets"]},
    "S4P dependency vulnerability guard": {
        "Frontend dependency audit": ["Reject high and critical vulnerabilities"],
        "Python dependency audit": ["Reject known vulnerabilities in runtime dependencies"],
    },
    "S4P CodeQL security analysis": {
        f"CodeQL / {language}": ["Run github/codeql-action/analyze@v4"]
        for language in ("python", "javascript-typescript")
    },
}


class GateError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def verify(api, sha: str) -> dict:
    require(bool(re.fullmatch(r"[0-9a-f]{40}", sha)), "Expected SHA must be a full commit")

    def check_head():
        branch = api("branches/main")
        require(branch["commit"]["sha"] == sha, "Main advanced; repeat CI and approval for its current SHA")
        require(branch.get("protected") is True, "Main has no active protection")

    check_head()
    protection = api("branches/main/protection")
    checks = protection.get("required_status_checks") or {}
    names = set(checks.get("contexts", [])) | {c["context"] for c in checks.get("checks", [])}
    require(checks.get("strict") is True, "Strict required status checks are missing")
    require({name for jobs in REQUIRED.values() for name in jobs} <= names,
            "Main does not require all ten CI jobs")
    for option in ("allow_force_pushes", "allow_deletions"):
        require(protection.get(option, {}).get("enabled") is False, f"Unsafe or unverifiable {option}")

    environment = api("environments/production")
    reviews = [r for r in environment.get("protection_rules", []) if r.get("type") == "required_reviewers"]
    require(any(r.get("reviewers") and r.get("prevent_self_review") is True for r in reviews),
            "Production requires an independent human reviewer")

    # Paginate runs and jobs; never accept a partial first page as full evidence.
    runs = []
    for page in range(1, 101):
        batch = api(f"actions/runs?event=push&head_sha={sha}&per_page=100&page={page}")["workflow_runs"]
        runs.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise GateError("Workflow pagination exceeded limit")
    evidence = []
    for name, required_jobs in REQUIRED.items():
        candidates = [r for r in runs if r.get("name") == name and r.get("head_sha") == sha
                      and r.get("event") == "push" and r.get("head_branch") == "main"]
        require(bool(candidates), f"Missing push workflow: {name}")
        run = max(candidates, key=lambda r: (r["run_number"], r["run_attempt"]))
        require(run.get("status") == "completed" and run.get("conclusion") == "success", f"Workflow not successful: {name}")
        jobs = []
        for page in range(1, 101):
            batch = api(f"actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs?per_page=100&page={page}")["jobs"]
            jobs.extend(batch)
            if len(batch) < 100:
                break
        else:
            raise GateError("Job pagination exceeded limit")
        require(len(jobs) == len(required_jobs) and {j["name"] for j in jobs} == set(required_jobs), f"Unexpected or missing jobs: {name}")
        for job in jobs:
            require(job.get("status") == "completed" and job.get("conclusion") == "success", f"Job not successful: {job['name']}")
            for step_name in required_jobs[job["name"]]:
                steps = [s for s in job.get("steps", []) if s.get("name") == step_name]
                require(len(steps) == 1 and steps[0].get("conclusion") == "success", f"Critical step missing or not successful: {step_name}")
        evidence.append({"workflow": name, "runId": run["id"], "attempt": run["run_attempt"]})
    check_head()
    return {"sha": sha, "workflows": evidence, "effectiveJobs": sum(map(len, REQUIRED.values()))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--repository", default="Clopezgg/S4P-")
    args = parser.parse_args()
    require(bool(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository)), "Invalid repository")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    require(bool(token), "GitHub token is required; do not print or pass it as a command argument")

    def api(path):
        request = urllib.request.Request(
            f"https://api.github.com/repos/{args.repository}/{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise GateError(f"GitHub verification unavailable (HTTP {exc.code}); gate remains closed") from None
        except (OSError, ValueError):
            raise GateError("GitHub verification unavailable; gate remains closed") from None

    print(json.dumps(verify(api, args.expected_sha), indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateError as exc:
        print(f"Release blocked: {exc}")
        raise SystemExit(1) from None
