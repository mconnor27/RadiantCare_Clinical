"""Push the two live schedule exports from OneDrive to where the apps read them.

Power Automate used to upload these with its HTTP action, but since late
October 2026 those requests arrive with the body stripped (Content-Length 0,
only Host + Authorization headers survive). The flow still writes correct
copies to OneDrive, which syncs to this Mac, so this job forwards them:

    Complete/ScheduleUpcoming.csv    -> R2 (key R2_SCHEDULE_UPCOMING_KEY),
                                        read by the Clinical dashboard
    Complete/Physician Schedule.csv  -> Scheduling app POST /api/aria/upload

Each run checks both files and uploads only when a file's content has
changed since the last successful upload and it passes validation (enough
bytes, required columns, at least one data row). Files modified in the last
minute are left for the next run in case OneDrive is still writing them.

Run by launchd every 5 minutes (scripts/com.radiantcare.schedule-sync.plist).

Usage:
    python scripts/sync_schedules.py             # upload whatever changed
    python scripts/sync_schedules.py --dry-run   # validate only, send nothing
    python scripts/sync_schedules.py --force     # upload even if unchanged

Requires in .env: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
R2_BUCKET, ARIA_UPLOAD_API_KEY. Optional: R2_SCHEDULE_UPCOMING_KEY,
SCHEDULING_UPLOAD_URL.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DATA_DIR_RAW, PROJECT_ROOT  # noqa: E402  (also loads .env)

STATE_PATH = PROJECT_ROOT / ".schedule_sync_state.json"
MIN_BYTES = 200
SETTLE_SECONDS = 60
SCHEDULING_UPLOAD_URL = os.environ.get(
    "SCHEDULING_UPLOAD_URL",
    "https://radiantcare-scheduling-production.up.railway.app/api/aria/upload",
)


def _log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def _with_retries(fn, what: str, attempts: int = 3):
    """Retry transient failures (network errors, 5xx) with backoff."""
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — log and retry anything transient
            if i == attempts:
                raise
            _log(f"[{what}] attempt {i} failed ({type(e).__name__}: {e}); retrying")
            time.sleep(5 * i)


def _validate(data: bytes, required: list[str]) -> tuple[bool, str, int]:
    if len(data) < MIN_BYTES:
        return False, f"only {len(data)} bytes", 0
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    header = next(reader, [])
    missing = [c for c in required if c not in header]
    if missing:
        return False, f"missing columns {missing}", 0
    rows = sum(1 for row in reader if any(cell.strip() for cell in row))
    if rows == 0:
        return False, "header only, no data rows", 0
    return True, "ok", rows


def _upload_r2(data: bytes) -> str:
    import boto3

    key = os.environ.get("R2_SCHEDULE_UPCOMING_KEY", "ScheduleUpcoming.csv").strip()
    bucket = os.environ.get("R2_BUCKET", "radiantcare-sanitized").strip()
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID'].strip()}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"].strip(),
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"].strip(),
        region_name="auto",
    )

    def put():
        s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType="text/csv")
        size = s3.head_object(Bucket=bucket, Key=key)["ContentLength"]
        if size != len(data):
            raise RuntimeError(f"R2 holds {size} bytes after upload, expected {len(data)}")

    _with_retries(put, "r2")
    return f"R2 {bucket}/{key}"


def _upload_scheduling(data: bytes) -> str:
    import requests

    api_key = os.environ["ARIA_UPLOAD_API_KEY"].strip()

    def post():
        r = requests.post(
            SCHEDULING_UPLOAD_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("aria-schedule.csv", data, "text/csv")},
            timeout=180,
        )
        if r.status_code >= 500:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        if r.status_code != 201:
            # 4xx won't fix itself on retry: report it without retrying.
            return f"REJECTED HTTP {r.status_code}: {r.text[:300]}"
        return None

    rejected = _with_retries(post, "scheduling")
    if rejected:
        raise PermissionError(rejected)
    return "Scheduling app upload"


TARGETS = [
    {
        "name": "ScheduleUpcoming",
        "file": "ScheduleUpcoming.csv",
        "required": ["ScheduledDateTime", "AssignedResource", "BookingStatus"],
        "send": _upload_r2,
    },
    {
        "name": "PhysicianSchedule",
        "file": "Physician Schedule.csv",
        "required": ["ScheduledDate", "PhysicianName"],
        "send": _upload_scheduling,
    },
]


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_PATH)


def sync(dry_run: bool = False, force: bool = False) -> int:
    state = _load_state()
    failures = 0
    for t in TARGETS:
        name = t["name"]
        path = DATA_DIR_RAW / "Complete" / t["file"]
        entry = state.setdefault(name, {})
        entry["last_check"] = datetime.now().isoformat(timespec="seconds")

        if not path.is_file():
            _log(f"[{name}] source missing: {path}")
            failures += 1
            continue
        mtime = path.stat().st_mtime
        if time.time() - mtime < SETTLE_SECONDS:
            continue  # OneDrive may still be writing; next run picks it up

        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest == entry.get("sha256") and not force:
            continue

        ok, reason, rows = _validate(data, t["required"])
        file_time = datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
        if not ok:
            if entry.get("rejected_sha256") != digest:  # log each bad file once
                _log(f"[{name}] NOT uploaded: {reason} (file modified {file_time}); previous upload kept")
                entry["rejected_sha256"] = digest
            continue

        if dry_run:
            _log(f"[{name}] dry run: would upload {len(data):,} bytes, {rows:,} rows (file modified {file_time})")
            continue

        try:
            where = t["send"](data)
        except Exception as e:  # noqa: BLE001
            _log(f"[{name}] upload FAILED: {type(e).__name__}: {e}")
            failures += 1
            continue

        entry.update(
            sha256=digest,
            bytes=len(data),
            rows=rows,
            file_modified=file_time,
            uploaded_at=datetime.now().isoformat(timespec="seconds"),
        )
        entry.pop("rejected_sha256", None)
        _log(f"[{name}] uploaded {len(data):,} bytes, {rows:,} rows (file modified {file_time}) -> {where}")

    if not dry_run:
        _save_state(state)
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="validate only, upload nothing")
    ap.add_argument("--force", action="store_true", help="upload even if the file is unchanged")
    args = ap.parse_args()
    return sync(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
