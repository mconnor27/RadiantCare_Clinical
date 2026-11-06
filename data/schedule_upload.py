"""ScheduleUpcoming upload: validation, the R2 write, and the HTTP endpoint.

The Power Automate "Schedule Slots" flow POSTs each ARIA export here as a
multipart form (a "file" part), the same shape as its working upload to the
Scheduling app. Uploads to the Cloudflare Worker arrived with the body
stripped from late October 2026, and the company DLP policy blocks
radiantcare.app, but *.up.railway.app is allowed.

    POST /api/schedule-upload
    Authorization: Bearer <SCHEDULE_UPLOAD_TOKEN>
    multipart/form-data with a "file" part (a raw CSV body also works)

The file is validated (size, required columns, at least one data row) and
written to R2 with the upload time as "source-modified" metadata, which the
dashboard's "Schedule updated" label reads. Invalid uploads get a 400 and
the existing R2 file is left alone. scripts/sync_schedules.py uses the same
validation and R2 write for its OneDrive-based fallback.
"""

from __future__ import annotations

import csv
import hmac
import io
import os
from datetime import datetime, timezone

UPLOAD_PATH = "/api/schedule-upload"
REQUIRED_COLUMNS = ("ScheduledDateTime", "AssignedResource", "BookingStatus")
MIN_BYTES = 200
MAX_BYTES = 10 * 1024 * 1024  # the real export is ~80 KB


def validate_csv(data: bytes, required=REQUIRED_COLUMNS) -> tuple[bool, str, int]:
    """Return (ok, reason, data_rows) for a CSV export."""
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


def put_schedule_upcoming(data: bytes, source_modified: str) -> str:
    """Write the export to R2 and verify the stored size. Returns bucket/key.

    source_modified is an ISO-8601 UTC timestamp of when the export was
    produced; it's stored as object metadata for the "Schedule updated" label.
    """
    import boto3

    key = os.environ.get("R2_SCHEDULE_UPCOMING_KEY", "").strip() or "ScheduleUpcoming.csv"
    bucket = (
        os.environ.get("R2_SCHEDULE_UPCOMING_BUCKET", "").strip()
        or os.environ.get("R2_BUCKET", "").strip()
        or "radiantcare-sanitized"
    )
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID'].strip()}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"].strip(),
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"].strip(),
        region_name="auto",
    )
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType="text/csv",
                  Metadata={"source-modified": source_modified})
    size = s3.head_object(Bucket=bucket, Key=key)["ContentLength"]
    if size != len(data):
        raise RuntimeError(f"R2 holds {size} bytes after upload, expected {len(data)}")
    return f"{bucket}/{key}"


def register_schedule_upload(server) -> None:
    """Add the upload route to the Flask server. auth.py lists UPLOAD_PATH as
    public (no Clerk session); the Bearer token is checked here instead."""
    from flask import request

    def _text(body: str, status: int):
        return body, status, {"Content-Type": "text/plain; charset=utf-8"}

    @server.route(UPLOAD_PATH, methods=["POST", "PUT"])
    def _schedule_upload():
        token = os.environ.get("SCHEDULE_UPLOAD_TOKEN", "").strip()
        if not token:
            return _text("Upload endpoint is not configured", 503)
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
            return _text("Unauthorized", 401)
        if (request.content_length or 0) > MAX_BYTES:
            return _text(f"Rejected: larger than {MAX_BYTES} bytes", 413)

        upload = request.files.get("file")
        data = upload.read() if upload is not None else request.get_data()

        ok, reason, rows = validate_csv(data)
        if not ok:
            print(f"[schedule_upload] rejected: {reason}", flush=True)
            return _text(f"Rejected: {reason}; existing schedule kept", 400)

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            where = put_schedule_upcoming(data, now)
        except Exception as exc:  # noqa: BLE001 — report storage failures to the flow
            print(f"[schedule_upload] R2 write failed: {exc}", flush=True)
            return _text("Storage write failed; existing schedule kept", 502)

        # Serve the new file on the next page load instead of after the TTL.
        try:
            from data.loader import load_schedule_upcoming
            load_schedule_upcoming.cache_clear()
        except Exception:  # noqa: BLE001
            pass

        print(f"[schedule_upload] stored {len(data):,} bytes, {rows:,} rows -> {where}", flush=True)
        return _text(f"OK {len(data)} bytes, {rows} rows", 200)
