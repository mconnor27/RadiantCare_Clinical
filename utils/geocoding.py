"""Patient address geocoding pipeline.

Uses a two-tier approach:
  1. **ZCTA centroid lookup** — US Census ZCTA centroid table (data/zcta_centroids.csv)
     for instant, offline, accurate ZIP-to-coordinate mapping (~33K entries).
  2. **Nominatim fallback** — for the rare ZIPs not in the ZCTA table (PO Box ZIPs,
     non-geographic ZIPs).  Results are validated against a bounding box.

All results are cached persistently in data/geocode_cache.csv.
"""

import re
import logging
import threading
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from functools import lru_cache

from config.settings import PROJECT_ROOT, DEPARTMENTS, DEPARTMENT_COLORS

logger = logging.getLogger(__name__)

CACHE_PATH = PROJECT_ROOT / "data" / "geocode_cache.csv"
ADDR_CACHE_PATH = PROJECT_ROOT / "data" / "geocode_addr_cache.csv"
ZCTA_PATH = PROJECT_ROOT / "data" / "zcta_centroids.csv"

# Bounding box for all US territory incl. Alaska, Hawaii, PR (validates Nominatim)
_US_LAT_MIN, _US_LAT_MAX = 17.5, 72.0
_US_LON_MIN, _US_LON_MAX = -180.0, -65.0

# Department coordinates — actual clinic addresses
# Lacey:     4525 3rd Ave SE, Suite 100, Lacey, WA 98503
# Aberdeen:  1200 Basich Blvd, Aberdeen, WA 98520
# Centralia: 2015 Cooks Hill Rd, Centralia, WA 98531
DEPT_COORDS = {
    "Lacey": (47.0452, -122.8258),
    "Centralia": (46.7141, -123.0101),
    "Aberdeen": (46.9754, -123.8157),
}

# ---------------------------------------------------------------------------
# ZIP normalization
# ---------------------------------------------------------------------------

_ZIP_STANDARD = re.compile(r"^(\d{5})(?:-\d{4})?$")
_ZIP_DUAL = re.compile(r"^(\d{5})[/,]\s*\d{5}")
_ZIP_SIX = re.compile(r"^(\d{5})\d$")


def normalize_zip(raw_zip):
    """Normalize a raw ZIP value to a 5-digit string, or None if invalid.

    Handles ZIP+4, dual ZIPs, 6-digit typos, and junk values.
    """
    if pd.isna(raw_zip):
        return None
    s = str(raw_zip).strip()
    if not s:
        return None

    m = _ZIP_STANDARD.match(s)
    if m:
        return m.group(1)

    m = _ZIP_DUAL.match(s)
    if m:
        return m.group(1)

    m = _ZIP_SIX.match(s)
    if m:
        return m.group(1)

    return None


# ---------------------------------------------------------------------------
# Address cleaning
# ---------------------------------------------------------------------------

_PO_BOX = re.compile(r"^P\.?O\.?\s*BOX\b", re.IGNORECASE)

_PHYSICAL_PATTERNS = [
    # (Physical: 460 N Mt View Dr, Hoodsport, WA 98548)
    re.compile(r"[\(\[]\s*physical\s*:\s*(.+?)[\)\]]?\s*$", re.IGNORECASE),
    # physical: 145 Oneil Road, Elma, WA
    re.compile(r"^physical\s*:\s*(.+)$", re.IGNORECASE),
    # Physical Address - 1305 Alexander St #32, Centralia WA 98531
    re.compile(r"^physical\s+address\s*[-:]\s*(.+)$", re.IGNORECASE),
    # 207 Mattson Road Oakville, Wa 98568 (Physical)
    re.compile(r"^(.+?)\s*\(physical\)\s*$", re.IGNORECASE),
]

_STREET_LIKE = re.compile(r"^\d+\s+\w")


def extract_physical_address(line1, line2):
    """Extract the best geocodable street address from Line1/Line2.

    Returns the physical street address when Line1 is a PO Box and
    Line2 contains a physical address.  Falls back to Line1.
    """
    l1 = str(line1).strip() if pd.notna(line1) else ""
    l2 = str(line2).strip() if pd.notna(line2) else ""

    is_po = bool(_PO_BOX.match(l1)) if l1 else False

    if is_po and l2:
        # Try to extract physical address from Line2
        for pat in _PHYSICAL_PATTERNS:
            m = pat.match(l2)
            if m:
                return m.group(1).strip()

        # If Line2 looks like a street address (starts with digit + word)
        if _STREET_LIKE.match(l2):
            return l2

    return l1 if l1 else None


# ---------------------------------------------------------------------------
# ZCTA centroid lookup (primary geocoding source)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_zcta_table():
    """Load the Census ZCTA centroid table into memory (cached for session)."""
    if not ZCTA_PATH.exists():
        logger.warning("ZCTA centroid file not found: %s", ZCTA_PATH)
        return {}
    df = pd.read_csv(ZCTA_PATH, dtype={"zip5": str})
    lookup = {}
    for _, row in df.iterrows():
        lookup[row["zip5"]] = (row["lat"], row["lon"])
    logger.info("Loaded %d ZCTA centroids", len(lookup))
    return lookup


@lru_cache(maxsize=1)
def _build_prefix_centroids():
    """Build a dict of 3-digit ZIP prefix → median centroid from all matching ZCTAs.

    Used as a fallback for PO Box ZIPs and other non-geographic ZIPs that
    aren't in the ZCTA table.
    """
    table = _load_zcta_table()
    if not table:
        return {}
    from collections import defaultdict
    prefix_coords = defaultdict(list)
    for z, (lat, lon) in table.items():
        prefix_coords[z[:3]].append((lat, lon))

    centroids = {}
    for prefix, coords in prefix_coords.items():
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        centroids[prefix] = (np.median(lats), np.median(lons))
    return centroids


def _zcta_lookup(zip5):
    """Look up a ZIP in the ZCTA centroid table, with prefix fallback.

    Returns (lat, lon, city_label) or None if not found.

    Strategy:
      1. Exact match in ZCTA table
      2. Fallback to 3-digit prefix centroid (for PO Box ZIPs like 98507, 98508)
    """
    table = _load_zcta_table()
    coords = table.get(zip5)
    if coords:
        return coords[0], coords[1], zip5

    # Prefix fallback for PO Box / non-geographic ZIPs
    prefix_centroids = _build_prefix_centroids()
    prefix = zip5[:3]
    centroid = prefix_centroids.get(prefix)
    if centroid:
        logger.debug("ZIP %s not in ZCTA; using prefix %sxx centroid", zip5, prefix)
        return centroid[0], centroid[1], zip5

    return None


# ---------------------------------------------------------------------------
# Result validation
# ---------------------------------------------------------------------------

def _is_valid_us_coord(lat, lon):
    """Check if coordinates fall within the continental US bounding box."""
    return (_US_LAT_MIN <= lat <= _US_LAT_MAX and
            _US_LON_MIN <= lon <= _US_LON_MAX)


# ---------------------------------------------------------------------------
# Persistent cache
# ---------------------------------------------------------------------------

def _load_cache():
    """Read geocode_cache.csv if it exists, purging invalid entries."""
    if CACHE_PATH.exists():
        try:
            df = pd.read_csv(CACHE_PATH, dtype={"zip5": str})
            if {"zip5", "lat", "lon"}.issubset(df.columns):
                before = len(df)
                # Purge entries with company-name city labels (known bad geocodes)
                if "city_label" in df.columns:
                    bad_mask = df["city_label"].str.contains(
                        r"\b(?:USA|Inc|Corp|LLC|Ltd|Logistics|Vibrant|Schenker|Murphy|Mattress|Honda|Auto|Hydraulics|Research Station|University of)\b",
                        case=False, na=False, regex=True,
                    )
                    df = df[~bad_mask]
                # Purge entries outside continental US
                df = df[df.apply(lambda r: _is_valid_us_coord(r["lat"], r["lon"]), axis=1)]
                purged = before - len(df)
                if purged > 0:
                    logger.info("Purged %d invalid entries from geocode cache", purged)
                    _save_cache(df)
                return df
        except Exception as exc:
            logger.warning("Failed to read geocode cache: %s", exc)
    return pd.DataFrame(columns=["zip5", "lat", "lon", "city_label", "geocoded_at", "source"])


def _save_cache(df):
    """Write geocode cache to CSV."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CACHE_PATH, index=False)
    logger.info("Saved geocode cache: %d entries -> %s", len(df), CACHE_PATH)


# ---------------------------------------------------------------------------
# Nominatim geocoding
# ---------------------------------------------------------------------------

_geocoder = None
_rate_limiter = None
_geocoder_lock = threading.Lock()


def _get_geocoder():
    """Lazy-init Nominatim geocoder with rate limiter (thread-safe)."""
    global _geocoder, _rate_limiter
    if _geocoder is None:
        with _geocoder_lock:
            if _geocoder is None:
                from geopy.geocoders import Nominatim
                from geopy.extra.rate_limiter import RateLimiter

                _geocoder = Nominatim(
                    user_agent="radiantcare_clinical_dashboard",
                    timeout=10,
                )
                _rate_limiter = RateLimiter(
                    _geocoder.geocode,
                    min_delay_seconds=1.5,
                    max_retries=1,
                    error_wait_seconds=10.0,
                )
    return _rate_limiter


def _geocode_single_zip(zip5):
    """Geocode a single 5-digit ZIP via Nominatim (fallback only).

    Returns (lat, lon, city_label) or None on failure.
    Validates results against the continental US bounding box.
    """
    geocode = _get_geocoder()
    try:
        location = geocode({"postalcode": zip5, "country": "US"})

        if location:
            lat, lon = location.latitude, location.longitude
            if not _is_valid_us_coord(lat, lon):
                logger.warning(
                    "Nominatim result for ZIP %s outside US bounds: (%.4f, %.4f) — skipped",
                    zip5, lat, lon,
                )
                return None
            city_label = location.address.split(",")[0] if location.address else zip5
            # Reject results where city_label looks like a business name
            if re.search(r"\b(USA|Inc|Corp|LLC|Ltd)\b", city_label, re.IGNORECASE):
                logger.warning(
                    "Nominatim result for ZIP %s looks like a business: %r — skipped",
                    zip5, city_label,
                )
                return None
            return lat, lon, city_label
    except Exception as exc:
        logger.warning("Geocoding failed for ZIP %s: %s", zip5, exc)

    return None


def geocode_zips(zip_list):
    """Geocode a list of 5-digit ZIP codes.

    Strategy:
      1. Check persistent cache
      2. Look up in ZCTA centroid table (instant, ~33K entries)
      3. Fall back to Nominatim API (rate-limited) with validation

    Returns a DataFrame with columns: zip5, lat, lon, city_label, geocoded_at, source.
    New results are appended to the persistent cache.
    """
    cache = _load_cache()
    cached_zips = set(cache["zip5"].values) if not cache.empty else set()

    needed = [z for z in zip_list if z and z not in cached_zips]

    if not needed:
        logger.info("All %d ZIPs found in cache", len(zip_list))
        return cache

    # --- Tier 1: ZCTA centroid table (instant, offline) ---
    new_rows = []
    still_needed = []
    for zip5 in needed:
        result = _zcta_lookup(zip5)
        if result:
            lat, lon, city_label = result
            new_rows.append({
                "zip5": zip5,
                "lat": lat,
                "lon": lon,
                "city_label": city_label,
                "geocoded_at": datetime.now().isoformat(),
                "source": "zcta",
            })
        else:
            still_needed.append(zip5)

    if new_rows:
        logger.info("ZCTA lookup resolved %d / %d ZIPs", len(new_rows), len(needed))

    # --- Tier 2: Nominatim API (slow, rate-limited) ---
    if still_needed:
        logger.info(
            "Falling back to Nominatim for %d ZIPs not in ZCTA table...",
            len(still_needed),
        )
        for i, zip5 in enumerate(still_needed):
            result = _geocode_single_zip(zip5)
            if result:
                lat, lon, city_label = result
                new_rows.append({
                    "zip5": zip5,
                    "lat": lat,
                    "lon": lon,
                    "city_label": city_label,
                    "geocoded_at": datetime.now().isoformat(),
                    "source": "nominatim",
                })
            if (i + 1) % 25 == 0:
                logger.info("  Geocoded %d / %d ZIPs...", i + 1, len(still_needed))

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        cache = pd.concat([cache, new_df], ignore_index=True)
        _save_cache(cache)
        logger.info("Geocoding complete: %d new entries added", len(new_rows))

    return cache


@lru_cache(maxsize=1)
def load_geocode_cache():
    """Load the geocode cache into memory (lru_cache for session lifetime)."""
    return _load_cache()


# ---------------------------------------------------------------------------
# Address geocoding (for referral provider locations)
# ---------------------------------------------------------------------------

def _load_addr_cache():
    """Read address geocode cache if it exists."""
    if not ADDR_CACHE_PATH.exists():
        return pd.DataFrame(columns=["addr_key", "lat", "lon", "geocoded_at"])
    try:
        df = pd.read_csv(ADDR_CACHE_PATH, dtype={"addr_key": str})
        df = df.dropna(subset=["lat", "lon"])
        return df
    except Exception:
        return pd.DataFrame(columns=["addr_key", "lat", "lon", "geocoded_at"])


def _save_addr_cache(df):
    """Write address geocode cache to CSV."""
    df.to_csv(ADDR_CACHE_PATH, index=False)
    logger.info("Saved address geocode cache: %d entries", len(df))


def _addr_geocode_key(address, city, state, zip_code):
    """Build a normalized cache key from address components."""
    parts = [
        (address or "").strip().upper(),
        (city or "").strip().upper(),
        (state or "").strip().upper(),
        (str(zip_code or "").strip()[:5]),
    ]
    return "|".join(parts)


def geocode_addresses(addr_records, max_nominatim=20):
    """Geocode a list of address dicts, using cache + Nominatim.

    Each record: {"address", "city", "state", "zip_code"} (all strings).
    Returns DataFrame with: addr_key, lat, lon.

    Uses a two-tier approach:
      1. Check persistent address cache
      2. Nominatim freeform query for uncached addresses (rate-limited)
    Falls back to ZIP centroid if Nominatim fails.

    Args:
        max_nominatim: Max Nominatim API calls per invocation to avoid
            blocking the page. Remaining addresses use ZIP centroid
            fallback and get precise geocoding on subsequent calls.
    """
    if not addr_records:
        return pd.DataFrame(columns=["addr_key", "lat", "lon"])

    cache = _load_addr_cache()
    cached_keys = set(cache["addr_key"].values) if not cache.empty else set()

    # Deduplicate by key
    key_to_record = {}
    for rec in addr_records:
        key = _addr_geocode_key(rec["address"], rec["city"], rec["state"], rec["zip_code"])
        if key not in key_to_record:
            key_to_record[key] = rec

    needed = {k: v for k, v in key_to_record.items() if k not in cached_keys}

    if not needed:
        return cache

    # Geocode via Nominatim (city + state + zip — skip street for reliability)
    geocode = _get_geocoder()
    new_rows = []
    zip_cache = geocode_zips([normalize_zip(r["zip_code"]) for r in needed.values()
                              if normalize_zip(r.get("zip_code"))])
    zip_lookup = {}
    if not zip_cache.empty:
        zip_lookup = dict(zip(zip_cache["zip5"], zip(zip_cache["lat"], zip_cache["lon"])))

    nominatim_calls = 0
    for key, rec in needed.items():
        address = (rec.get("address") or "").strip()
        city = (rec.get("city") or "").strip()
        state = (rec.get("state") or "").strip()
        zip5 = normalize_zip(rec.get("zip_code"))
        lat = lon = None

        # Only hit Nominatim if under the batch limit
        if nominatim_calls < max_nominatim:
            # Try full street address first
            if address and city and state:
                query = f"{address}, {city}, {state}"
                if zip5:
                    query += f" {zip5}"
                try:
                    location = geocode(query + ", US")
                    nominatim_calls += 1
                    if location and _is_valid_us_coord(location.latitude, location.longitude):
                        lat, lon = location.latitude, location.longitude
                except Exception as exc:
                    logger.debug("Full address geocode failed for %s: %s", key, exc)

            # Fall back to city + state + zip
            if lat is None and city and state:
                query = f"{city}, {state}"
                if zip5:
                    query += f" {zip5}"
                try:
                    location = geocode(query + ", US")
                    nominatim_calls += 1
                    if location and _is_valid_us_coord(location.latitude, location.longitude):
                        lat, lon = location.latitude, location.longitude
                except Exception as exc:
                    logger.debug("City geocode failed for %s: %s", key, exc)

        # Fall back to ZIP centroid
        if lat is None and zip5 and zip5 in zip_lookup:
            lat, lon = zip_lookup[zip5]

        if lat is not None and lon is not None:
            new_rows.append({
                "addr_key": key,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "geocoded_at": datetime.now().isoformat(),
            })

    if nominatim_calls >= max_nominatim and len(needed) > max_nominatim:
        logger.info(
            "Address geocoding: capped at %d Nominatim calls (%d remaining will use ZIP fallback this pass)",
            nominatim_calls, len(needed) - max_nominatim,
        )

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        cache = pd.concat([cache, new_df], ignore_index=True)
        _save_addr_cache(cache)
        logger.info("Address geocoding: %d new entries added", len(new_rows))

    return cache


# ---------------------------------------------------------------------------
# Patient data aggregation
# ---------------------------------------------------------------------------

def prepare_patient_geo_data(df):
    """Add geocoded lat/lon to patient data and aggregate by ZIP + Department.

    Args:
        df: Patient DataFrame with at least Zip, City, Department, PatientId columns.

    Returns:
        DataFrame with columns:
            zip5, lat, lon, patient_count, primary_city, department
    """
    if df.empty:
        return pd.DataFrame(
            columns=["zip5", "lat", "lon", "patient_count", "primary_city", "department"]
        )

    work = df.copy()
    work["zip5"] = work["Zip"].apply(normalize_zip)
    work = work.dropna(subset=["zip5"])

    if work.empty:
        return pd.DataFrame(
            columns=["zip5", "lat", "lon", "patient_count", "primary_city", "department"]
        )

    # Ensure cache covers all ZIPs
    unique_zips = work["zip5"].unique().tolist()
    cache = geocode_zips(unique_zips)

    has_dept = "Department" in work.columns
    group_cols = ["zip5"]
    if has_dept:
        group_cols.append("Department")

    # Aggregate: patient count per ZIP (per department)
    agg = (
        work.groupby(group_cols)
        .agg(
            patient_count=("PatientId", "nunique"),
            primary_city=("City", lambda x: x.mode().iloc[0] if not x.mode().empty else ""),
        )
        .reset_index()
    )

    # Clean city names
    agg["primary_city"] = agg["primary_city"].str.strip().str.title()

    # Merge with geocode cache
    agg = agg.merge(cache[["zip5", "lat", "lon"]], on="zip5", how="left")
    agg = agg.dropna(subset=["lat", "lon"])

    return agg


def bezier_arc(from_lat, from_lon, to_lat, to_lon, num_points=30, curvature=0.25):
    """Generate curved arc points between two coordinates using a quadratic Bezier.

    The control point is offset perpendicular to the straight line, producing
    a smooth arc similar to flow-map visualizations.

    Returns:
        (lats, lons) — two lists of floats for the curved path.
    """
    dlat = to_lat - from_lat
    dlon = to_lon - from_lon

    mid_lat = (from_lat + to_lat) / 2
    mid_lon = (from_lon + to_lon) / 2

    # Perpendicular offset (rotate 90° CCW so arcs bow "left" of travel dir)
    cos_lat = np.cos(np.radians(mid_lat))
    perp_lat = -dlon * cos_lat
    perp_lon = dlat / cos_lat

    perp_len = np.sqrt(perp_lat ** 2 + perp_lon ** 2)
    if perp_len > 0:
        perp_lat /= perp_len
        perp_lon /= perp_len

    dist = np.sqrt(dlat ** 2 + (dlon * cos_lat) ** 2)

    ctrl_lat = mid_lat + perp_lat * curvature * dist
    ctrl_lon = mid_lon + perp_lon * curvature * dist

    t = np.linspace(0, 1, num_points)
    lats = ((1 - t) ** 2 * from_lat + 2 * (1 - t) * t * ctrl_lat + t ** 2 * to_lat)
    lons = ((1 - t) ** 2 * from_lon + 2 * (1 - t) * t * ctrl_lon + t ** 2 * to_lon)

    return lats.tolist(), lons.tolist()


def get_department_patient_flows(geo_df, min_patients=2):
    """Compute flow lines from patient origin ZIPs to each department.

    Args:
        geo_df: Output of prepare_patient_geo_data().
        min_patients: Minimum patient count for a ZIP to get a flow line.

    Returns:
        List of dicts: {from_lat, from_lon, to_lat, to_lon, dept, count, city_label}
    """
    if geo_df.empty or "Department" not in geo_df.columns:
        return []

    flows = []
    for dept in DEPARTMENTS:
        dept_data = geo_df[geo_df["Department"] == dept]
        if dept_data.empty:
            continue

        dept_coord = DEPT_COORDS.get(dept)
        if not dept_coord:
            continue

        origins = dept_data[dept_data["patient_count"] >= min_patients]
        for _, row in origins.iterrows():
            # Skip if origin is essentially the same location as department
            if abs(row["lat"] - dept_coord[0]) < 0.01 and abs(row["lon"] - dept_coord[1]) < 0.01:
                continue
            flows.append({
                "from_lat": row["lat"],
                "from_lon": row["lon"],
                "to_lat": dept_coord[0],
                "to_lon": dept_coord[1],
                "dept": dept,
                "count": row["patient_count"],
                "city_label": row.get("primary_city", row["zip5"]),
                "zip5": row["zip5"],
                "addr_key": row.get("addr_key", ""),
                "institution": row.get("institution", ""),
            })

    return flows


# ---------------------------------------------------------------------------
# Background geocoding helper
# ---------------------------------------------------------------------------

_geocoding_in_progress = False
_geocoding_complete = False


def trigger_background_geocode(zip_list):
    """Start geocoding in a background thread (non-blocking).

    Call this on first page load. The page can poll is_geocoding_complete()
    to know when to refresh.
    """
    global _geocoding_in_progress, _geocoding_complete

    if _geocoding_in_progress or _geocoding_complete:
        return

    cache = _load_cache()
    cached_zips = set(cache["zip5"].values) if not cache.empty else set()
    needed = [z for z in zip_list if z and z not in cached_zips]

    if not needed:
        _geocoding_complete = True
        return

    _geocoding_in_progress = True

    def _run():
        global _geocoding_in_progress, _geocoding_complete
        try:
            geocode_zips(zip_list)
            # Clear the lru_cache so fresh data is picked up
            load_geocode_cache.cache_clear()
        finally:
            _geocoding_in_progress = False
            _geocoding_complete = True

    threading.Thread(target=_run, daemon=True).start()
    logger.info("Background geocoding started for %d ZIPs", len(needed))


def is_geocoding_complete():
    """Check if background geocoding has finished."""
    return _geocoding_complete


def geocoding_progress():
    """Return (cached_count, total_needed) for progress display."""
    cache = _load_cache()
    return len(cache), 0  # total_needed not tracked; use cached count
