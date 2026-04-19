#!/usr/bin/env python3
"""Build the PHI-sanitized mirror of the AURA reports directory.

Reads the raw data from DATA_DIR_RAW (OneDrive path) and writes de-identified
copies to DATA_DIR_SANITIZED, mirroring the folder structure exactly so the
existing data/loader.py reads the output unchanged when PHI_MODE=true.

Usage:
    PHI_SALT=<long-random-hex> python scripts/sanitize.py
    PHI_SALT=<…> python scripts/sanitize.py --upload

    --upload    After a successful sanitize, tar+gzip the sanitized directory
                and push it to Cloudflare R2 for the cloud app to download
                on next container boot. Requires R2_ACCOUNT_ID,
                R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, and R2_BUCKET
                in the environment.

The salt must match across runs so PatientId hashes remain stable across
incremental refreshes. Store it in your local .env file (gitignored).
"""

from __future__ import annotations

import io
import json
import os
import sys
import tarfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DATA_DIR_RAW, DATA_DIR_SANITIZED
from data.sanitize.core import load_salt
from data.sanitize.rules import sanitize_all


def _fmt_row(entry: dict) -> str:
    name = entry.get("name", "?")
    status = entry.get("status", "")
    files = entry.get("files", 0)
    rin = entry.get("rows_in", 0)
    rout = entry.get("rows_out", 0)
    dropped = ",".join(entry.get("dropped", []) or []) or "-"
    hashed = ",".join(entry.get("hashed", []) or []) or "-"
    short = entry.get("short_code_from") or "-"
    return (
        f"  {name:24s} {status:18s} files={files:<3d} "
        f"rows={rin:>9,}→{rout:>9,}  "
        f"dropped=[{dropped}]  hashed=[{hashed}]  code_from={short}"
    )


def main() -> int:
    salt = load_salt()

    raw = DATA_DIR_RAW
    out = DATA_DIR_SANITIZED

    if not raw.exists():
        print(f"ERROR: raw data dir does not exist: {raw}")
        return 2

    print(f"Raw:       {raw}")
    print(f"Sanitized: {out}")
    print(f"Salt:      {len(salt)} chars loaded from PHI_SALT")
    print()

    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    audit = sanitize_all(raw, out, salt)
    elapsed = time.time() - t0

    print("Per-dataset summary:")
    for entry in audit:
        print(_fmt_row(entry))
    print()

    # Totals
    total_files = sum(e.get("files", 0) for e in audit)
    total_in = sum(e.get("rows_in", 0) for e in audit)
    total_out = sum(e.get("rows_out", 0) for e in audit)
    print(
        f"Totals: {total_files} files, "
        f"{total_in:,} rows in → {total_out:,} rows out, "
        f"{elapsed:.1f}s"
    )

    # Write audit JSON (without salt, safe to keep alongside sanitized data)
    audit_path = out / "_sanitize_audit.json"
    audit_path.write_text(json.dumps({
        "raw_root": str(raw),
        "sanitized_root": str(out),
        "elapsed_seconds": round(elapsed, 2),
        "datasets": audit,
    }, indent=2, default=str))
    print(f"Audit log: {audit_path}")

    return 0


def upload_to_r2() -> int:
    """Tar-gzip DATA_DIR_SANITIZED and push it to Cloudflare R2.

    The cloud app downloads and extracts this tarball on container startup
    via scripts/bootstrap_data.py. R2 is S3-compatible, so we use boto3
    with the R2 endpoint.

    Env vars required:
        R2_ACCOUNT_ID          Cloudflare account ID (hex string in R2 URLs)
        R2_ACCESS_KEY_ID       Access key from "R2 → API Tokens → Create"
        R2_SECRET_ACCESS_KEY   Secret for that key
        R2_BUCKET              Bucket name (default: radiantcare-sanitized)

    Optional:
        R2_OBJECT              Object key (default: sanitized.tar.gz)
    """
    try:
        import boto3
        from botocore.config import Config as _BotoConfig
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        print("[upload] ERROR: boto3 not installed; `pip install boto3`.")
        return 1

    account_id = os.environ.get("R2_ACCOUNT_ID", "").strip()
    access_key = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    bucket = os.environ.get("R2_BUCKET", "radiantcare-sanitized").strip()
    object_key = os.environ.get("R2_OBJECT", "sanitized.tar.gz").strip()

    missing = [n for n, v in (
        ("R2_ACCOUNT_ID", account_id),
        ("R2_ACCESS_KEY_ID", access_key),
        ("R2_SECRET_ACCESS_KEY", secret_key),
    ) if not v]
    if missing:
        print(f"[upload] ERROR: missing env vars: {', '.join(missing)}")
        return 1
    if not DATA_DIR_SANITIZED.exists():
        print(f"[upload] ERROR: sanitized dir not found: {DATA_DIR_SANITIZED}")
        return 1

    def _filter(ti: tarfile.TarInfo) -> tarfile.TarInfo | None:
        base = os.path.basename(ti.name)
        if base in (".DS_Store",) or base.startswith("._"):
            return None
        return ti

    print(f"[upload] Packing {DATA_DIR_SANITIZED} …")
    t0 = time.time()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(DATA_DIR_SANITIZED), arcname="data", filter=_filter)
    size_mb = buf.tell() / 1e6
    pack_elapsed = time.time() - t0
    print(f"[upload]   tarball: {size_mb:.1f} MB (packed in {pack_elapsed:.1f}s)")

    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    print(f"[upload] PUT {bucket}/{object_key} @ {endpoint}")

    # R2 requires us to pin the region to "auto" and use path-style addressing.
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=_BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )

    buf.seek(0)
    try:
        s3.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=buf.getvalue(),
            ContentType="application/gzip",
            CacheControl="no-cache",
        )
    except (BotoCoreError, ClientError) as exc:
        print(f"[upload] ERROR: {exc}")
        return 1

    total = time.time() - t0
    print(f"[upload] OK — total {total:.1f}s")
    return 0


if __name__ == "__main__":
    rc = main()
    if rc == 0 and "--upload" in sys.argv[1:]:
        rc = upload_to_r2()
    sys.exit(rc)
