"""Local (offline) street-address matcher for patient home geocoding.

Matches patient addresses against the public address-point / parcel reference
built by scripts/build_address_reference.py — no address ever leaves the
machine. Used only in local (non-PHI) mode; the reference lives in the
gitignored .geocache_phi/ directory.

Match levels, tried in order (all restricted to candidates within MAX_KM of
the patient's ZIP centroid, preferring same ZIP / same city / building-placed
points):
  full    house number + full street (directionals and type included)
  core    house number + street name, ignoring a direction or street type
          that is missing on one side (never a conflicting one)
  fuzzy   house number + near-identical street name (spelling variants:
          CAPITAL/CAPITOL, OLD/OLDE), same ZIP or city only
  interp  same street, house number not listed — position interpolated
          between the nearest listed numbers on either side (or the nearest
          one when it's close), like a street-range geocoder
"""

from __future__ import annotations

import bisect
import difflib
import logging
import math
import re
import threading
from pathlib import Path

import pandas as pd

from config.settings import PROJECT_ROOT

logger = logging.getLogger(__name__)

REF_PATH = PROJECT_ROOT / ".geocache_phi" / "ref" / "address_reference.csv"
MAX_KM = 25.0
FUZZY_MIN = 0.85          # difflib ratio for spelling variants
INTERP_MAX_GAP = 200      # max house-number span between interpolation anchors
INTERP_MAX_SPAN_KM = 0.8  # anchors further apart than this aren't one street run
NEAREST_MAX_DIFF = 20     # one-sided: use the nearest listed number if this close

_DIRS = {
    "N": "N", "NORTH": "N", "S": "S", "SOUTH": "S", "E": "E", "EAST": "E",
    "W": "W", "WEST": "W", "NE": "NE", "NORTHEAST": "NE", "NW": "NW",
    "NORTHWEST": "NW", "SE": "SE", "SOUTHEAST": "SE", "SW": "SW", "SOUTHWEST": "SW",
}
_TYPES = {
    "ST": "ST", "STREET": "ST", "STR": "ST",
    "AVE": "AVE", "AVENUE": "AVE", "AV": "AVE",
    "RD": "RD", "ROAD": "RD",
    "DR": "DR", "DRIVE": "DR", "DRV": "DR",
    "LN": "LN", "LANE": "LN",
    "CT": "CT", "COURT": "CT", "CRT": "CT",
    "PL": "PL", "PLACE": "PL",
    "BLVD": "BLVD", "BOULEVARD": "BLVD",
    "WAY": "WAY", "WY": "WAY",
    "LOOP": "LOOP", "LP": "LOOP",
    "CIR": "CIR", "CIRCLE": "CIR",
    "TER": "TER", "TERRACE": "TER",
    "TRL": "TRL", "TRAIL": "TRL",
    "PKWY": "PKWY", "PARKWAY": "PKWY",
    "HWY": "HWY", "HIGHWAY": "HWY",
    "XING": "XING", "CROSSING": "XING",
    "PT": "PT", "POINT": "PT",
    "RUN": "RUN", "ROW": "ROW", "PATH": "PATH", "WALK": "WALK",
    "SQ": "SQ", "SQUARE": "SQ", "CV": "CV", "COVE": "CV",
    "LNDG": "LNDG", "LANDING": "LNDG", "VW": "VW", "VIEW": "VW",
    "HTS": "HTS", "HEIGHTS": "HTS", "ALY": "ALY", "ALLEY": "ALY",
    "BND": "BND", "BEND": "BND", "PASS": "PASS", "RDG": "RDG", "RIDGE": "RDG",
}
_ORDINALS = {
    "FIRST": "1ST", "SECOND": "2ND", "THIRD": "3RD", "FOURTH": "4TH", "FIFTH": "5TH",
    "SIXTH": "6TH", "SEVENTH": "7TH", "EIGHTH": "8TH", "NINTH": "9TH", "TENTH": "10TH",
    "ELEVENTH": "11TH", "TWELFTH": "12TH", "THIRTEENTH": "13TH", "FOURTEENTH": "14TH",
    "FIFTEENTH": "15TH", "SIXTEENTH": "16TH", "SEVENTEENTH": "17TH",
    "EIGHTEENTH": "18TH", "NINETEENTH": "19TH", "TWENTIETH": "20TH",
}
# Name words abbreviated inconsistently between sources (mapped on both sides).
_WORDS = {
    "MOUNT": "MT", "FORT": "FT", "SAINT": "ST", "PARK": "PK",
    "GARDENS": "GDNS", "GRDNS": "GDNS", "GARDEN": "GDN", "LAKE": "LK",
    "CREEK": "CRK", "MOUNTAIN": "MTN", "VALLEY": "VLY", "ISLAND": "IS",
    "HARBOR": "HBR", "SPRINGS": "SPGS", "SPRING": "SPG", "BEACH": "BCH",
}
_GENERIC_TYPES = {"RD", "ST", "AVE", "DR"}
_STRONG_TYPES = {"LOOP", "WAY", "CT", "PL", "LN", "CIR", "TER", "BLVD", "PKWY",
                 "AVE", "ST", "RD", "DR", "TRL"}
# Towns whose names show up glued onto Grays Harbor situs strings (which have
# no city field). Patient-side city tails are stripped using the patient's city.
_TAIL_TOWNS = [
    "OCEAN SHORES", "OCEAN CITY", "WESTPORT", "ABERDEEN", "HOQUIAM", "COSMOPOLIS",
    "MONTESANO", "ELMA", "MCCLEARY", "OAKVILLE", "GRAYLAND", "MOCLIPS", "COPALIS",
    "PACIFIC BEACH", "TAHOLAH", "AMANDA PARK", "QUINAULT", "HUMPTULIPS", "SATSOP",
    "BRADY", "PORTER", "MALONE", "TOKELAND", "NORTH COVE", "AXFORD", "CENTRAL PARK",
]

_TAIL_LAST = {t.split()[-1] for t in _TAIL_TOWNS}

_UNIT_WORDS = r"APT|APARTMENT|UNIT|SPC|SP|SPACE|LOT|STE|SUITE|TRLR|TRAILER|RM|ROOM|BLDG|NO"
_UNIT_TAIL = re.compile(rf"\s+(?:(?:{_UNIT_WORDS})\b\s*#?|#)\s*[\w-]*\s*$")
_STATE_ZIP_TAIL = re.compile(r"(?:\s+WA)?(?:\s+\d{5}(?:-\d{4})?)?\s*$")
_HWY = re.compile(
    r"\b(?:(?:US|U S|STATE|ST)\s+)?(?:HIGHWAY|HWY|ROUTE|RTE|RT)\s+(\d+)\b|\bSR\s*-?\s*(\d+)\b|\bUS\s*-?\s*(\d+)\b"
)
_NUM = re.compile(r"^(\d+)(?:[A-Z]|-[\w]+)?$")
_FRACTION = re.compile(r"^\d+/\d+$")
_BAD_PUNCT = re.compile(r"[.,;:'\"()]")


def _strip_tail_words(toks, phrase):
    w = phrase.split()
    if len(toks) > len(w) + 1 and toks[-len(w):] == w:
        return toks[:-len(w)]
    return toks


def normalize(address, city=None):
    """Return (number, full_street, core_street, (pre, types, post)) or None.

    `types` is a frozenset of street-type abbreviations (one street can carry
    two, e.g. "BINNS SWIGER LOOP RD"); the core drops all of them.
    """
    if not isinstance(address, str):
        return None
    s = address.upper()
    if "," in s:
        segs = [x.strip() for x in s.split(",")]
        s = next((x for x in segs if x[:1].isdigit()), segs[0])
    s = s.replace(" -", " ")
    s = _BAD_PUNCT.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for _ in range(3):
        s2 = _UNIT_TAIL.sub("", s).strip()
        s2 = _STATE_ZIP_TAIL.sub("", s2).strip()
        if s2 == s:
            break
        s = s2
    s = s.replace("#", " ").strip()
    s = _HWY.sub(lambda m: f"HWY {m.group(1) or m.group(2) or m.group(3)}", s)
    toks = s.split()
    if len(toks) < 2:
        return None
    m = _NUM.match(toks[0])
    if not m:
        return None
    num = m.group(1)
    toks = toks[1:]
    # "1234 1/2 MAIN", "12405 A BRONSON" — drop a fraction or lone unit letter
    if toks and (_FRACTION.match(toks[0]) or (len(toks[0]) == 1 and toks[0] not in _DIRS
                                               and len(toks) > 1)):
        toks = toks[1:]
    # Trailing city names (patient's own city; GH towns on the reference side)
    if city:
        toks = _strip_tail_words(toks, city.upper().strip())
    if toks and toks[-1] in _TAIL_LAST:
        for t in _TAIL_TOWNS:
            toks = _strip_tail_words(toks, t)
    toks = [_ORDINALS.get(t, _WORDS.get(t, _TYPES.get(t, t))) for t in toks]
    if not toks:
        return None

    # Cut trailing junk after the last street type (+ directional):
    # "FERN ST SW E103", "OCEAN SHORES BLVD SW OCEAN", "345TH ST S ROY".
    type_vals = set(_TYPES.values()) - {"HWY"}
    last_t = max((i for i, t in enumerate(toks) if i >= 1 and t in type_vals), default=None)
    if last_t is not None:
        j = last_t + 1
        if j < len(toks) and toks[j] in _DIRS:
            j += 1
        toks = toks[:j]

    pre = post = ""
    types = []
    if len(toks) > 1 and toks[0] in _DIRS:
        pre, toks = _DIRS[toks[0]], toks[1:]
    if len(toks) > 1 and toks[-1] in _DIRS:
        post, toks = _DIRS[toks[-1]], toks[:-1]
    full_mid = list(toks)
    # "BINNS SWIGER LOOP RD" ≈ "BINNS SWIGER LOOP": a generic type after a
    # strong one is redundant. (Not after VIEW/POINT/etc., which are usually
    # name words — "LAKE VIEW DR" must not collapse to "LAKE".)
    if len(toks) > 2 and toks[-1] in _GENERIC_TYPES and toks[-2] in _STRONG_TYPES:
        types.append(toks[-1])
        toks = toks[:-1]
    if len(toks) > 1 and toks[-1] in type_vals:
        types.append(toks[-1])
        toks = toks[:-1]
    name = " ".join(toks)
    full = " ".join(p for p in (pre, " ".join(full_mid), post) if p)
    return num, full, name, (pre, frozenset(types), post)


def _compatible(a, b):
    """Directionals may be missing on one side but must not conflict; street
    types must overlap when both sides state them."""
    return ((not a[0] or not b[0] or a[0] == b[0])
            and (not a[2] or not b[2] or a[2] == b[2])
            and (not a[1] or not b[1] or bool(a[1] & b[1])))


def _haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


_zcta = {"arr": None}
ZIP_RANK_MAX = 8   # patient ZIP must be among the 8 ZIP centres nearest the point (keeps 99.3% of true locations)


def _zcta_arrays():
    """(zips, lat, lon) numpy arrays of PNW ZIP centroids (97xxx–99xxx)."""
    if _zcta["arr"] is None:
        import numpy as np
        from utils.geocoding import _load_zcta_table
        t = {z: ll for z, ll in _load_zcta_table().items() if z[:2] in ("97", "98", "99")}
        zs = np.array(list(t.keys()))
        ll = np.array(list(t.values()), dtype=float).reshape(-1, 2)
        _zcta["arr"] = (zs, ll[:, 0], ll[:, 1])
    return _zcta["arr"]


def _zip_plausible(lat, lon, zip5):
    """True when zip5 is among the ZIP_RANK_MAX ZIP centroids nearest the
    point. Guards against a same-named street in a neighbouring town when the
    true address isn't in the reference. Unknown ZIPs (PO-box ZIPs) pass."""
    import numpy as np
    zs, zlat, zlon = _zcta_arrays()
    if not zip5 or not len(zs) or zip5 not in set(zs.tolist()):
        return True
    d = (zlat - lat) ** 2 + ((zlon - lon) * math.cos(math.radians(lat))) ** 2
    nearest = zs[np.argsort(d)[:ZIP_RANK_MAX]]
    return zip5 in nearest


class _Index:
    def __init__(self, df):
        self.lat = df["lat"].astype(float).to_numpy()
        self.lon = df["lon"].astype(float).to_numpy()
        self.zip = df["zip"].fillna("").astype(str).str[:5].to_numpy()
        self.city = df["city"].fillna("").astype(str).str.upper().str.strip().to_numpy()
        self.rank = df["rank"].astype(int).to_numpy()
        self.source = df["source"].to_numpy()
        self.full, self.core, self.parts, self.num = {}, {}, {}, {}
        self.by_num = {}      # number -> [(core, i)]  (fuzzy)
        self.street = {}      # core -> [i]            (interp)
        for i, a in enumerate(df["addr"].to_numpy()):
            n = normalize(a)
            if not n or n[0] == "0":
                continue
            self.parts[i] = n[3]
            self.num[i] = int(n[0])
            self.full.setdefault((n[0], n[1]), []).append(i)
            self.core.setdefault((n[0], n[2]), []).append(i)
            self.by_num.setdefault(n[0], []).append((n[2], i))
            self.street.setdefault(n[2], []).append(i)

    # -- helpers -------------------------------------------------------------
    def _near(self, i, zip_ll, city):
        """Distance (km) from the ZIP centroid, or None if out of range."""
        if zip_ll:
            d = _haversine_km(zip_ll[0], zip_ll[1], self.lat[i], self.lon[i])
            return d if d <= MAX_KM else None
        return 0.0 if city and self.city[i] == city else None

    def _pick(self, cands, n, zip5, city, zip_ll, guard):
        best = None
        for i in cands:
            if guard and not _compatible(n[3], self.parts[i]):
                continue
            d = self._near(i, zip_ll, city)
            if d is None:
                continue
            if not (zip5 and self.zip[i] == zip5) and not _zip_plausible(self.lat[i], self.lon[i], zip5):
                continue
            key = (0 if (zip5 and self.zip[i] == zip5) else 1,
                   0 if (city and self.city[i] == city) else 1,
                   self.rank[i], d)
            if best is None or key < best[0]:
                best = (key, i)
        return best[1] if best else None

    def _local_subset(self, cands, n, zip5, city, zip_ll):
        """Candidates in range, narrowed to same ZIP (or city) when any are."""
        ok = [i for i in cands
              if _compatible(n[3], self.parts[i]) and self._near(i, zip_ll, city) is not None]
        same_zip = [i for i in ok if zip5 and self.zip[i] == zip5]
        if same_zip:
            return same_zip
        same_city = [i for i in ok if city and self.city[i] == city]
        return same_city or ok

    def _interp(self, n, zip5, city, zip_ll):
        cands = self.street.get(n[2])
        if not cands:
            return None
        pts = self._local_subset(cands, n, zip5, city, zip_ll)
        if not pts:
            return None
        target = int(n[0])
        pts.sort(key=lambda i: self.num[i])
        nums = [self.num[i] for i in pts]
        k = bisect.bisect_left(nums, target)
        lo = pts[k - 1] if k > 0 else None
        hi = pts[k] if k < len(pts) else None
        if lo is not None and hi is not None:
            n_lo, n_hi = self.num[lo], self.num[hi]
            span = _haversine_km(self.lat[lo], self.lon[lo], self.lat[hi], self.lon[hi])
            if n_hi - n_lo <= INTERP_MAX_GAP and span <= INTERP_MAX_SPAN_KM:
                f = (target - n_lo) / (n_hi - n_lo) if n_hi != n_lo else 0.5
                return (self.lat[lo] + f * (self.lat[hi] - self.lat[lo]),
                        self.lon[lo] + f * (self.lon[hi] - self.lon[lo]))
        near = min((i for i in (lo, hi) if i is not None),
                   key=lambda i: abs(self.num[i] - target), default=None)
        if near is not None and abs(self.num[near] - target) <= NEAREST_MAX_DIFF:
            return self.lat[near], self.lon[near]
        return None

    # -- public --------------------------------------------------------------
    def match(self, address, city, zip5, zip_ll):
        """Return (lat, lon, source, level) or None.

        zip_ll: (lat, lon) centroid for the patient's ZIP, or None.
        """
        city = (city or "").upper().strip()
        n = normalize(address, city)
        if not n:
            return None

        i = self._pick(self.full.get((n[0], n[1]), ()), n, zip5, city, zip_ll, guard=False)
        if i is not None:
            return float(self.lat[i]), float(self.lon[i]), str(self.source[i]), "full"
        i = self._pick(self.core.get((n[0], n[2]), ()), n, zip5, city, zip_ll, guard=True)
        if i is not None:
            return float(self.lat[i]), float(self.lon[i]), str(self.source[i]), "core"

        # Spelling variants: same number, near-identical street, same ZIP/city.
        best = None
        for core, j in self.by_num.get(n[0], ()):
            if not ((zip5 and self.zip[j] == zip5) or (city and self.city[j] == city)
                    or (not self.zip[j] and not self.city[j])):
                continue
            if self._near(j, zip_ll, city) is None or not _compatible(n[3], self.parts[j]):
                continue
            r = difflib.SequenceMatcher(None, n[2], core).ratio()
            if r >= FUZZY_MIN and (best is None or r > best[0]) and (
                    (zip5 and self.zip[j] == zip5) or _zip_plausible(self.lat[j], self.lon[j], zip5)):
                best = (r, j)
        if best:
            j = best[1]
            return float(self.lat[j]), float(self.lon[j]), str(self.source[j]), "fuzzy"

        ll = self._interp(n, zip5, city, zip_ll)
        if ll and _zip_plausible(ll[0], ll[1], zip5):
            return float(ll[0]), float(ll[1]), "interpolated", "interp"
        return None


_index_lock = threading.Lock()
_index_memo = {"mtime": None, "index": None}


def get_index():
    """Load (memoized on file mtime) the reference index, or None if absent."""
    p = REF_PATH
    if not p.exists():
        return None
    mtime = p.stat().st_mtime
    with _index_lock:
        if _index_memo["mtime"] == mtime:
            return _index_memo["index"]
        idx = _load_pickled(mtime)
        if idx is None:
            df = pd.read_csv(p, dtype={"addr": str, "unit": str, "city": str, "zip": str})
            idx = _Index(df)
            _save_pickled(idx, mtime)
            logger.info("Built local address index: %d points, %d address keys",
                        len(df), len(idx.full))
        _index_memo.update(mtime=mtime, index=idx)
        return idx


# Normalizing ~800k reference rows takes a minute or more, so the built index
# is pickled next to the reference and reused until the reference or the
# matcher changes. Local file in the gitignored .geocache_phi/ only.
MATCHER_VERSION = "4"
_PICKLE_PATH = REF_PATH.with_name("address_index.pkl")


def _load_pickled(mtime):
    import pickle
    try:
        with open(_PICKLE_PATH, "rb") as fh:
            tag, idx = pickle.load(fh)
        if tag == (mtime, MATCHER_VERSION):
            return idx
    except Exception:
        pass
    return None


def _save_pickled(idx, mtime):
    import pickle
    try:
        tmp = _PICKLE_PATH.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            pickle.dump(((mtime, MATCHER_VERSION), idx), fh, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(_PICKLE_PATH)
    except Exception as exc:
        logger.warning("Could not cache address index: %s", exc)


def reference_available():
    return Path(REF_PATH).exists()
