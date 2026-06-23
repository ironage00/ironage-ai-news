from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    dashboard_dir = root / "dashboard"
    sys.path.insert(0, str(dashboard_dir))

    from artifact_utils import report_artifacts_csv_path, upsert_report_artifacts
    from db import get_engine

    csv_path = report_artifacts_csv_path()
    if not csv_path.exists():
        raise SystemExit(f"Report artifacts CSV not found: {csv_path}")
    artifacts = pd.read_csv(csv_path)
    count = upsert_report_artifacts(get_engine(), artifacts)
    print(f"Synced report artifacts: {count} rows from {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
