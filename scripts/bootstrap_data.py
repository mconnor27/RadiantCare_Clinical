#!/usr/bin/env python3
"""Download the latest sanitized dataset from Cloudflare R2.

Runs once at container startup on the Railway side — the cloud host never
sees the raw OneDrive export, only the pre-sanitized tarball uploaded by
the nightly local job.

Environment variables:
    R2_ACCOUNT_ID           (required) — Cloudflare account ID
    R2_ACCESS_KEY_ID        (required) — R2 API token Access Key
    R2_SECRET_ACCESS_KEY    (required) — R2 API token Secret
    R2_BUCKET               (required) — bucket name
                                         (default: radiantcare-sanitized)
    R2_OBJECT               (optional) — object key
                                         (default: sanitized.tar.gz)
    DATA_SANITIZED          (optional) — extraction target directory
                                         (default: /app/data)

Exit codes:
    0 — success, OR skipped because env missing and existing data present
    1 — download/extract failed AND no usable existing data

Idempotent: safe to run on every container boot. Atomic-swap extraction
prevents half-unpacked state from being served.
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import tarfile
import time
from pathlib import Path


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, "").strip()
    return v or default


def main() -> int:
    try:
        import boto3
        from botocore.config import Config as _BotoConfig
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        print("[bootstrap] ERROR: boto3 not installed; `pip install boto3`.")
        return 1

    account_id = _env("R2_ACCOUNT_ID")
    access_key = _env("R2_ACCESS_KEY_ID")
    secret_key = _env("R2_SECRET_ACCESS_KEY")
    bucket = _env("R2_BUCKET", "radiantcare-sanitized")
    object_key = _env("R2_OBJECT", "sanitized.tar.gz")

    target = Path(_env("DATA_SANITIZED", "/app/data"))
    has_existing = target.exists() and any(target.iterdir())

    if not (account_id and access_key and secret_key):
        if has_existing:
            print("[bootstrap] R2 env vars not set. Using pre-existing data at "
                  f"{target}.")
            return 0
        print("[bootstrap] ERROR: R2 env vars not set and no local data.")
        return 1

    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    print(f"[bootstrap] Fetching s3://{bucket}/{object_key} @ {endpoint}")

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
            connect_timeout=30,
            read_timeout=300,
        ),
    )

    start = time.time()
    try:
        resp = s3.get_object(Bucket=bucket, Key=object_key)
        content = resp["Body"].read()
    except (BotoCoreError, ClientError) as exc:
        print(f"[bootstrap] Download failed: {exc}")
        if has_existing:
            print(f"[bootstrap] Continuing with stale data at {target}.")
            return 0
        return 1

    size_mb = len(content) / 1e6
    elapsed = time.time() - start
    print(f"[bootstrap] Downloaded {size_mb:.1f} MB in {elapsed:.1f}s.")

    # Atomic-swap extraction: unpack into staging dir, then swap into place.
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / (target.name + "._staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
            # Reject tarball entries that try to escape the staging dir.
            for member in tar.getmembers():
                member_path = (staging / member.name).resolve()
                if not str(member_path).startswith(str(staging.resolve())):
                    raise RuntimeError(
                        f"Refusing to extract outside staging: {member.name}"
                    )
            # filter="data" applies the safe-extraction policy that becomes
            # mandatory in Python 3.14 (silences the DeprecationWarning).
            tar.extractall(path=staging, filter="data")
    except Exception as exc:
        print(f"[bootstrap] Extraction failed: {exc}")
        shutil.rmtree(staging, ignore_errors=True)
        if has_existing:
            print(f"[bootstrap] Continuing with stale data at {target}.")
            return 0
        return 1

    # The uploader packs the sanitized dir under arcname="data".
    inner = staging / "data"
    source_dir = inner if inner.is_dir() else staging

    # Optional second subtree: pre-built parquet caches (e.g. BillingEnriched).
    # Lives at staging/data_cache/, gets installed under PROJECT_ROOT/.data_cache_phi/
    # so the loaders find it on first request — no 10s cold rebuild.
    cache_subtree = staging / "data_cache"
    if cache_subtree.is_dir():
        project_root = Path(__file__).resolve().parent.parent
        phi = os.environ.get("PHI_MODE", "").lower() in ("1", "true", "yes", "on")
        cache_target = project_root / (".data_cache_phi" if phi else ".data_cache")
        cache_target.mkdir(parents=True, exist_ok=True)
        installed = 0
        for entry in cache_subtree.iterdir():
            try:
                if entry.is_dir():
                    # Subdirectories (e.g. MachineDowntimeFields_per_date/) — copy
                    # the whole tree. copytree fails if the target exists, so
                    # remove it first to keep the install idempotent.
                    dst = cache_target / entry.name
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(str(entry), str(dst))
                    installed += sum(1 for _ in dst.rglob("*") if _.is_file())
                else:
                    shutil.copy2(str(entry), str(cache_target / entry.name))
                    installed += 1
            except Exception as exc:
                print(f"[bootstrap]   cache {entry.name} install failed: {exc}")
        if installed:
            print(f"[bootstrap]   pre-warmed cache: {installed} file(s) → {cache_target}")

    # Swap into place. We don't keep an "_old" rollback copy because
    # Path.rename() fails with OSError 18 (cross-device link) when /app/data
    # happens to be a mount point (common in Railway's squashfs image),
    # and the rollback offered no protection we weren't already getting
    # from verifying the extraction succeeded above.
    if target.exists():
        shutil.rmtree(target)
    shutil.move(str(source_dir), str(target))

    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)

    print(f"[bootstrap] Installed to {target}")
    try:
        n_entries = len(list(target.iterdir()))
        print(f"[bootstrap]   top-level entries: {n_entries}")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
