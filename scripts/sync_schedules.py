"""Push the live ScheduleUpcoming export from OneDrive to R2.

Power Automate used to upload it with an HTTP PUT to the Cloudflare Worker,
but since late October 2026 those requests arrive with the body stripped
(Content-Length 0, only Host + Authorization headers survive). The flow
still writes a correct copy to OneDrive, which syncs to this Mac, so this
job forwards it:

    Complete/ScheduleUpcoming.csv    -> R2 (key R2_SCHEDULE_UPCOMING_KEY),
                                        read by the Clinical dashboard

The Scheduling app uploader (_upload_scheduling) is kept for the physician
schedule but disabled in TARGETS; see the note there.

Each run checks each target file and uploads only when its content has
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
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DATA_DIR_RAW, PROJECT_ROOT  # noqa: E402  (also loads .env)
from data.schedule_upload import put_schedule_upcoming, validate_csv  # noqa: E402

STATE_PATH = PROJECT_ROOT / ".schedule_sync_state.json"
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


def _upload_r2(data: bytes, file_modified: str) -> str:
    # file_modified (OneDrive mtime, UTC) becomes the "Schedule updated" time.
    return "R2 " + _with_retries(lambda: put_schedule_upcoming(data, file_modified), "r2")


def _upload_scheduling(data: bytes, file_modified: str) -> str:  # noqa: ARG001
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
    # Physician Schedule.csv -> Scheduling app is NOT synced here: the flow's
    # own multipart POST to /api/aria/upload still arrives intact (201 nightly
    # at ~1:45 AM), so a second upload would only duplicate snapshots. Re-add
    # {"name": "PhysicianSchedule", "file": "Physician Schedule.csv",
    #  "required": ["ScheduledDate", "PhysicianName"], "send": _upload_scheduling}
    # if that flow step ever starts arriving empty too.
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

        ok, reason, rows = validate_csv(data, t["required"])
        file_time = datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
        file_time_utc = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(timespec="seconds")
        if not ok:
            if entry.get("rejected_sha256") != digest:  # log each bad file once
                _log(f"[{name}] NOT uploaded: {reason} (file modified {file_time}); previous upload kept")
                entry["rejected_sha256"] = digest
            continue

        if dry_run:
            _log(f"[{name}] dry run: would upload {len(data):,} bytes, {rows:,} rows (file modified {file_time})")
            continue

        try:
            where = t["send"](data, file_time_utc)
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
