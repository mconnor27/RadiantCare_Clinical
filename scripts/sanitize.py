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

# Force PHI_MODE before importing config so the post-sanitize enrichment step
# reads from DATA_DIR_SANITIZED and writes its parquet into .data_cache_phi/.
# Sanitize itself reads from DATA_DIR_RAW directly and is unaffected.
os.environ["PHI_MODE"] = "true"

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
    enriched = ",".join(entry.get("enriched", []) or []) or "-"
    short = entry.get("short_code_from") or "-"
    return (
        f"  {name:24s} {status:18s} files={files:<3d} "
        f"rows={rin:>9,}→{rout:>9,}  "
        f"enriched=[{enriched}]  dropped=[{dropped}]  hashed=[{hashed}]  "
        f"code_from={short}"
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
        # Availability ships via its own live R2 feed (Power Automate →
        # availability.csv), not the daily tarball. Excluding it here keeps
        # the daily redeploy from clobbering whatever the live feed wrote
        # most recently.
        norm = ti.name.replace("\\", "/")
        if "/Incremental/Availability" in norm or norm.endswith("/Incremental/Availability"):
            return None
        # Determinism: zero out per-file timestamps and ownership so an
        # unchanged dataset produces an unchanged tarball, byte-for-byte.
        # That lets the SHA-based skip-if-unchanged check below avoid a
        # pointless PUT + Railway redeploy when nothing meaningful changed.
        ti.mtime = 0
        ti.uid = 0
        ti.gid = 0
        ti.uname = ""
        ti.gname = ""
        return ti

    print(f"[upload] Packing {DATA_DIR_SANITIZED} …")
    t0 = time.time()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(DATA_DIR_SANITIZED), arcname="data", filter=_filter)
        # Ship pre-built derived parquets so production starts warm —
        # bootstrap_data.py extracts the `data_cache/` subtree into
        # /app/.data_cache_phi/ on container boot.
        # Critical: the big-4 raw-loader parquets are included so Railway
        # never re-parses 600K-row CSVs on cold boot (transient peak was
        # ~+1.7 GB RSS during categorize). Also the Fields date-index +
        # per-date sidecars so Level-III drill-down hits the parquet
        # fast-path on first navigation.
        from config.settings import PROJECT_ROOT
        cache_dir = PROJECT_ROOT / ".data_cache_phi"
        cache_stems = (
            # Raw-loader parquets (categorical-encoded)
            "Billing",
            "TreatmentDetail",
            "Workflow",
            "DowntimeGaps",
            "MedOncReferrals",
            # Derived caches
            "BillingEnriched",
            "DowntimeGaps_transformed",
            "DowntimeGaps_gap_evt",
            "DowntimeGaps_fd_evt",
        )
        cache_added = 0
        for stem in cache_stems:
            for ext in (".parquet", ".sig"):
                p = cache_dir / f"{stem}{ext}"
                if p.exists():
                    tar.add(str(p), arcname=f"data_cache/{stem}{ext}", filter=_filter)
                    cache_added += 1
        # Ship the MachineDowntimeFields date-index (json) and per-date
        # parquet sidecars built by load_downtime_fields_for_date. These are
        # what make Level-III drill-down fast on first navigation.
        idx_json = cache_dir / "MachineDowntimeFields.idx.json"
        if idx_json.exists():
            tar.add(str(idx_json), arcname=f"data_cache/{idx_json.name}", filter=_filter)
            cache_added += 1
        per_date_dir = cache_dir / "MachineDowntimeFields_per_date"
        if per_date_dir.is_dir():
            for f in per_date_dir.glob("*.parquet"):
                tar.add(str(f),
                        arcname=f"data_cache/{per_date_dir.name}/{f.name}",
                        filter=_filter)
                cache_added += 1
        if cache_added:
            print(f"[upload]   + {cache_added} cache file(s) from {cache_dir.name}/")
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

    # Skip-if-unchanged: hash the tarball bytes (deterministic via _filter),
    # compare with the SHA stored as metadata on the existing R2 object. If
    # they match, skip both the PUT and the Railway redeploy — production
    # already has identical data, so a redeploy is pure churn (cold start,
    # cache rebuild, deployment-list noise).
    import hashlib
    payload = buf.getvalue()
    new_sha = hashlib.sha256(payload).hexdigest()
    try:
        head = s3.head_object(Bucket=bucket, Key=object_key)
        existing_sha = (head.get("Metadata") or {}).get("sha256")
    except (BotoCoreError, ClientError):
        existing_sha = None

    if existing_sha == new_sha:
        print(f"[upload] Tarball unchanged (sha256 {new_sha[:12]}…) — "
              f"skipping PUT + redeploy.")
        return 0

    buf.seek(0)
    try:
        s3.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=payload,
            ContentType="application/gzip",
            CacheControl="no-cache",
            Metadata={"sha256": new_sha},
        )
    except (BotoCoreError, ClientError) as exc:
        print(f"[upload] ERROR: {exc}")
        return 1

    total = time.time() - t0
    print(f"[upload] OK — total {total:.1f}s (sha256 {new_sha[:12]}…)")

    _trigger_redeploy()
    return 0


def _trigger_redeploy() -> None:
    """Redeploy the Railway service so production pulls the fresh tarball.

    Uses `railway redeploy` — requires Railway CLI installed and logged in,
    with the Clinical project linked (one-time `railway link`). Falls back
    to a DEPLOY_HOOK_URL POST if the CLI isn't available (e.g., if sanitize
    is ever moved off this Mac).

    Non-fatal: the upload already succeeded — if redeploy fails, the
    tarball still sits in R2 and the next container restart will pick it up.
    """
    import shutil
    import subprocess

    service = os.environ.get("RAILWAY_SERVICE", "radiantcare-clinical").strip()

    if shutil.which("railway"):
        try:
            result = subprocess.run(
                ["railway", "redeploy", "-s", service, "-y"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                print(f"[upload] Railway redeploy triggered for {service}.")
                return
            print(
                f"[upload] railway redeploy failed (rc={result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        except Exception as exc:
            print(f"[upload] railway redeploy errored: {exc}")

    hook = os.environ.get("DEPLOY_HOOK_URL", "").strip()
    if hook:
        try:
            import urllib.request
            req = urllib.request.Request(hook, data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                print(f"[upload] Deploy hook fired: HTTP {r.status}")
        except Exception as exc:
            print(f"[upload] Deploy hook failed (upload still OK): {exc}")


def warm_caches() -> int:
    """Pre-build derived parquet caches against the freshly sanitized data.

    Runs after sanitize so the local app and (via the R2 tarball) production
    both start with warm caches instead of paying multi-second cold rebuilds
    on first page load. Non-fatal — failures don't block upload or redeploy.

    Warms:
      - The four monster loaders (billing, treatment_detail, workflow,
        downtime_gaps) — building these from CSVs at runtime causes a
        transient RSS spike of ~2 GB during categorize/dedup, which is what
        drove the original "huge cold-start memory" problem on Railway.
      - BillingEnriched (~10-15s cold) — RVU/OPPS merges + payor + revenue
      - DowntimeGaps_{transformed,gap_evt,fd_evt} (~4-15s cold) — dedup +
        confidence scoring + boundary interpolation
      - MedOncReferrals — read_excel of PRCS .xlsx exports peaks at ~170 MB
      - MachineDowntimeFields date-index (~0.5s cold; powers Level-III strip)
    """
    targets = [
        # Raw loaders that write categorical-typed parquet sidecars
        ("Billing",          "data.loader", "load_billing"),
        ("TreatmentDetail",  "data.loader", "load_treatment_detail"),
        ("Workflow",         "data.loader", "load_workflow"),
        ("DowntimeGaps",     "data.loader", "load_downtime_gaps"),
        ("MedOncReferrals",  "data.loader", "load_medonc_referrals"),
        # Derived caches
        ("BillingEnriched",       "data.billing_enrichment",      "_get_enriched_billing"),
        ("DowntimeGaps_xform",    "data.downtime_gaps_transform", "_get_transformed_gaps"),
    ]
    for label, mod_name, fn_name in targets:
        try:
            from importlib import import_module
            print(f"[warm] Building {label} parquet…")
            t0 = time.time()
            df = getattr(import_module(mod_name), fn_name)()
            print(f"[warm]   OK — {len(df):,} rows in {time.time()-t0:.1f}s")
        except Exception as exc:
            print(f"[warm]   WARN ({label}): {exc}  (will rebuild lazily on next page load)")

    # Pre-build the per-date index used by load_downtime_fields_for_date.
    try:
        from data.loader import _downtime_fields_date_index
        print("[warm] Building MachineDowntimeFields date index…")
        t0 = time.time()
        idx = _downtime_fields_date_index()
        print(f"[warm]   OK — {len(idx):,} dates in {time.time()-t0:.1f}s")
    except Exception as exc:
        print(f"[warm]   WARN (Fields index): {exc}")
    return 0


if __name__ == "__main__":
    rc = main()
    if rc == 0:
        warm_caches()
    if rc == 0 and "--upload" in sys.argv[1:]:
        rc = upload_to_r2()
    sys.exit(rc)
