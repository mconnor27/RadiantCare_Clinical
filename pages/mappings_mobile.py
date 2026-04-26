"""Mobile-only consolidated mapping manager.

Admin-only page at /mobile/mappings. Three tabs (Diagnoses, Payors, Providers)
each rendering a tappable card list — designed for triaging unreviewed entries
during idle time on a phone. Tapping a card opens an edit drawer that writes
through the same reviews_db helpers as the desktop modal managers.

Desktop manager modals live in pages/diagnosis.py, pages/billing.py, and
pages/referrals.py and are unchanged.
"""

from __future__ import annotations

import dash
import dash_mantine_components as dmc
from dash import (
    ALL, callback, clientside_callback, ctx,
    Input, Output, State, dcc, html, no_update,
)
from dash_iconify import DashIconify
import pandas as pd

from config.settings import PRIMARY, NEUTRAL, ABMS_SPECIALTIES, normalize_specialty
from utils.diagnosis_categories import SUBCATEGORIES, CATEGORIES
from utils.permissions import is_admin
from data.reviews_db import (
    get_all_diagnosis_overrides,
    upsert_diagnosis_override,
    set_diagnosis_reviewed_bulk,
    get_all_payor_mappings,
    upsert_payor_mapping,
    get_standardized_payor_counts,
    rename_standardized_payor,
    delete_standardized_payor,
    get_all_referring_overrides,
    upsert_referring,
    set_reviewed_bulk,
    upsert_insurance_rate,
    get_all_insurance_rates,
    get_all_institutions,
    add_institution,
    rename_institution,
    delete_institution,
    sync_institutions_from_physicians,
)


dash.register_page(
    __name__,
    path="/mobile/mappings",
    name="Mobile Mappings",
    order=200,  # high order keeps it out of any auto-iterated nav
)


PAGE_ID = "mmap"

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

BROAD_PAYOR_CATEGORIES = [
    "Medicare", "Medicaid", "Private", "Military/VA",
    "Workers Comp", "Tribal/IHS", "Self Pay", "Other/Unknown",
]

PHDSC_CATEGORIES = [
    "1 - Medicare", "2 - Medicaid/CHIP", "3 - Other Govt",
    "4 - Corrections", "5 - Private", "6 - BCBS",
    "8 - No Payment", "9 - Other",
]

SORT_OPTIONS = [
    {"value": "impact", "label": "Most impact"},
    {"value": "recent", "label": "Most recent"},
    {"value": "alpha",  "label": "A–Z"},
]


def _id(suffix: str) -> str:
    return f"{PAGE_ID}-{suffix}"


# --------------------------------------------------------------------------
# Data loaders — wrap the existing builders so we touch one source of truth.
# Imports are lazy to avoid pulling heavy datasets until the page is opened.
# --------------------------------------------------------------------------

def _load_diag_rows() -> list[dict]:
    """Pool the curated catalog with the referral review queue.

    The catalog (~991 codes from diagnosis_subcategories.csv) is the canonical
    code list. The review queue (built from rad-onc + med-onc referrals)
    surfaces *new* ICD codes never in the catalog plus free-text diagnoses
    that need human classification. Free-text entries are keyed by their
    lowercased description; ICD entries by code. ``row_key`` is the unique
    identifier across both sources.
    """
    from pages.diagnosis import _build_diag_mgr_data
    from pages.referrals import _build_diag_grid_data

    catalog_rows, _ = _build_diag_mgr_data()
    catalog_codes = {r.get("icd_code") for r in catalog_rows if r.get("icd_code")}

    pooled = []
    for r in catalog_rows:
        code = r.get("icd_code") or ""
        pooled.append({
            **r,
            "row_key": f"icd:{code}" if code else "",
            "origin": "catalog",
        })

    try:
        rq_rows, _count, _stats = _build_diag_grid_data()
    except Exception as e:
        print(f"[mmap] review-queue load failed: {e}", flush=True)
        rq_rows = []

    for r in rq_rows:
        code = r.get("icd_code") or ""
        desc = r.get("description") or ""
        # Skip ICD entries already represented by the catalog (catalog wins)
        if code and code in catalog_codes:
            continue
        if code:
            row_key = f"icd:{code}"
        elif desc:
            row_key = f"text:{desc.lower()}"
        else:
            continue
        pooled.append({
            **r,
            "row_key": row_key,
        })

    return pooled


def _load_provider_rows() -> list[dict]:
    from pages.referrals import _build_rpm_grid_data
    rows, _stats = _build_rpm_grid_data()
    return rows


def _load_payor_rows() -> list[dict]:
    """Mappings tab data: raw_name + counts + current standardization."""
    from pages.billing import _get_enriched_billing, _seed_payor_mappings_if_needed

    _seed_payor_mappings_if_needed()
    mappings = get_all_payor_mappings()

    counts: dict[str, int] = {}
    try:
        df = _get_enriched_billing()
        if not df.empty and "PrimaryInsurance" in df.columns:
            counts = df["PrimaryInsurance"].value_counts().to_dict()
    except Exception:
        pass

    rows = []
    for m in mappings:
        rows.append({
            "raw_name": m["raw_name"],
            "event_count": int(counts.get(m["raw_name"], 0)),
            "standardized_payor": m.get("standardized_payor") or "",
            "broad_category": m.get("broad_category") or "",
            "phdsc_category": m.get("phdsc_category") or "9",
            "reviewed": bool(m.get("reviewed")),
        })
    return rows


def _load_payor_entities() -> list[dict]:
    return [
        {"name": e["name"], "mapping_count": int(e.get("mapping_count") or 0)}
        for e in get_standardized_payor_counts()
        if e.get("name")
    ]


def _load_institutions() -> list[dict]:
    """Institutions list with provider counts derived from referring overrides."""
    sync_institutions_from_physicians()
    inst_names = set(get_all_institutions())
    counts: dict[str, int] = {n: 0 for n in inst_names}
    for ov in get_all_referring_overrides().values():
        name = (ov.get("institution") or "").strip()
        if name:
            counts[name] = counts.get(name, 0) + 1
    return [
        {"name": n, "mapping_count": counts.get(n, 0)}
        for n in sorted(counts.keys(), key=lambda s: s.lower())
    ]


# --------------------------------------------------------------------------
# Filter / sort helpers
# --------------------------------------------------------------------------

def _filter_unreviewed(rows: list[dict], scope: str) -> list[dict]:
    if scope == "unreviewed":
        return [r for r in rows if not r.get("reviewed")]
    return rows


def _search_match(row: dict, q: str, fields: tuple[str, ...]) -> bool:
    if not q:
        return True
    q = q.strip().lower()
    if not q:
        return True
    for f in fields:
        v = row.get(f)
        if v and q in str(v).lower():
            return True
    return False


def _sort_rows(rows: list[dict], sort_key: str, *, impact_field: str,
               recent_field: str | None, alpha_field: str) -> list[dict]:
    if sort_key == "alpha":
        return sorted(rows, key=lambda r: str(r.get(alpha_field) or "").lower())
    if sort_key == "recent" and recent_field:
        # last_referral may be "MM/DD/YYYY"; fall back to impact when blank
        def _k(r):
            v = r.get(recent_field) or ""
            try:
                return pd.Timestamp(v)
            except Exception:
                return pd.Timestamp("1900-01-01")
        return sorted(rows, key=_k, reverse=True)
    # default: impact (numeric desc, then alpha)
    return sorted(
        rows,
        key=lambda r: (-int(r.get(impact_field) or 0), str(r.get(alpha_field) or "").lower()),
    )


# --------------------------------------------------------------------------
# Card builders
# --------------------------------------------------------------------------

_CARD_PAPER = dict(p="sm", radius="md", withBorder=True, shadow="xs", mb=8)


def _badge(text: str, color: str = "gray", variant: str = "light"):
    if not text:
        return None
    return dmc.Badge(text, color=color, variant=variant, size="sm",
                     styles={"root": {"textTransform": "none", "fontWeight": 500}})


def _reviewed_dot(reviewed: bool):
    return DashIconify(
        icon="tabler:circle-check-filled" if reviewed else "tabler:circle-dashed",
        width=18,
        color="#16A34A" if reviewed else "#9CA3AF",
    )


def _card_button(card_id: dict, children) -> dmc.UnstyledButton:
    return dmc.UnstyledButton(
        id=card_id,
        n_clicks=0,
        children=dmc.Paper(
            **_CARD_PAPER,
            className="mmap-card",
            children=children,
        ),
        style={"width": "100%", "textAlign": "left"},
    )


def _diag_card(row: dict):
    code = row.get("icd_code", "") or ""
    desc = row.get("description", "") or ""
    cat = row.get("category", "") or ""
    sub = row.get("subcategory", "") or ""
    pts = int(row.get("patients") or 0)
    reviewed = bool(row.get("reviewed"))
    origin = row.get("origin") or "catalog"
    row_key = row.get("row_key") or (f"icd:{code}" if code else f"text:{desc.lower()}")

    # Header badge: ICD code for coded entries, "free-text" for narrative ones.
    if code:
        head_badge = _badge(code, color="blue")
    else:
        head_badge = _badge("free-text", color="orange")

    # Right-side origin chip (only for review-queue rows; catalog entries omit it).
    origin_chip = None
    if origin == "medonc":
        origin_chip = _badge("med-onc", color="grape")
    elif origin == "rad-onc":
        origin_chip = _badge("rad-onc", color="violet")
    elif origin == "both":
        origin_chip = _badge("both", color="indigo")

    # Count label adapts to source — catalog tracks unique patients,
    # review queue tracks referral instances.
    if origin == "catalog":
        count_label = f"{pts:,} pt" if pts else "—"
    else:
        count_label = f"{pts:,} ref" if pts else "—"

    return _card_button(
        {"type": _id("card"), "tab": "diag", "key": row_key},
        children=[
            dmc.Group(justify="space-between", wrap="nowrap", gap=6, children=[
                dmc.Group(gap=6, wrap="nowrap", children=[
                    head_badge,
                    dmc.Text(count_label, size="xs", c="dimmed"),
                    origin_chip,
                ]),
                _reviewed_dot(reviewed),
            ]),
            dmc.Text(desc, size="sm", lineClamp=2, mt=4,
                     style={"lineHeight": 1.3}),
            dmc.Group(gap=6, mt=6, children=[
                _badge(cat or "Uncategorized",
                       color="grape" if cat else "gray"),
                _badge(sub, color="violet") if sub else None,
            ]),
        ],
    )


def _payor_card(row: dict):
    raw = row.get("raw_name", "")
    std = row.get("standardized_payor") or ""
    broad = row.get("broad_category") or ""
    phdsc = row.get("phdsc_category") or ""
    n = int(row.get("event_count") or 0)
    reviewed = bool(row.get("reviewed"))

    google_url = "https://www.google.com/search?q=" + raw.replace(" ", "+")

    return _card_button(
        {"type": _id("card"), "tab": "payor", "key": raw},
        children=[
            dmc.Group(justify="space-between", wrap="nowrap", gap=6, children=[
                dmc.Text(raw, size="sm", fw=600, lineClamp=2,
                         style={"flex": 1, "lineHeight": 1.25}),
                _reviewed_dot(reviewed),
            ]),
            dmc.Group(gap=6, mt=6, children=[
                _badge(f"{n:,} events" if n else "0 events", color="gray"),
                _badge(std or "Unmapped",
                       color="green" if std else "red"),
                _badge(broad, color="indigo") if broad else None,
                _badge(phdsc, color="cyan") if phdsc else None,
            ]),
            dmc.Group(gap=4, mt=6, children=[
                html.A(
                    DashIconify(icon="tabler:brand-google", width=14),
                    href=google_url, target="_blank", rel="noopener",
                    title="Google search",
                    style={"color": "#6B7280", "display": "inline-flex"},
                ),
                dmc.Text(" Look up", size="xs", c="dimmed"),
            ]),
        ],
    )


def _payor_entity_card(row: dict):
    name = row.get("name", "")
    cnt = int(row.get("mapping_count") or 0)
    return _card_button(
        {"type": _id("card"), "tab": "payor-entity", "key": name},
        children=[
            dmc.Group(justify="space-between", wrap="nowrap", children=[
                dmc.Text(name, size="sm", fw=600, lineClamp=2,
                         style={"flex": 1}),
                _badge(f"{cnt} maps", color="gray"),
            ]),
        ],
    )


def _provider_card(row: dict):
    name = row.get("name", "")
    npi = row.get("npi", "")
    spec = row.get("specialty", "") or ""
    inst = row.get("institution", "") or ""
    addr = row.get("full_address", "") or ""
    pts = int(row.get("patient_count") or 0)
    reviewed = bool(row.get("reviewed"))
    row_key = row.get("row_key") or f"{npi}|{row.get('address_key', '')}"

    npi_url = f"https://npiregistry.cms.hhs.gov/provider-view/{npi}" if npi else ""
    addr_search = "https://www.google.com/search?q=" + addr.replace(" ", "+") if addr else ""

    children = [
        dmc.Group(justify="space-between", wrap="nowrap", gap=6, children=[
            dmc.Text(name or "(no name)", size="sm", fw=600, lineClamp=2,
                     style={"flex": 1, "lineHeight": 1.25}),
            _reviewed_dot(reviewed),
        ]),
        dmc.Group(gap=6, mt=4, children=[
            _badge(f"{pts:,} ref" if pts else "—", color="gray"),
            _badge(spec or "No specialty",
                   color="teal" if spec else "red"),
        ]),
    ]
    if inst:
        children.append(dmc.Text(inst, size="xs", c="dimmed",
                                 lineClamp=1, mt=4))
    if addr:
        children.append(dmc.Text(addr, size="xs", c="dimmed",
                                 lineClamp=1, mt=2))

    icon_links = []
    if npi_url:
        icon_links.append(html.A(
            DashIconify(icon="tabler:id-badge-2", width=14),
            href=npi_url, target="_blank", rel="noopener",
            title=f"NPPES: {npi}",
            style={"color": "#6B7280", "display": "inline-flex"},
        ))
    if addr_search:
        icon_links.append(html.A(
            DashIconify(icon="tabler:map-pin", width=14),
            href=addr_search, target="_blank", rel="noopener",
            title="Google maps/search",
            style={"color": "#6B7280", "display": "inline-flex"},
        ))
    if icon_links:
        children.append(dmc.Group(gap=8, mt=6, children=icon_links))

    return _card_button(
        {"type": _id("card"), "tab": "provider", "key": row_key},
        children=children,
    )


def _institution_card(row: dict):
    name = row.get("name", "")
    cnt = int(row.get("mapping_count") or 0)
    return _card_button(
        {"type": _id("card"), "tab": "institution", "key": name},
        children=[
            dmc.Group(justify="space-between", wrap="nowrap", children=[
                dmc.Text(name, size="sm", fw=600, lineClamp=2,
                         style={"flex": 1}),
                _badge(f"{cnt} provider" + ("s" if cnt != 1 else ""), color="gray"),
            ]),
        ],
    )


def _empty_state(msg: str):
    return dmc.Center(
        dmc.Stack(align="center", gap=4, children=[
            DashIconify(icon="tabler:check", width=32, color="#9CA3AF"),
            dmc.Text(msg, size="sm", c="dimmed"),
        ]),
        h=120,
    )


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------

def _filter_bar(prefix: str, *, with_sort: bool = True, with_search: bool = True,
                default_sort: str = "impact"):
    """Triage controls: unreviewed/all toggle + sort + collapsible search."""
    children = [
        dmc.SegmentedControl(
            id=_id(f"{prefix}-scope"),
            value="unreviewed",
            data=[
                {"value": "unreviewed", "label": "Unreviewed"},
                {"value": "all", "label": "All"},
            ],
            fullWidth=True, size="xs", color="grape",
        ),
    ]
    row2 = []
    if with_sort:
        row2.append(dmc.Select(
            id=_id(f"{prefix}-sort"),
            value=default_sort,
            data=SORT_OPTIONS,
            clearable=False,
            size="xs",
            style={"flex": 1},
        ))
    if with_search:
        row2.append(dmc.TextInput(
            id=_id(f"{prefix}-search"),
            placeholder="Search…",
            leftSection=DashIconify(icon="tabler:search", width=14),
            size="xs",
            style={"flex": 1.4},
            debounce=300,
        ))
    if row2:
        children.append(dmc.Group(gap=6, grow=True, children=row2))
    children.append(dmc.Text(id=_id(f"{prefix}-count"),
                             size="xs", c="dimmed", ta="right"))
    return dmc.Stack(gap=6, children=children)


def _list_panel(prefix: str, *, with_sort: bool = True, with_search: bool = True,
                default_sort: str = "impact"):
    """Filter bar + scrollable card list."""
    return dmc.Stack(gap=8, children=[
        _filter_bar(prefix, with_sort=with_sort, with_search=with_search,
                    default_sort=default_sort),
        dcc.Loading(
            type="dot", color=PRIMARY,
            children=html.Div(id=_id(f"{prefix}-list"),
                              style={"minHeight": 80}),
        ),
    ])


def _drawer():
    return dmc.Drawer(
        id=_id("drawer"),
        position="bottom",
        size="85%",
        opened=False,
        padding="md",
        title=dmc.Text(id=_id("drawer-title"), fw=700),
        zIndex=10500,
        children=dcc.Loading(
            id=_id("drawer-loading"),
            type="dot",
            color=PRIMARY,
            children=html.Div(id=_id("drawer-body")),
            parent_style={"minHeight": "120px"},
        ),
    )


def _access_denied():
    return dmc.Center(
        dmc.Paper(
            dmc.Stack(align="center", gap="md", children=[
                DashIconify(icon="tabler:lock", width=48, color=PRIMARY),
                dmc.Title("Access denied", order=3, c=PRIMARY),
                dmc.Text("Data Mappings is restricted to admins.",
                         c=NEUTRAL["text_secondary"]),
            ]),
            p=40, radius="md", shadow="sm", withBorder=True, maw=420,
        ),
        h="60vh",
    )


def _header():
    return html.Div(
        style={"display": "flex", "justifyContent": "space-between",
               "alignItems": "flex-end", "marginBottom": "12px", "gap": "8px"},
        children=[
            dcc.Link(
                DashIconify(icon="tabler:arrow-left", width=24, color="#4B5563"),
                href="/mobile",
                title="Back",
                style={"display": "inline-flex", "alignItems": "center",
                       "padding": "4px"},
            ),
            html.A(
                html.Img(src="/assets/radiantcare.png",
                         style={"height": "32px", "objectFit": "contain"}),
                href="https://radiantcare.app", target="_blank",
            ),
            html.Div(id="mobile-auth-user-chip",
                     style={"display": "flex", "alignItems": "flex-end",
                            "height": "26px", "minWidth": "26px"}),
        ],
    )


def layout():
    if not is_admin():
        return dmc.Container(size="sm", px="xs", pt=4, children=[
            _header(),
            _access_denied(),
        ])

    return dmc.Container(
        size="sm", px="xs", pt=4, pb="xl",
        children=[
            # Initial-load trigger
            dcc.Interval(id=_id("boot"), interval=300, n_intervals=0,
                         max_intervals=1),
            # Per-source data caches (full unfiltered rows)
            dcc.Store(id=_id("store-diag")),
            dcc.Store(id=_id("store-payor")),
            dcc.Store(id=_id("store-payor-entity")),
            dcc.Store(id=_id("store-provider")),
            dcc.Store(id=_id("store-institution")),
            # Active edit context: {"tab": "...", "key": "..."}
            dcc.Store(id=_id("edit-store")),
            _drawer(),

            _header(),
            dmc.Title("Data Mappings", order=3, c=PRIMARY, ta="center",
                      fw=700, mb="sm"),

            dmc.Tabs(
                id=_id("tabs"),
                value="diag",
                color="grape",
                variant="pills",
                children=[
                    dmc.TabsList(grow=True, children=[
                        dmc.TabsTab("Diagnoses", value="diag"),
                        dmc.TabsTab("Payors", value="payor"),
                        dmc.TabsTab("Providers", value="provider"),
                    ]),

                    dmc.TabsPanel(value="diag", pt="sm", children=[
                        _list_panel("diag"),
                    ]),

                    dmc.TabsPanel(value="payor", pt="sm", children=[
                        dmc.Tabs(
                            value="map",
                            children=[
                                dmc.TabsList(children=[
                                    dmc.TabsTab("Mappings", value="map"),
                                    dmc.TabsTab("Entities", value="ent"),
                                ]),
                                dmc.TabsPanel(value="map", pt="sm", children=[
                                    _list_panel("payor"),
                                ]),
                                dmc.TabsPanel(value="ent", pt="sm", children=[
                                    dmc.Group(gap=6, mb=6, children=[
                                        dmc.TextInput(
                                            id=_id("payor-entity-add-name"),
                                            placeholder="New payor name…",
                                            size="xs",
                                            style={"flex": 1},
                                        ),
                                        dmc.Button(
                                            "Add", id=_id("payor-entity-add-btn"),
                                            size="xs", color="grape",
                                        ),
                                    ]),
                                    dmc.Text(id=_id("payor-entity-add-msg"),
                                             size="xs", c="dimmed"),
                                    _list_panel("payor-entity",
                                                with_sort=False,
                                                default_sort="alpha"),
                                ]),
                            ],
                        ),
                    ]),

                    dmc.TabsPanel(value="provider", pt="sm", children=[
                        dmc.Tabs(
                            value="prov",
                            children=[
                                dmc.TabsList(children=[
                                    dmc.TabsTab("Providers", value="prov"),
                                    dmc.TabsTab("Institutions", value="inst"),
                                ]),
                                dmc.TabsPanel(value="prov", pt="sm", children=[
                                    _list_panel("provider"),
                                ]),
                                dmc.TabsPanel(value="inst", pt="sm", children=[
                                    dmc.Group(gap=6, mb=6, children=[
                                        dmc.TextInput(
                                            id=_id("institution-add-name"),
                                            placeholder="New institution…",
                                            size="xs",
                                            style={"flex": 1},
                                        ),
                                        dmc.Button(
                                            "Add", id=_id("institution-add-btn"),
                                            size="xs", color="grape",
                                        ),
                                    ]),
                                    dmc.Text(id=_id("institution-add-msg"),
                                             size="xs", c="dimmed"),
                                    _list_panel("institution",
                                                with_sort=False,
                                                default_sort="alpha"),
                                ]),
                            ],
                        ),
                    ]),
                ],
            ),
        ],
    )


# --------------------------------------------------------------------------
# Initial data load — pulled lazily once, then cached in stores
# --------------------------------------------------------------------------

@callback(
    Output(_id("store-diag"), "data"),
    Output(_id("store-payor"), "data"),
    Output(_id("store-payor-entity"), "data"),
    Output(_id("store-provider"), "data"),
    Output(_id("store-institution"), "data"),
    Input(_id("boot"), "n_intervals"),
    State(_id("store-diag"), "data"),
    prevent_initial_call=False,
)
def _boot_load(n, existing):
    if not is_admin():
        return [], [], [], [], []
    if existing:  # already loaded
        return no_update, no_update, no_update, no_update, no_update
    try:
        diag = _load_diag_rows()
    except Exception as e:
        print(f"[mmap] diag load failed: {e}", flush=True)
        diag = []
    try:
        payor = _load_payor_rows()
    except Exception as e:
        print(f"[mmap] payor load failed: {e}", flush=True)
        payor = []
    try:
        pe = _load_payor_entities()
    except Exception as e:
        print(f"[mmap] payor entities load failed: {e}", flush=True)
        pe = []
    try:
        prov = _load_provider_rows()
    except Exception as e:
        print(f"[mmap] provider load failed: {e}", flush=True)
        prov = []
    try:
        inst = _load_institutions()
    except Exception as e:
        print(f"[mmap] institutions load failed: {e}", flush=True)
        inst = []
    return diag, payor, pe, prov, inst


# --------------------------------------------------------------------------
# List rendering — one callback per tab
# --------------------------------------------------------------------------

def _loading_state():
    return dmc.Center(dmc.Loader(size="sm", color=PRIMARY), h=120)


def _render_list(rows, scope, sort_key, q, *, fields, builder,
                 impact_field, recent_field, alpha_field):
    if rows is None:
        return _loading_state(), "Loading…"
    rows = _filter_unreviewed(rows, scope)
    if q:
        rows = [r for r in rows if _search_match(r, q, fields)]
    rows = _sort_rows(rows, sort_key, impact_field=impact_field,
                      recent_field=recent_field, alpha_field=alpha_field)
    if not rows:
        return _empty_state("Nothing here — inbox zero."), "0 items"
    # Cap visible rows for mobile responsiveness
    visible = rows[:300]
    cards = [builder(r) for r in visible]
    label = f"{len(rows):,} item" + ("s" if len(rows) != 1 else "")
    if len(rows) > len(visible):
        label += f" (showing {len(visible):,})"
    return cards, label


@callback(
    Output(_id("diag-list"), "children"),
    Output(_id("diag-count"), "children"),
    Input(_id("store-diag"), "data"),
    Input(_id("diag-scope"), "value"),
    Input(_id("diag-sort"), "value"),
    Input(_id("diag-search"), "value"),
)
def _render_diag(data, scope, sort_key, q):
    return _render_list(
        data, scope, sort_key, q,
        fields=("icd_code", "description", "category", "subcategory", "origin"),
        builder=_diag_card,
        impact_field="patients", recent_field=None, alpha_field="row_key",
    )


@callback(
    Output(_id("payor-list"), "children"),
    Output(_id("payor-count"), "children"),
    Input(_id("store-payor"), "data"),
    Input(_id("payor-scope"), "value"),
    Input(_id("payor-sort"), "value"),
    Input(_id("payor-search"), "value"),
)
def _render_payor(data, scope, sort_key, q):
    return _render_list(
        data, scope, sort_key, q,
        fields=("raw_name", "standardized_payor", "broad_category"),
        builder=_payor_card,
        impact_field="event_count", recent_field=None, alpha_field="raw_name",
    )


@callback(
    Output(_id("payor-entity-list"), "children"),
    Output(_id("payor-entity-count"), "children"),
    Input(_id("store-payor-entity"), "data"),
    Input(_id("payor-entity-scope"), "value"),
    Input(_id("payor-entity-search"), "value"),
)
def _render_payor_entities(data, scope, q):
    if data is None:
        return _loading_state(), "Loading…"
    rows = data
    if scope == "unreviewed":  # entities don't track reviewed; treat as no-op
        pass
    if q:
        rows = [r for r in rows if _search_match(r, q, ("name",))]
    rows = sorted(rows, key=lambda r: str(r.get("name") or "").lower())
    if not rows:
        return _empty_state("No payor entities yet."), "0 items"
    return [_payor_entity_card(r) for r in rows], f"{len(rows):,} entities"


@callback(
    Output(_id("provider-list"), "children"),
    Output(_id("provider-count"), "children"),
    Input(_id("store-provider"), "data"),
    Input(_id("provider-scope"), "value"),
    Input(_id("provider-sort"), "value"),
    Input(_id("provider-search"), "value"),
)
def _render_providers(data, scope, sort_key, q):
    return _render_list(
        data, scope, sort_key, q,
        fields=("name", "npi", "specialty", "institution", "full_address"),
        builder=_provider_card,
        impact_field="patient_count", recent_field="last_referral",
        alpha_field="name",
    )


@callback(
    Output(_id("institution-list"), "children"),
    Output(_id("institution-count"), "children"),
    Input(_id("store-institution"), "data"),
    Input(_id("institution-scope"), "value"),
    Input(_id("institution-search"), "value"),
)
def _render_institutions(data, scope, q):
    if data is None:
        return _loading_state(), "Loading…"
    rows = data
    if q:
        rows = [r for r in rows if _search_match(r, q, ("name",))]
    rows = sorted(rows, key=lambda r: str(r.get("name") or "").lower())
    if not rows:
        return _empty_state("No institutions yet."), "0 items"
    return [_institution_card(r) for r in rows], f"{len(rows):,} institutions"


# --------------------------------------------------------------------------
# Drawer open: card click → set edit context + render form for that row
# --------------------------------------------------------------------------

def _drawer_form_diag(row: dict):
    code = row.get("icd_code", "")
    cur_cat = row.get("category", "") or ""
    cur_sub = row.get("subcategory", "") or ""
    sub_options = SUBCATEGORIES.get(cur_cat, []) if cur_cat else []
    return dmc.Stack(gap="sm", children=[
        dmc.Text(row.get("description", "") or "", size="sm", c="dimmed"),
        dmc.Text(f"{int(row.get('patients') or 0):,} patients · source: {row.get('source') or 'csv'}",
                 size="xs", c="dimmed"),
        dmc.Select(
            id=_id("drawer-diag-cat"),
            label="Category",
            data=[{"value": "", "label": "— none —"}]
                 + [{"value": c, "label": c} for c in CATEGORIES]
                 + [{"value": "Unknown", "label": "Unknown"}],
            value=cur_cat,
            searchable=True, clearable=False, size="sm",
        ),
        dmc.Select(
            id=_id("drawer-diag-sub"),
            label="Subcategory",
            data=[{"value": "", "label": "— none —"}]
                 + [{"value": s, "label": s} for s in sub_options],
            value=cur_sub if cur_sub in sub_options else "",
            searchable=True, clearable=True, size="sm",
        ),
        dmc.Switch(
            id=_id("drawer-diag-reviewed"),
            label="Reviewed",
            checked=bool(row.get("reviewed")),
            color="green",
        ),
        dmc.Group(justify="flex-end", gap="xs", mt="sm", children=[
            dmc.Button("Cancel", id=_id("drawer-cancel"),
                       variant="subtle", color="gray", size="sm"),
            dmc.Button("Save", id=_id("drawer-save-diag"),
                       color="grape", size="sm",
                       leftSection=DashIconify(icon="tabler:check", width=14)),
        ]),
        dmc.Text(id=_id("drawer-diag-msg"), size="xs", c="dimmed"),
    ])


def _drawer_form_payor(row: dict):
    raw = row.get("raw_name", "")
    cur_std = row.get("standardized_payor", "") or ""
    cur_broad = row.get("broad_category", "") or ""
    cur_phdsc = row.get("phdsc_category", "") or "9"
    canonical = sorted({e["name"] for e in get_standardized_payor_counts() if e.get("name")})
    if cur_std and cur_std not in canonical:
        canonical = sorted(set(canonical + [cur_std]))
    return dmc.Stack(gap="sm", children=[
        dmc.Text(raw, size="sm", fw=600),
        dmc.Anchor(
            "🔍 Google search",
            href="https://www.google.com/search?q=" + raw.replace(" ", "+"),
            target="_blank", size="xs", c="dimmed",
        ),
        dmc.Text(f"{int(row.get('event_count') or 0):,} events", size="xs", c="dimmed"),
        dmc.Select(
            id=_id("drawer-payor-std"),
            label="Standardized payor",
            data=[{"value": "", "label": "— unmapped —"}]
                 + [{"value": n, "label": n} for n in canonical],
            value=cur_std,
            searchable=True, clearable=True, size="sm",
        ),
        dmc.Select(
            id=_id("drawer-payor-broad"),
            label="Broad category",
            data=[{"value": c, "label": c} for c in BROAD_PAYOR_CATEGORIES],
            value=cur_broad if cur_broad in BROAD_PAYOR_CATEGORIES else "Other/Unknown",
            clearable=False, size="sm",
        ),
        dmc.Select(
            id=_id("drawer-payor-phdsc"),
            label="PHDSC category",
            data=[{"value": c, "label": c} for c in PHDSC_CATEGORIES],
            value=cur_phdsc if cur_phdsc in PHDSC_CATEGORIES else "9 - Other",
            clearable=False, size="sm",
        ),
        dmc.Switch(
            id=_id("drawer-payor-reviewed"),
            label="Reviewed",
            checked=bool(row.get("reviewed")),
            color="green",
        ),
        dmc.Group(justify="flex-end", gap="xs", mt="sm", children=[
            dmc.Button("Cancel", id=_id("drawer-cancel"),
                       variant="subtle", color="gray", size="sm"),
            dmc.Button("Save", id=_id("drawer-save-payor"),
                       color="grape", size="sm",
                       leftSection=DashIconify(icon="tabler:check", width=14)),
        ]),
        dmc.Text(id=_id("drawer-payor-msg"), size="xs", c="dimmed"),
    ])


def _drawer_form_payor_entity(row: dict):
    name = row.get("name", "")
    cnt = int(row.get("mapping_count") or 0)
    return dmc.Stack(gap="sm", children=[
        dmc.Text(f"Used by {cnt} mapping" + ("s" if cnt != 1 else ""),
                 size="xs", c="dimmed"),
        dmc.TextInput(
            id=_id("drawer-pe-name"),
            label="Rename to",
            value=name, size="sm",
        ),
        dmc.Alert(
            "Renaming updates every mapping that points at this payor.",
            color="yellow", variant="light", icon=DashIconify(icon="tabler:info-circle"),
        ),
        dmc.Group(justify="space-between", mt="sm", children=[
            dmc.Button(
                "Delete", id=_id("drawer-delete-pe"),
                color="red", variant="light", size="sm",
                leftSection=DashIconify(icon="tabler:trash", width=14),
                disabled=cnt > 0,
            ),
            dmc.Group(gap="xs", children=[
                dmc.Button("Cancel", id=_id("drawer-cancel"),
                           variant="subtle", color="gray", size="sm"),
                dmc.Button("Save", id=_id("drawer-save-pe"),
                           color="grape", size="sm"),
            ]),
        ]),
        dmc.Text(id=_id("drawer-pe-msg"), size="xs", c="dimmed"),
    ])


def _drawer_form_provider(row: dict):
    name = row.get("name", "")
    npi = row.get("npi", "")
    cur_spec = row.get("specialty", "") or ""
    cur_inst = row.get("institution", "") or ""
    cur_addr_full = row.get("full_address", "") or ""
    inst_options = sorted(get_all_institutions())
    if cur_inst and cur_inst not in inst_options:
        inst_options = sorted(set(inst_options + [cur_inst]))
    return dmc.Stack(gap="sm", children=[
        dmc.Group(gap=6, children=[
            dmc.Text(name, size="sm", fw=600),
        ]),
        dmc.Group(gap=8, children=[
            (dmc.Anchor(f"NPPES {npi}",
                        href=f"https://npiregistry.cms.hhs.gov/provider-view/{npi}",
                        target="_blank", size="xs", c="dimmed")
             if npi else dmc.Text("(no NPI)", size="xs", c="dimmed")),
            (dmc.Anchor("📍 Maps",
                        href="https://www.google.com/search?q=" + cur_addr_full.replace(" ", "+"),
                        target="_blank", size="xs", c="dimmed")
             if cur_addr_full else None),
        ]),
        dmc.Select(
            id=_id("drawer-prov-spec"),
            label="Specialty",
            data=[{"value": "", "label": "— none —"}]
                 + [{"value": s, "label": s} for s in ABMS_SPECIALTIES],
            value=cur_spec if cur_spec in ABMS_SPECIALTIES else "",
            searchable=True, clearable=True, size="sm",
        ),
        dmc.Select(
            id=_id("drawer-prov-inst"),
            label="Institution",
            data=[{"value": "", "label": "— none —"}]
                 + [{"value": n, "label": n} for n in inst_options],
            value=cur_inst,
            searchable=True, clearable=True, size="sm",
        ),
        dmc.Group(justify="space-between", align="flex-end", gap=6, children=[
            dmc.Text("Address", size="xs", fw=500, c="dimmed"),
            dmc.Button(
                "Use NPPES address",
                id=_id("drawer-prov-nppes-btn"),
                leftSection=DashIconify(icon="tabler:map-pin", width=12),
                variant="subtle", color="grape", size="compact-xs",
                disabled=not (npi or "").strip(),
            ),
        ]),
        dmc.Text(id=_id("drawer-prov-nppes-msg"), size="xs", c="dimmed"),
        dmc.Select(
            id=_id("drawer-prov-copy-addr"),
            placeholder="Copy address from another provider…",
            data=[],
            value=None,
            searchable=True, clearable=True, size="xs",
            leftSection=DashIconify(icon="tabler:copy", width=12),
        ),
        dmc.Textarea(
            id=_id("drawer-prov-paste"),
            placeholder="…or paste a full address (e.g. 123 Main St, Seattle, WA 98101) — auto-splits",
            autosize=True, minRows=1, maxRows=2,
            size="xs",
        ),
        dmc.TextInput(
            id=_id("drawer-prov-addr"),
            label="Street address",
            value=row.get("address", "") or "",
            size="sm",
        ),
        dmc.Group(gap=6, grow=True, children=[
            dmc.TextInput(id=_id("drawer-prov-city"), label="City",
                          value=row.get("city", "") or "", size="sm"),
            dmc.TextInput(id=_id("drawer-prov-state"), label="State",
                          value=row.get("state", "") or "", size="sm"),
            dmc.TextInput(id=_id("drawer-prov-zip"), label="ZIP",
                          value=row.get("zip", "") or "", size="sm"),
        ]),
        dmc.Switch(
            id=_id("drawer-prov-reviewed"),
            label="Reviewed",
            checked=bool(row.get("reviewed")),
            color="green",
        ),
        dmc.Group(justify="flex-end", gap="xs", mt="sm", children=[
            dmc.Button("Cancel", id=_id("drawer-cancel"),
                       variant="subtle", color="gray", size="sm"),
            dmc.Button("Save", id=_id("drawer-save-prov"),
                       color="grape", size="sm",
                       leftSection=DashIconify(icon="tabler:check", width=14)),
        ]),
        dmc.Text(id=_id("drawer-prov-msg"), size="xs", c="dimmed"),
    ])


def _drawer_form_institution(row: dict):
    name = row.get("name", "")
    cnt = int(row.get("mapping_count") or 0)
    return dmc.Stack(gap="sm", children=[
        dmc.Text(f"{cnt} provider" + ("s" if cnt != 1 else "") + " linked",
                 size="xs", c="dimmed"),
        dmc.TextInput(
            id=_id("drawer-inst-name"),
            label="Rename to",
            value=name, size="sm",
        ),
        dmc.Alert(
            "Renaming updates every provider currently linked.",
            color="yellow", variant="light", icon=DashIconify(icon="tabler:info-circle"),
        ),
        dmc.Group(justify="space-between", mt="sm", children=[
            dmc.Button(
                "Delete", id=_id("drawer-delete-inst"),
                color="red", variant="light", size="sm",
                leftSection=DashIconify(icon="tabler:trash", width=14),
                disabled=cnt > 0,
            ),
            dmc.Group(gap="xs", children=[
                dmc.Button("Cancel", id=_id("drawer-cancel"),
                           variant="subtle", color="gray", size="sm"),
                dmc.Button("Save", id=_id("drawer-save-inst"),
                           color="grape", size="sm"),
            ]),
        ]),
        dmc.Text(id=_id("drawer-inst-msg"), size="xs", c="dimmed"),
    ])


def _find_row(rows: list[dict], key: str, key_field: str) -> dict | None:
    for r in rows or []:
        if str(r.get(key_field) or "") == str(key):
            return r
    return None


# Clientside: open drawer instantly on any card tap (no server round-trip).
# The body is then filled in by the per-tab server callbacks below.
clientside_callback(
    """
    function(nClicksList) {
        var ctx = window.dash_clientside.callback_context;
        if (!ctx || !ctx.triggered || !ctx.triggered.length) {
            return [window.dash_clientside.no_update,
                    window.dash_clientside.no_update,
                    window.dash_clientside.no_update];
        }
        var trig = ctx.triggered[0];
        if (!trig.value) {
            return [window.dash_clientside.no_update,
                    window.dash_clientside.no_update,
                    window.dash_clientside.no_update];
        }
        // Parse pattern-matched id to get a friendly title hint.
        var id;
        try { id = JSON.parse(trig.prop_id.split('.')[0]); } catch (e) { id = {}; }
        var hint = '';
        if (id && id.tab) {
            hint = ({diag: 'Diagnosis', payor: 'Payor mapping',
                     'payor-entity': 'Payor', provider: 'Provider',
                     institution: 'Institution'}[id.tab]) || '';
        }
        if (id && id.key && id.tab !== 'payor') hint += ' · ' + id.key;
        // Empty body so dcc.Loading shows its spinner during server fill.
        return [true, hint || 'Loading…', ''];
    }
    """,
    Output(_id("drawer"), "opened", allow_duplicate=True),
    Output(_id("drawer-title"), "children", allow_duplicate=True),
    Output(_id("drawer-body"), "children", allow_duplicate=True),
    Input({"type": _id("card"), "tab": ALL, "key": ALL}, "n_clicks"),
    prevent_initial_call=True,
)


def _click_value():
    """Return the n_clicks value of the currently triggered pattern-matched input,
    or 0 if not a real click."""
    if not ctx.triggered:
        return 0
    return ctx.triggered[0].get("value") or 0


@callback(
    Output(_id("drawer-title"), "children", allow_duplicate=True),
    Output(_id("drawer-body"), "children", allow_duplicate=True),
    Output(_id("edit-store"), "data", allow_duplicate=True),
    Input({"type": _id("card"), "tab": "diag", "key": ALL}, "n_clicks"),
    State(_id("store-diag"), "data"),
    prevent_initial_call=True,
)
def _open_diag(_n, rows):
    if not _click_value():
        return no_update, no_update, no_update
    key = ctx.triggered_id.get("key") if isinstance(ctx.triggered_id, dict) else None
    row = _find_row(rows, key, "row_key")
    if not row:
        return no_update, no_update, no_update
    code = row.get("icd_code") or ""
    desc = row.get("description") or ""
    title_label = code if code else (desc[:40] + ("…" if len(desc) > 40 else ""))
    return (f"Diagnosis · {title_label}",
            _drawer_form_diag(row),
            {"tab": "diag", "key": key})


@callback(
    Output(_id("drawer-title"), "children", allow_duplicate=True),
    Output(_id("drawer-body"), "children", allow_duplicate=True),
    Output(_id("edit-store"), "data", allow_duplicate=True),
    Input({"type": _id("card"), "tab": "payor", "key": ALL}, "n_clicks"),
    State(_id("store-payor"), "data"),
    prevent_initial_call=True,
)
def _open_payor(_n, rows):
    if not _click_value():
        return no_update, no_update, no_update
    key = ctx.triggered_id.get("key") if isinstance(ctx.triggered_id, dict) else None
    row = _find_row(rows, key, "raw_name")
    if not row:
        return no_update, no_update, no_update
    return "Payor mapping", _drawer_form_payor(row), {"tab": "payor", "key": key}


@callback(
    Output(_id("drawer-title"), "children", allow_duplicate=True),
    Output(_id("drawer-body"), "children", allow_duplicate=True),
    Output(_id("edit-store"), "data", allow_duplicate=True),
    Input({"type": _id("card"), "tab": "payor-entity", "key": ALL}, "n_clicks"),
    State(_id("store-payor-entity"), "data"),
    prevent_initial_call=True,
)
def _open_payor_entity(_n, rows):
    if not _click_value():
        return no_update, no_update, no_update
    key = ctx.triggered_id.get("key") if isinstance(ctx.triggered_id, dict) else None
    row = _find_row(rows, key, "name") or {"name": key, "mapping_count": 0}
    return f"Payor · {key}", _drawer_form_payor_entity(row), {"tab": "payor-entity", "key": key}


@callback(
    Output(_id("drawer-title"), "children", allow_duplicate=True),
    Output(_id("drawer-body"), "children", allow_duplicate=True),
    Output(_id("edit-store"), "data", allow_duplicate=True),
    Input({"type": _id("card"), "tab": "provider", "key": ALL}, "n_clicks"),
    State(_id("store-provider"), "data"),
    prevent_initial_call=True,
)
def _open_provider(_n, rows):
    if not _click_value():
        return no_update, no_update, no_update
    key = ctx.triggered_id.get("key") if isinstance(ctx.triggered_id, dict) else None
    row = _find_row(rows, key, "row_key")
    if not row:
        return no_update, no_update, no_update
    return row.get("name") or "Provider", _drawer_form_provider(row), {"tab": "provider", "key": key}


@callback(
    Output(_id("drawer-title"), "children", allow_duplicate=True),
    Output(_id("drawer-body"), "children", allow_duplicate=True),
    Output(_id("edit-store"), "data", allow_duplicate=True),
    Input({"type": _id("card"), "tab": "institution", "key": ALL}, "n_clicks"),
    State(_id("store-institution"), "data"),
    prevent_initial_call=True,
)
def _open_institution(_n, rows):
    if not _click_value():
        return no_update, no_update, no_update
    key = ctx.triggered_id.get("key") if isinstance(ctx.triggered_id, dict) else None
    row = _find_row(rows, key, "name") or {"name": key, "mapping_count": 0}
    return f"Institution · {key}", _drawer_form_institution(row), {"tab": "institution", "key": key}


@callback(
    Output(_id("drawer"), "opened", allow_duplicate=True),
    Input(_id("drawer-cancel"), "n_clicks"),
    prevent_initial_call=True,
)
def _close_drawer(n):
    if not n:
        return no_update
    return False


# Clientside: close drawer the instant any Save / Delete button is tapped.
# The matching server callback still runs in the background to persist the
# change and refresh the store; the user just doesn't have to wait for it.
clientside_callback(
    """
    function(d, p, pe, prov, inst, dpe, dinst) {
        var ctx = window.dash_clientside.callback_context;
        if (!ctx || !ctx.triggered || !ctx.triggered.length) {
            return window.dash_clientside.no_update;
        }
        if (!ctx.triggered[0].value) {
            return window.dash_clientside.no_update;
        }
        return false;
    }
    """,
    Output(_id("drawer"), "opened", allow_duplicate=True),
    Input(_id("drawer-save-diag"), "n_clicks"),
    Input(_id("drawer-save-payor"), "n_clicks"),
    Input(_id("drawer-save-pe"), "n_clicks"),
    Input(_id("drawer-save-prov"), "n_clicks"),
    Input(_id("drawer-save-inst"), "n_clicks"),
    Input(_id("drawer-delete-pe"), "n_clicks"),
    Input(_id("drawer-delete-inst"), "n_clicks"),
    prevent_initial_call=True,
)


# Keep diagnosis subcategory options in sync with selected category
@callback(
    Output(_id("drawer-diag-sub"), "data"),
    Output(_id("drawer-diag-sub"), "value"),
    Input(_id("drawer-diag-cat"), "value"),
    State(_id("drawer-diag-sub"), "value"),
    prevent_initial_call=True,
)
def _sync_diag_sub(cat, current):
    options = SUBCATEGORIES.get(cat or "", [])
    data = [{"value": "", "label": "— none —"}] + [{"value": s, "label": s} for s in options]
    new_val = current if current in options else ""
    return data, new_val


# --------------------------------------------------------------------------
# Save handlers — one per row type
# --------------------------------------------------------------------------

@callback(
    Output(_id("store-diag"), "data", allow_duplicate=True),
    Output(_id("drawer"), "opened", allow_duplicate=True),
    Output(_id("drawer-diag-msg"), "children"),
    Input(_id("drawer-save-diag"), "n_clicks"),
    State(_id("edit-store"), "data"),
    State(_id("store-diag"), "data"),
    State(_id("drawer-diag-cat"), "value"),
    State(_id("drawer-diag-sub"), "value"),
    State(_id("drawer-diag-reviewed"), "checked"),
    prevent_initial_call=True,
)
def _save_diag(n, edit, rows, cat, sub, reviewed):
    if not n or not edit or edit.get("tab") != "diag":
        return no_update, no_update, no_update
    if not is_admin():
        return no_update, no_update, "Not authorized."
    row_key = edit.get("key") or ""
    # Find the source row so we know whether to upsert by ICD code or by
    # description (free-text entries from the review queue have no code).
    source_row = _find_row(rows, row_key, "row_key") or {}
    code = source_row.get("icd_code") or ""
    desc = source_row.get("description") or ""
    override_key = code if code else desc
    if not override_key:
        return no_update, no_update, "Missing key."
    try:
        upsert_diagnosis_override(override_key, category=cat or "",
                                  subcategory=sub or "", source="manual")
        set_diagnosis_reviewed_bulk([override_key], reviewed=bool(reviewed))
    except Exception as e:
        return no_update, no_update, f"Save failed: {e}"
    new_rows = []
    for r in rows or []:
        if r.get("row_key") == row_key:
            r = {**r, "category": cat or "", "subcategory": sub or "",
                 "reviewed": bool(reviewed), "source": "manual"}
        new_rows.append(r)
    return new_rows, False, ""


@callback(
    Output(_id("store-payor"), "data", allow_duplicate=True),
    Output(_id("store-payor-entity"), "data", allow_duplicate=True),
    Output(_id("drawer"), "opened", allow_duplicate=True),
    Output(_id("drawer-payor-msg"), "children"),
    Input(_id("drawer-save-payor"), "n_clicks"),
    State(_id("edit-store"), "data"),
    State(_id("store-payor"), "data"),
    State(_id("drawer-payor-std"), "value"),
    State(_id("drawer-payor-broad"), "value"),
    State(_id("drawer-payor-phdsc"), "value"),
    State(_id("drawer-payor-reviewed"), "checked"),
    prevent_initial_call=True,
)
def _save_payor(n, edit, rows, std, broad, phdsc, reviewed):
    if not n or not edit or edit.get("tab") != "payor":
        return no_update, no_update, no_update, no_update
    if not is_admin():
        return no_update, no_update, no_update, "Not authorized."
    raw = edit.get("key")
    try:
        upsert_payor_mapping(
            raw, standardized_payor=std or "",
            broad_category=broad or "Other/Unknown",
            phdsc_category=phdsc or "9 - Other",
            reviewed=bool(reviewed),
        )
    except Exception as e:
        return no_update, no_update, no_update, f"Save failed: {e}"
    new_rows = []
    for r in rows or []:
        if r.get("raw_name") == raw:
            r = {**r, "standardized_payor": std or "",
                 "broad_category": broad or "Other/Unknown",
                 "phdsc_category": phdsc or "9 - Other",
                 "reviewed": bool(reviewed)}
        new_rows.append(r)
    try:
        new_entities = _load_payor_entities()
    except Exception:
        new_entities = no_update
    return new_rows, new_entities, False, ""


@callback(
    Output(_id("store-payor-entity"), "data", allow_duplicate=True),
    Output(_id("store-payor"), "data", allow_duplicate=True),
    Output(_id("drawer"), "opened", allow_duplicate=True),
    Output(_id("drawer-pe-msg"), "children"),
    Input(_id("drawer-save-pe"), "n_clicks"),
    Input(_id("drawer-delete-pe"), "n_clicks"),
    State(_id("edit-store"), "data"),
    State(_id("drawer-pe-name"), "value"),
    prevent_initial_call=True,
)
def _save_payor_entity(n_save, n_del, edit, new_name):
    if not edit or edit.get("tab") != "payor-entity":
        return no_update, no_update, no_update, no_update
    if not is_admin():
        return no_update, no_update, no_update, "Not authorized."
    trig = ctx.triggered_id
    old_name = edit.get("key")

    try:
        if trig == _id("drawer-delete-pe") and n_del:
            delete_standardized_payor(old_name)
        elif trig == _id("drawer-save-pe") and n_save:
            new_name = (new_name or "").strip()
            if not new_name:
                return no_update, no_update, no_update, "Name required."
            if new_name != old_name:
                rename_standardized_payor(old_name, new_name)
        else:
            return no_update, no_update, no_update, no_update
    except Exception as e:
        return no_update, no_update, no_update, f"Failed: {e}"

    return _load_payor_entities(), _load_payor_rows(), False, ""


@callback(
    Output(_id("store-payor-entity"), "data", allow_duplicate=True),
    Output(_id("payor-entity-add-name"), "value"),
    Output(_id("payor-entity-add-msg"), "children"),
    Input(_id("payor-entity-add-btn"), "n_clicks"),
    State(_id("payor-entity-add-name"), "value"),
    prevent_initial_call=True,
)
def _add_payor_entity(n, name):
    if not n:
        return no_update, no_update, no_update
    if not is_admin():
        return no_update, no_update, "Not authorized."
    name = (name or "").strip()
    if not name:
        return no_update, no_update, "Enter a name first."
    try:
        # Match desktop behavior: register the new entity in the rates table
        # so it appears in dropdowns and persists even before any mapping
        # points at it.
        existing = {r["payor"] for r in get_all_insurance_rates()}
        if name not in existing:
            upsert_insurance_rate(payor=name, pct_medicare=100.0, source="manual")
    except Exception as e:
        return no_update, no_update, f"Failed: {e}"
    return _load_payor_entities(), "", f"Added {name}."


@callback(
    Output(_id("store-provider"), "data", allow_duplicate=True),
    Output(_id("store-institution"), "data", allow_duplicate=True),
    Output(_id("drawer"), "opened", allow_duplicate=True),
    Output(_id("drawer-prov-msg"), "children"),
    Input(_id("drawer-save-prov"), "n_clicks"),
    State(_id("edit-store"), "data"),
    State(_id("store-provider"), "data"),
    State(_id("drawer-prov-spec"), "value"),
    State(_id("drawer-prov-inst"), "value"),
    State(_id("drawer-prov-addr"), "value"),
    State(_id("drawer-prov-city"), "value"),
    State(_id("drawer-prov-state"), "value"),
    State(_id("drawer-prov-zip"), "value"),
    State(_id("drawer-prov-reviewed"), "checked"),
    prevent_initial_call=True,
)
def _save_provider(n, edit, rows, spec, inst, addr, city, state_, zip_, reviewed):
    if not n or not edit or edit.get("tab") != "provider":
        return no_update, no_update, no_update, no_update
    if not is_admin():
        return no_update, no_update, no_update, "Not authorized."
    row_key = edit.get("key", "")
    npi, _, addr_key = row_key.partition("|")
    spec_norm = normalize_specialty(spec or "")
    full_addr = ", ".join(p for p in [addr or "", city or "", state_ or "", zip_ or ""] if p)
    addr_changed_manually = bool((addr or "").strip() or (city or "").strip()
                                 or (state_ or "").strip() or (zip_ or "").strip())
    try:
        upsert_referring(
            npi=npi, address_key=addr_key,
            specialty=spec_norm or None,
            institution=(inst or None),
            address=(addr or None),
            city=(city or None),
            state=(state_ or None),
            zip_code=(zip_ or None),
            address_source=("manual" if addr_changed_manually else None),
            source="manual",
        )
        set_reviewed_bulk([(npi, addr_key)], reviewed=bool(reviewed))
    except Exception as e:
        return no_update, no_update, no_update, f"Save failed: {e}"

    new_rows = []
    for r in rows or []:
        if r.get("row_key") == row_key:
            r = {**r,
                 "specialty": spec_norm or "",
                 "institution": inst or "",
                 "address": addr or "",
                 "city": city or "",
                 "state": state_ or "",
                 "zip": zip_ or "",
                 "full_address": full_addr,
                 "address_source": "manual" if addr_changed_manually else r.get("address_source", ""),
                 "reviewed": bool(reviewed),
                 "source": "manual"}
        new_rows.append(r)

    try:
        new_inst = _load_institutions()
    except Exception:
        new_inst = no_update
    return new_rows, new_inst, False, ""


@callback(
    Output(_id("drawer-prov-copy-addr"), "data"),
    Input(_id("edit-store"), "data"),
    State(_id("store-provider"), "data"),
    prevent_initial_call=True,
)
def _populate_copy_address_options(edit, providers):
    """Build the copy-from-existing dropdown when the provider drawer opens.

    Ranks options: same NPI first (other addresses on file for this provider),
    then same institution, then everything else with a usable address. Limits
    to 200 to keep the Select responsive.
    """
    if not edit or edit.get("tab") != "provider" or not providers:
        return []
    cur_key = edit.get("key", "") or ""
    cur_npi = cur_key.partition("|")[0].strip()
    cur_inst = ""
    for r in providers:
        if r.get("row_key") == cur_key:
            cur_inst = (r.get("institution") or "").strip()
            break

    same_npi, same_inst, other = [], [], []
    for r in providers:
        rk = r.get("row_key") or ""
        if rk == cur_key:
            continue
        if not (r.get("address") or r.get("city") or r.get("state") or r.get("zip")):
            continue
        full = r.get("full_address") or ""
        name = r.get("name") or "(unknown)"
        label = f"{name} — {full}" if full else name
        opt = {"value": rk, "label": label[:120]}
        rnpi = (r.get("npi") or "").strip()
        rinst = (r.get("institution") or "").strip()
        if cur_npi and rnpi == cur_npi:
            same_npi.append(opt)
        elif cur_inst and rinst == cur_inst:
            same_inst.append(opt)
        else:
            other.append(opt)
    # Truncate to keep payload + Select snappy
    return (same_npi + same_inst + other)[:200]


# Clientside: fill the four address fields when an option is picked.
clientside_callback(
    """
    function(rowKey, providers) {
        const NU = window.dash_clientside.no_update;
        if (!rowKey || !providers) return [NU, NU, NU, NU];
        const target = providers.find(p => (p.row_key || '') === rowKey);
        if (!target) return [NU, NU, NU, NU];
        return [
            target.address || '',
            target.city || '',
            target.state || '',
            target.zip || '',
        ];
    }
    """,
    Output(_id("drawer-prov-addr"), "value", allow_duplicate=True),
    Output(_id("drawer-prov-city"), "value", allow_duplicate=True),
    Output(_id("drawer-prov-state"), "value", allow_duplicate=True),
    Output(_id("drawer-prov-zip"), "value", allow_duplicate=True),
    Input(_id("drawer-prov-copy-addr"), "value"),
    State(_id("store-provider"), "data"),
    prevent_initial_call=True,
)


# Clientside: parse a pasted full address into the four fields.
# Handles "123 Main St, Seattle, WA 98101" and common variants.
clientside_callback(
    r"""
    function(text) {
        const NU = window.dash_clientside.no_update;
        if (!text || !text.trim()) return [NU, NU, NU, NU];
        const STATES = new Set([
            'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL',
            'IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT',
            'NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI',
            'SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','DC',
        ]);
        // Collapse whitespace, strip USA suffix, strip trailing commas.
        let s = text.replace(/\s+/g, ' ').trim();
        s = s.replace(/,?\s*(USA|U\.S\.A\.|United States)\s*$/i, '').trim();

        // ZIP at end, optional +4
        let zip = '';
        const zipMatch = s.match(/(\d{5})(?:-\d{4})?\s*$/);
        if (zipMatch) {
            zip = zipMatch[1];
            s = s.slice(0, zipMatch.index).trim().replace(/[,\s]+$/, '').trim();
        }

        // State at end (2-letter, validated). Allow comma or space separator.
        let state = '';
        const stMatch = s.match(/[,\s]+([A-Za-z]{2})\s*$/);
        if (stMatch && STATES.has(stMatch[1].toUpperCase())) {
            state = stMatch[1].toUpperCase();
            s = s.slice(0, stMatch.index).trim().replace(/[,\s]+$/, '').trim();
        }

        // Remaining: "street, city" or just "street". Split on commas;
        // last segment is city, everything before is street.
        const parts = s.split(',').map(x => x.trim()).filter(Boolean);
        let street = '', city = '';
        if (parts.length >= 2) {
            city = parts.pop();
            street = parts.join(', ');
        } else if (parts.length === 1) {
            // No comma — best effort: leave as street, no city
            street = parts[0];
        }
        return [street, city, state, zip];
    }
    """,
    Output(_id("drawer-prov-addr"), "value", allow_duplicate=True),
    Output(_id("drawer-prov-city"), "value", allow_duplicate=True),
    Output(_id("drawer-prov-state"), "value", allow_duplicate=True),
    Output(_id("drawer-prov-zip"), "value", allow_duplicate=True),
    Input(_id("drawer-prov-paste"), "value"),
    prevent_initial_call=True,
)


@callback(
    Output(_id("drawer-prov-addr"), "value", allow_duplicate=True),
    Output(_id("drawer-prov-city"), "value", allow_duplicate=True),
    Output(_id("drawer-prov-state"), "value", allow_duplicate=True),
    Output(_id("drawer-prov-zip"), "value", allow_duplicate=True),
    Output(_id("drawer-prov-nppes-msg"), "children"),
    Input(_id("drawer-prov-nppes-btn"), "n_clicks"),
    State(_id("edit-store"), "data"),
    prevent_initial_call=True,
)
def _fetch_nppes_address(n, edit):
    """Pull the practice-location address from NPPES into the four fields."""
    if not n or not edit or edit.get("tab") != "provider":
        return (no_update,) * 5
    npi = (edit.get("key") or "").partition("|")[0].strip()
    if not npi:
        return no_update, no_update, no_update, no_update, "No NPI on this row."
    try:
        from utils.npi_lookup import lookup_npi
        info = lookup_npi(npi)
    except Exception as e:
        return no_update, no_update, no_update, no_update, f"NPPES error: {e}"
    if not info:
        return no_update, no_update, no_update, no_update, "NPI not found in NPPES."
    addr = info.get("address") or ""
    city = info.get("city") or ""
    state_ = info.get("state") or ""
    zip_ = info.get("zip_code") or ""
    if not (addr or city or state_ or zip_):
        return no_update, no_update, no_update, no_update, "NPPES returned no address."
    return addr, city, state_, zip_, "Filled from NPPES — review and Save."


@callback(
    Output(_id("store-institution"), "data", allow_duplicate=True),
    Output(_id("store-provider"), "data", allow_duplicate=True),
    Output(_id("drawer"), "opened", allow_duplicate=True),
    Output(_id("drawer-inst-msg"), "children"),
    Input(_id("drawer-save-inst"), "n_clicks"),
    Input(_id("drawer-delete-inst"), "n_clicks"),
    State(_id("edit-store"), "data"),
    State(_id("drawer-inst-name"), "value"),
    prevent_initial_call=True,
)
def _save_institution(n_save, n_del, edit, new_name):
    if not edit or edit.get("tab") != "institution":
        return no_update, no_update, no_update, no_update
    if not is_admin():
        return no_update, no_update, no_update, "Not authorized."
    trig = ctx.triggered_id
    old_name = edit.get("key")

    try:
        if trig == _id("drawer-delete-inst") and n_del:
            delete_institution(old_name)
        elif trig == _id("drawer-save-inst") and n_save:
            new_name = (new_name or "").strip()
            if not new_name:
                return no_update, no_update, no_update, "Name required."
            if new_name != old_name:
                rename_institution(old_name, new_name)
        else:
            return no_update, no_update, no_update, no_update
    except Exception as e:
        return no_update, no_update, no_update, f"Failed: {e}"

    return _load_institutions(), _load_provider_rows(), False, ""


@callback(
    Output(_id("store-institution"), "data", allow_duplicate=True),
    Output(_id("institution-add-name"), "value"),
    Output(_id("institution-add-msg"), "children"),
    Input(_id("institution-add-btn"), "n_clicks"),
    State(_id("institution-add-name"), "value"),
    prevent_initial_call=True,
)
def _add_institution(n, name):
    if not n:
        return no_update, no_update, no_update
    if not is_admin():
        return no_update, no_update, "Not authorized."
    name = (name or "").strip()
    if not name:
        return no_update, no_update, "Enter a name first."
    try:
        add_institution(name)
    except Exception as e:
        return no_update, no_update, f"Failed: {e}"
    return _load_institutions(), "", f"Added {name}."
