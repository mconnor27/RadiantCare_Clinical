"""CPT code categories and subcategories for billing page filters.

Organizes CPT/HCPCS codes into clinical categories and subcategories
aligned with radiation oncology billing workflows.

Public API
----------
- ``CPT_CATEGORIES``       – {category: {code, ...}} flat set per category
- ``CPT_SUBCATEGORIES``    – {category: {subcategory: [code, ...]}} nested
- ``CPT_DESCRIPTIONS``     – {code: short description} from RVU lookup
- ``CODE_TO_CATEGORY``     – {code: category} reverse lookup
- ``CODE_TO_SUBCATEGORY``  – {code: subcategory} reverse lookup
- ``CATEGORY_NAMES``       – sorted list of category display names + "Other"
- ``CATEGORY_SLUGS``       – {category: slug} for CSS/ID generation
- ``SLUG_TO_CATEGORY``     – reverse of CATEGORY_SLUGS
- ``CATEGORY_COLORS``      – {category: hex color}
- ``codes_for_categories`` – return set of codes for given category names
- ``codes_for_subcategory``– return list of codes for a category+subcategory
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Category → Subcategory → Codes
# ---------------------------------------------------------------------------

CPT_SUBCATEGORIES: dict[str, dict[str, list[str]]] = {
    "E&M": {
        "New Patient": ["99202", "99203", "99204", "99205"],
        "Established Patient": ["99211", "99212", "99213", "99214", "99215"],
        "Inpatient": [
            "99221", "99222", "99223", "99231", "99232",
            "99251", "99252", "99253", "99254", "99255",
            "99261", "99262", "99263",
        ],
        "Office Consultation": ["99241", "99242", "99243", "99244", "99245"],
        "Telehealth": [
            "98003", "98004", "98006", "98007", "98015",
            "99441", "99442", "99443",
        ],
        "Prolonged Services": ["99354", "99355", "99356", "99357", "99417"],
        "Add-on": [
            "G2211", "G2212",
            "99406", "99407", "G0436", "G0437",
            "99459",
        ],
        "Legacy/Other": [
            "99271", "99272", "99273", "99274", "99275",
            "99499",
        ],
    },
    "Simulation": {
        "Simple": ["77280"],
        "Intermediate": ["77285"],
        "Complex": ["77290"],
        "Respiratory Motion": ["77293"],
        "CT Localization": ["77011", "76370"],
    },
    "Treatment Planning": {
        "Clinical Planning": ["77261", "77263"],
        "Dosimetry": ["77295", "77300", "77301"],
        "Teletherapy Isodose": ["77305", "77306", "77307", "77310", "77315"],
        "Brachytherapy Isodose": ["77316", "77318"],
        "Special Plans": ["77320", "77321", "77328"],
    },
    "Physics & Devices": {
        "Dosimetry": ["77331"],
        "Treatment Devices": ["77332", "77333", "77334"],
        "Physics Consult": ["77336", "77370"],
        "MLC/IMRT Design": ["77338"],
        "Special Treatment": ["77470"],
        "Unlisted": ["77399"],
    },
    "Treatment Delivery": {
        "Standard Delivery": [
            "77402", "77407", "77412",
            "77403", "77404", "77408", "77409",
            "77413", "77414",
        ],
        "IMRT (thru 2025)": ["77385", "77386", "77418"],
        "SRS/SBRT": ["77372", "77373"],
        "Port Films": ["77416", "77417"],
        "Hospital G-codes (thru 2025)": [
            "G6002", "G6004", "G6005", "G6006", "G6009",
            "G6012", "G6013", "G6014", "G6015",
        ],
    },
    "Image Guidance": {
        "IGRT": ["77387"],
        "CT Guidance": ["77014"],
        "Motion Tracking": ["G6017", "0197T"],
        "Other Guidance": ["77421"],
    },
    "Treatment Management": {
        "Weekly Management": ["77427"],
        "Other Management": ["77431", "77432", "77435"],
    },
    "Brachytherapy": {
        "Interstitial": ["77778"],
        "Handling": ["77790"],
        "Ultrasound Guidance": ["76965"],
    },
    "Procedures": {
        "Prostate": ["55874", "55875", "55876"],
        "Ultrasound": ["76873", "76942"],
        "Supplies": ["A4646", "A4648"],
    },
    "Drug Administration": {
        "Chemotherapy": ["96400", "J9217"],
        "Injection": ["90782"],
    },
    "Radiopharmaceutical": {
        "Nuclear Therapy": ["79101"],
    },
}

# ---------------------------------------------------------------------------
# Flat category sets (derived from subcategories)
# ---------------------------------------------------------------------------

CPT_CATEGORIES: dict[str, set[str]] = {}
for _cat, _subs in CPT_SUBCATEGORIES.items():
    _all_codes: set[str] = set()
    for _codes in _subs.values():
        _all_codes.update(_codes)
    CPT_CATEGORIES[_cat] = _all_codes

# Reverse lookups
CODE_TO_CATEGORY: dict[str, str] = {}
for _cat, _codes in CPT_CATEGORIES.items():
    for _code in _codes:
        CODE_TO_CATEGORY[_code] = _cat

CODE_TO_SUBCATEGORY: dict[str, str] = {}
for _cat, _subs in CPT_SUBCATEGORIES.items():
    for _subcat, _codes in _subs.items():
        for _code in _codes:
            CODE_TO_SUBCATEGORY[_code] = _subcat

CATEGORY_NAMES: list[str] = list(CPT_SUBCATEGORIES.keys()) + ["Other"]

CATEGORY_SLUGS: dict[str, str] = {
    "E&M": "em", "Simulation": "simulation", "Treatment Planning": "planning",
    "Physics & Devices": "physics", "Treatment Delivery": "delivery",
    "Image Guidance": "igrt", "Treatment Management": "management",
    "Brachytherapy": "brachy", "Procedures": "procedures",
    "Drug Administration": "drugs", "Radiopharmaceutical": "radiopharm",
    "Other": "other",
}
SLUG_TO_CATEGORY: dict[str, str] = {v: k for k, v in CATEGORY_SLUGS.items()}

# ---------------------------------------------------------------------------
# CPT Descriptions (short labels from CMS PFS)
# ---------------------------------------------------------------------------

CPT_DESCRIPTIONS: dict[str, str] = {
    # E&M — New Patient
    "99202": "Office o/p new SF 15 min",
    "99203": "Office o/p new low 30 min",
    "99204": "Office o/p new mod 45 min",
    "99205": "Office o/p new high 60 min",
    # E&M — Established Patient
    "99211": "Off/op est may not req phy",
    "99212": "Office o/p est SF 10 min",
    "99213": "Office o/p est low 20 min",
    "99214": "Office o/p est mod 30 min",
    "99215": "Office o/p est high 40 min",
    # E&M — Inpatient
    "99221": "Initial hosp ip/obs SF/low 40",
    "99222": "Initial hosp ip/obs mod 55",
    "99223": "Initial hosp ip/obs high 75",
    "99231": "Subsequent hosp ip/obs SF/low 25",
    "99232": "Subsequent hosp ip/obs mod 35",
    # E&M — Office Consultation
    "99241": "Office consultation",
    "99242": "Off/op consult new/est SF 20",
    "99243": "Off/op consult new/est low 30",
    "99244": "Off/op consult new/est mod 40",
    "99245": "Off/op consult new/est high 55",
    # E&M — Inpatient (consultations)
    "99251": "Inpatient consultation",
    "99252": "Ip/obs consult new/est SF 35",
    "99253": "Ip/obs consult new/est low 45",
    "99254": "Ip/obs consult new/est mod 60",
    "99255": "Ip/obs consult new/est high 80",
    # E&M — Telehealth
    "98003": "Synch audio-video new high 60",
    "98004": "Synch audio-video est SF 10",
    "98006": "Synch audio-video est mod 30",
    "98007": "Synch audio-video est high 40",
    "98015": "Synch audio-only est high 40",
    "99441": "Phone E/M 5-10 min",
    "99442": "Phone E/M 11-20 min",
    "99443": "Phone E/M 21-30 min",
    # E&M — Prolonged Services
    "99354": "Prolonged svc o/p 1st hour",
    "99355": "Prolonged svc o/p ea addl 30",
    "99356": "Prolonged svc i/p 1st hour",
    "99357": "Prolonged svc i/p ea addl",
    "99417": "Prolonged o/p E/M ea 15 min",
    # E&M — Add-on
    "G2211": "Complex E/M visit add-on",
    "G2212": "Prolonged outpt/office visit",
    "99406": "Tobacco cessation 3-10 min",
    "99407": "Tobacco cessation > 10 min",
    "G0436": "Tobacco-use counsel 3-10 min",
    "G0437": "Tobacco-use counsel > 10 min",
    # E&M — Add-on (continued)
    "99459": "Pelvic examination",
    # E&M — Inpatient (legacy follow-up consults)
    "99261": "Follow-up inpatient consult (legacy)",
    "99262": "Follow-up inpatient consult (legacy)",
    "99263": "Follow-up inpatient consult (legacy)",
    # E&M — Legacy/Other
    "99271": "Confirmatory consult (legacy, retired 2006)",
    "99272": "Confirmatory consult (legacy, retired 2006)",
    "99273": "Confirmatory consult (legacy, retired 2006)",
    "99274": "Confirmatory consult (legacy, retired 2006)",
    "99275": "Confirmatory consult (legacy, retired 2006)",
    "99499": "Unlisted E&M service",
    # Simulation
    "77280": "Simulation - simple",
    "77285": "Simulation - intermediate",
    "77290": "Simulation - complex",
    "77293": "Respiratory motion mgmt sim",
    "77011": "CT scan for localization",
    "76370": "CT guidance for procedure",
    # Treatment Planning
    "77261": "Treatment planning - simple",
    "77263": "Treatment planning - complex",
    "77295": "3-D radiotherapy plan",
    "77300": "Radiation therapy dose plan",
    "77301": "IMRT dose plan",
    "77305": "Teletherapy isodose plan",
    "77306": "Teletherapy isodose simple",
    "77307": "Teletherapy isodose complex",
    "77310": "Teletherapy isodose plan",
    "77315": "Teletherapy isodose plan",
    "77316": "Brachytherapy isodose simple",
    "77318": "Brachytherapy isodose complex",
    "77320": "Special teletherapy port plan",
    "77321": "Special teletherapy port plan",
    "77328": "Brachytherapy isodose plan",
    # Physics & Devices
    "77331": "Special radiation dosimetry",
    "77332": "Radiation treatment aid(s)",
    "77333": "Radiation treatment aid(s)",
    "77334": "Radiation treatment aid(s)",
    "77336": "Radiation physics consult",
    "77338": "Design MLC device for IMRT",
    "77370": "Radiation physics consult",
    "77399": "Unlisted medical rad physics",
    "77470": "Special radiation treatment",
    # Treatment Delivery — Standard (2026+ primary, also historical)
    "77402": "Radiation tx delivery - simple",
    "77407": "Radiation tx delivery - intermediate",
    "77412": "Radiation tx delivery - complex",
    # Treatment Delivery — IMRT (thru 2025)
    "77385": "IMRT delivery - simple (thru 2025)",
    "77386": "IMRT delivery - complex (thru 2025)",
    # Treatment Delivery — SRS/SBRT
    "77372": "SRS cranial, linear-based",
    "77373": "SBRT body delivery",
    # Treatment Delivery — Port Films
    "77416": "Radiation tx port film(s)",
    "77417": "Therapeutic radiology port image(s)",
    # Treatment Delivery — Hospital G-codes (thru 2025)
    "G6002": "Stereoscopic x-ray guidance",
    "G6004": "Radiation treatment delivery",
    "G6005": "Radiation treatment delivery",
    "G6006": "Radiation treatment delivery",
    "G6009": "Radiation treatment delivery",
    "G6012": "Radiation treatment delivery",
    "G6013": "Radiation treatment delivery",
    "G6014": "Radiation treatment delivery",
    "G6015": "Radiation tx delivery IMRT",
    # Treatment Delivery — Legacy (pre-2015)
    "77403": "Radiation tx delivery (legacy)",
    "77404": "Radiation tx delivery (legacy)",
    "77408": "Radiation tx delivery (legacy)",
    "77409": "Radiation tx delivery (legacy)",
    "77413": "Radiation tx delivery (legacy)",
    "77414": "Radiation tx delivery (legacy)",
    "77418": "Proton/IMRT delivery (legacy)",
    # Image Guidance
    "77014": "CT scan for therapy guide",
    "77387": "IGRT guidance for delivery",
    "77421": "Stereotactic guidance",
    "0197T": "Intrafraction motion mgmt",
    "G6017": "Intrafraction track motion",
    # Treatment Management
    "77427": "Weekly radiation management x5",
    "77431": "Radiation therapy management",
    "77432": "Stereotactic radiation mgmt",
    "77435": "SBRT management",
    # Brachytherapy
    "77778": "Interstitial brachy - complex",
    "77790": "Radiation handling",
    "76965": "Ultrasound guidance for brachy",
    # Procedures
    "55874": "Transperineal biodegrad implant",
    "55875": "Transperineal needle placement",
    "55876": "Place RT device/marker prostate",
    "76873": "Transrectal prostate US study",
    "76942": "Ultrasound guidance for biopsy",
    "A4646": "Supply: transperineal needle",
    "A4648": "Implantable tissue marker",
    # Drug Administration
    "96400": "Chemotherapy administration",
    "J9217": "Leuprolide acetate suspension",
    "90782": "Injection, therapeutic",
    # Radiopharmaceutical
    "79101": "Nuclear therapy IV admin",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def codes_for_categories(cat_names: list[str]) -> set[str]:
    """Return the union of all CPT codes for the given category names."""
    out: set[str] = set()
    for cat in cat_names:
        out.update(CPT_CATEGORIES.get(cat, set()))
    return out


def codes_for_subcategory(cat: str, subcat: str) -> list[str]:
    """Return ordered codes for a specific subcategory within a category."""
    return CPT_SUBCATEGORIES.get(cat, {}).get(subcat, [])


def subcategory_names(cat: str) -> list[str]:
    """Return ordered subcategory names for a category."""
    return list(CPT_SUBCATEGORIES.get(cat, {}).keys())
