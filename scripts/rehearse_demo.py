"""Run the deterministic Block 8 rehearsal from an installed checkout."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, env: dict[str, str] | None = None, capture: bool = False) -> str:
    print(f"+ {' '.join(command)}", flush=True)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return completed.stdout if capture else ""


def main() -> None:
    run(["make", "check"])
    run(["npm", "--prefix", "apps/web", "run", "check"])
    with tempfile.TemporaryDirectory(prefix="expediente-cero-demo-") as temporary:
        environment = os.environ.copy()
        environment.update(
            {
                "EXPEDIENTE_CERO_ENVIRONMENT": "demo",
                "EXPEDIENTE_CERO_DATABASE_URL": f"sqlite:///{Path(temporary) / 'demo.sqlite3'}",
            }
        )
        run(
            [sys.executable, "-m", "app.demo", "reset", "--confirm", "RESET-DEMO-DATA"],
            env=environment,
        )
        raw_status = run(
            [sys.executable, "-m", "app.demo", "status"],
            env=environment,
            capture=True,
        )
        statuses = json.loads(raw_status)
        if len(statuses) != 3 or {item["status"] for item in statuses} != {"draft"}:
            raise RuntimeError("demo seed rehearsal did not produce three draft cases")
    run(["npm", "--prefix", "apps/web", "run", "test:e2e"])
    print("Demo rehearsal passed: API, web, seed/reset, and responsive E2E.")


if __name__ == "__main__":
    main()
