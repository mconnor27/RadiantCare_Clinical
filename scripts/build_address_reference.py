"""Build the local address-point reference used to geocode patient homes
without sending addresses to a third-party geocoder.

Sources (all public, downloaded once; no patient data is sent anywhere):
  * Thurston County Address Points (TCOMM) — structure-placed points
  * Washington State Parcels Project (geo.wa.gov "Current Parcels") — parcel
    centroids + situs address, for the neighbouring counties below
  * Grays Harbor County Parcel.gdb — the statewide layer has no Grays Harbor
    rows, so its parcels come from the county download (point-on-surface via
    GDAL's ogr2ogr)

Output: .geocache_phi/ref/address_reference.csv
        columns: addr, unit, city, zip, lat, lon, source, rank
        (rank: 0 = structure point, 1 = parcel/site point)

The output is gitignored/dockerignored (.geocache_phi/). Thurston's terms
restrict redistribution of substantial portions of its data — keep it local.

Usage:  python scripts/build_address_reference.py [--force]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REF_DIR = ROOT / ".geocache_phi" / "ref"
OUT_PATH = REF_DIR / "address_reference.csv"

THURSTON_PTS = ("https://tconline.co.thurston.wa.us/server/rest/services/ThurstonExt/"
                "Thurston_AddressPoints_TCOMM/FeatureServer/0/query")
WA_PARCELS = ("https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/"
              "Current_Parcels/FeatureServer/0/query")
GH_PARCEL_ZIP = "https://www.graysharbor.us/GIS/Data_Download/Parcel.gdb.zip"

# Statewide-layer county codes (COUNTY_NM coded domain = county FIPS).
# Thurston is pulled here too, as a parcel fallback behind its address points.
WA_COUNTIES = {
    "67": "Thurston", "41": "Lewis", "45": "Mason", "49": "Pacific",
    "15": "Cowlitz", "69": "Wahkiakum", "53": "Pierce",   # Pierce last: largest
}

PAGE = 2000
UA = {"User-Agent": "RadiantCare-address-reference/1.0"}


def _get_json(url, params, retries=8):
    q = urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(f"{url}?{q}", headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read())
            if "error" in d:
                raise RuntimeError(d["error"])
            return d
        except Exception as exc:
            if attempt == retries - 1:
                raise
            print(f"  retry {attempt + 1} ({exc})", file=sys.stderr)
            time.sleep(min(2 ** attempt, 30))


def _paged(url, where, fields, extra=None, workers=4, label=""):
    """Fetch all features matching `where`, paging by OBJECTID ranges.

    Offset paging fails on deep pages (the statewide service rejects offsets
    past ~240k), so fetch the ID list first and query ID windows instead.
    """
    ids = _get_json(url, {"where": where, "returnIdsOnly": "true", "f": "json"})["objectIds"] or []
    ids.sort()
    windows = [(ids[i], ids[min(i + PAGE, len(ids)) - 1]) for i in range(0, len(ids), PAGE)]
    base = {"outFields": ",".join(fields), "outSR": 4326, "f": "json"}
    base.update(extra or {})
    done = [0]

    def one(win):
        lo, hi = win
        d = _get_json(url, {**base, "where": f"({where}) AND OBJECTID>={lo} AND OBJECTID<={hi}"})
        done[0] += 1
        if done[0] % 20 == 0:
            print(f"  {label}: {done[0]}/{len(windows)} pages", flush=True)
        return d.get("features", [])

    with ThreadPoolExecutor(max_workers=workers) as pool:
        feats = [f for page in pool.map(one, windows) for f in page]
    print(f"  {label}: {len(feats):,} of {len(ids):,} features")
    return feats


def fetch_thurston_points():
    fields = ["ADDRESS", "Unit", "Post_Comm", "Post_Code", "Placement", "Long", "Lat"]
    # Thurston's server stalls on parallel requests — fetch serially.
    feats = _paged(THURSTON_PTS, "1=1", fields, {"returnGeometry": "true"},
                   workers=1, label="Thurston points")
    rows = []
    for f in feats:
        a = f["attributes"]
        g = f.get("geometry") or {}
        lat, lon = g.get("y", a.get("Lat")), g.get("x", a.get("Long"))
        addr = (a.get("ADDRESS") or "").split(",")[0].strip()
        if not addr or lat is None or lon is None:
            continue
        rows.append({
            "addr": addr, "unit": a.get("Unit") or "", "city": a.get("Post_Comm") or "",
            "zip": a.get("Post_Code") or "", "lat": lat, "lon": lon,
            "source": f"thurston_{(a.get('Placement') or '').lower()}",
            "rank": 0 if a.get("Placement") == "Structure" else 1,
        })
    return rows


def fetch_wa_parcels():
    fields = ["SITUS_ADDRESS", "SUB_ADDRESS", "SITUS_CITY_NM", "SITUS_ZIP_NR"]
    rows = []
    for code, name in WA_COUNTIES.items():
        where = f"COUNTY_NM='{code}' AND SITUS_ADDRESS IS NOT NULL AND SITUS_ADDRESS<>''"
        part = REF_DIR / f"part_wa_{name.lower()}.csv"
        if part.exists():
            print(f"  WA parcels {name}: using cached {part.name}")
            rows += pd.read_csv(part, dtype=str).to_dict("records")
            continue
        feats = _paged(WA_PARCELS, where, fields,
                       {"returnGeometry": "false", "returnCentroid": "true"},
                       workers=2, label=f"WA parcels {name}")
        county_rows = []
        for f in feats:
            a, c = f["attributes"], f.get("centroid") or {}
            if c.get("y") is None:
                continue
            county_rows.append({
                "addr": a["SITUS_ADDRESS"].strip(), "unit": a.get("SUB_ADDRESS") or "",
                "city": a.get("SITUS_CITY_NM") or "", "zip": a.get("SITUS_ZIP_NR") or "",
                "lat": c["y"], "lon": c["x"], "source": f"wa_parcel_{name.lower()}", "rank": 1,
            })
        rows += county_rows
        pd.DataFrame(county_rows).to_csv(part, index=False)
    return rows


def fetch_grays_harbor(force=False):
    gh_dir = REF_DIR / "gh"
    gh_dir.mkdir(parents=True, exist_ok=True)
    zpath = gh_dir / "Parcel.gdb.zip"
    if force or not zpath.exists():
        print("  downloading Grays Harbor Parcel.gdb.zip …")
        req = urllib.request.Request(GH_PARCEL_ZIP, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=600) as r, open(zpath, "wb") as fh:
            fh.write(r.read())
        with zipfile.ZipFile(zpath) as z:
            z.extractall(gh_dir)
    gdb = next(gh_dir.glob("*.gdb"))
    csv_out = gh_dir / "gh_parcels.csv"
    sql = ("SELECT SITUS AS addr, ZIPCODE AS zip, ST_PointOnSurface(Shape) AS geom "
           "FROM Parcel_poly WHERE SITUS IS NOT NULL AND TRIM(SITUS)<>''")
    csv_out.unlink(missing_ok=True)
    subprocess.run(["ogr2ogr", "-f", "CSV", str(csv_out), str(gdb),
                    "-t_srs", "EPSG:4326", "-dialect", "SQLite", "-sql", sql,
                    "-lco", "GEOMETRY=AS_XY"], check=True)
    df = pd.read_csv(csv_out, dtype=str)
    # ZIPCODE in this layer is the owner's mailing ZIP, not the situs ZIP —
    # left blank so matching relies on the address + distance check.
    print(f"  Grays Harbor parcels: {len(df):,}")
    return [{"addr": a.strip(), "unit": "", "city": "", "zip": "", "lat": float(y),
             "lon": float(x), "source": "gh_parcel", "rank": 1}
            for a, x, y in zip(df["addr"], df["X"], df["Y"]) if isinstance(a, str) and a.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download everything")
    args = ap.parse_args()
    REF_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    parts = []
    for name, fn in (("thurston_points", fetch_thurston_points),
                     ("grays_harbor", lambda: fetch_grays_harbor(force=args.force)),
                     ("wa_parcels", fetch_wa_parcels)):
        part = REF_DIR / f"part_{name}.csv"
        if part.exists() and not args.force:
            print(f"{name}: using cached {part.name}")
            parts.append(pd.read_csv(part, dtype=str))
            continue
        print(f"{name} …")
        pdf = pd.DataFrame(fn())
        pdf.to_csv(part, index=False)
        parts.append(pdf)

    df = pd.concat(parts, ignore_index=True)
    df["lat"] = df["lat"].astype(float).round(6)
    df["lon"] = df["lon"].astype(float).round(6)
    tmp = OUT_PATH.with_suffix(".tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(OUT_PATH)
    print(f"\nWrote {len(df):,} reference points → {OUT_PATH} ({time.time() - t0:.0f}s)")
    print(df["source"].value_counts().to_string())


if __name__ == "__main__":
    main()
