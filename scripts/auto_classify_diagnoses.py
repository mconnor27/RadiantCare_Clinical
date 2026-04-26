"""One-time auto-classification of unmapped diagnosis codes.

Walks every entry currently surfacing as "uncategorized" in the diagnosis
review queue and assigns a (category, subcategory) override based on
ICD-10 chapter rules. Cancer codes go to their site-specific existing
category; everything we cannot confidently classify (Z surveillance,
R symptoms, comorbidities, free-text admin) goes to "Unknown".

Run with --dry-run to preview counts; without --dry-run to actually
write overrides via upsert_diagnosis_override(..., source="auto_icd_map").
Re-runnable — overrides upsert by icd_code.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

# Allow running as a script from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def propose(code: str, desc: str = "") -> tuple[str, str]:
    """Return (category, subcategory) for an ICD-10 code mapped to the
    existing taxonomy. Returns ("Unknown", "") for codes we can't
    confidently place — those still get an override so the queue stops
    showing them as needing classification, but the classification is
    explicitly "Unknown" rather than blank.
    """
    if not code:
        return ("Unknown", "")
    c = code.upper().strip()
    desc_l = (desc or "").lower()

    # ---- METASTASES (C77-C80) ----
    if c.startswith("C77"):
        return ("Metastases & Palliative", "Lymph Node Metastases")
    if c.startswith("C78.0"):
        return ("Metastases & Palliative", "Lung Metastases")
    if c.startswith("C78.7"):
        return ("Metastases & Palliative", "Liver Metastases")
    if c.startswith("C78"):
        return ("Metastases & Palliative", "Other Metastases")
    if c.startswith("C79.31"):
        return ("Metastases & Palliative", "Brain Metastases")
    if c.startswith("C79.5"):
        return ("Metastases & Palliative", "Bone Metastases")
    if c.startswith("C79.7"):
        return ("Metastases & Palliative", "Adrenal Metastases")
    if c.startswith("C79") or c.startswith("C80"):
        return ("Metastases & Palliative", "Other Metastases")

    # ---- HEMATOLOGIC cancers (C81-C96) ----
    if c.startswith("C81"):
        return ("Hematologic", "Hodgkin Lymphoma")
    if c.startswith("C82"):
        return ("Hematologic", "Non-Hodgkin Lymphoma (Follicular)")
    if c.startswith("C83.1"):
        return ("Hematologic", "Mantle Cell")
    if c.startswith("C83"):
        return ("Hematologic", "Non-Hodgkin Lymphoma (Diffuse)")
    if c.startswith("C84.0"):
        return ("Hematologic", "Mycosis Fungoides")
    if c.startswith("C84") or c.startswith("C86"):
        return ("Hematologic", "T-Cell Lymphoma")
    if c.startswith("C85"):
        return ("Hematologic", "Non-Hodgkin Lymphoma (Other)")
    if c.startswith("C88"):
        return ("Hematologic", "Other/Unspecified")
    if c.startswith("C90"):
        return ("Hematologic", "Myeloma / Plasmacytoma")
    if re.match(r"C9[12345]", c):
        return ("Hematologic", "Leukemia")
    if c.startswith("C96"):
        return ("Hematologic", "Other/Unspecified")
    if c.startswith("C46"):
        return ("Hematologic", "Kaposi Sarcoma")

    # MDS / MPN uncertain-behavior heme (D45-D47)
    if c.startswith("D45") or c.startswith("D46"):
        return ("Hematologic", "MDS/PMF/Splenomegaly")
    if c.startswith("D47.4"):
        return ("Hematologic", "MDS/PMF/Splenomegaly")
    if c.startswith("D47"):
        return ("Hematologic", "Other/Unspecified")

    # Non-cancer heme — blood disorders D50-D89, monocytosis
    if c.startswith("D5") or c.startswith("D6") or c.startswith("D7") or c.startswith("D8"):
        return ("Hematologic", "Other/Unspecified")
    # R59 lymphadenopathy, R70-R72 RBC/WBC findings
    if c.startswith("R59") or re.match(r"R7[012]", c):
        return ("Hematologic", "Other/Unspecified")
    # E83.1 hemochromatosis, E61.1 iron deficiency
    if c.startswith("E83.1") or c.startswith("E61.1"):
        return ("Hematologic", "Other/Unspecified")

    # ---- BREAST (C50, D05) ----
    if c.startswith("C50") or c.startswith("D05"):
        m = re.match(r"^[CD]\d{2}\.\d([12])", c)
        if m:
            return ("Breast", "Right" if m.group(1) == "1" else "Left")
        if "left" in desc_l:
            return ("Breast", "Left")
        if "right" in desc_l:
            return ("Breast", "Right")
        if "male" in desc_l:
            return ("Breast", "Male")
        return ("Breast", "Unspecified Laterality")

    # ---- GASTROINTESTINAL ----
    if c.startswith("C15"):
        return ("Gastrointestinal", "Esophageal")
    if c.startswith("C16"):
        return ("Gastrointestinal", "Gastric")
    if c.startswith("C17"):
        return ("Gastrointestinal", "Small Intestine")
    if c.startswith("C18"):
        return ("Gastrointestinal", "Colon")
    if c.startswith("C19") or c.startswith("C20"):
        return ("Gastrointestinal", "Rectal")
    if c.startswith("C21"):
        return ("Gastrointestinal", "Anal")
    if c.startswith("C22"):
        return ("Gastrointestinal", "Liver / HCC")
    if c.startswith("C23") or c.startswith("C24"):
        return ("Gastrointestinal", "Biliary")
    if c.startswith("C25"):
        return ("Gastrointestinal", "Pancreatic")
    if (c.startswith("C26") or c.startswith("D00") or c.startswith("D01")
            or c.startswith("D37")):
        return ("Gastrointestinal", "Other/Unspecified")
    if c.startswith("C7A") or c.startswith("D3A"):
        return ("Gastrointestinal", "Neuroendocrine")
    # K-codes — GI workup
    if c.startswith("K"):
        if "liver" in desc_l or "hepat" in desc_l:
            return ("Gastrointestinal", "Liver / HCC")
        if "pancrea" in desc_l:
            return ("Gastrointestinal", "Pancreatic")
        return ("Gastrointestinal", "Other/Unspecified")
    # Hepatitis → Liver
    if re.match(r"B1[789]", c):
        return ("Gastrointestinal", "Liver / HCC")
    # R18 ascites, R19 abdominal mass — GI/Other
    if c.startswith("R18") or c.startswith("R19"):
        return ("Gastrointestinal", "Other/Unspecified")
    if c.startswith("R97.0"):  # CEA elevated
        return ("Gastrointestinal", "Other/Unspecified")

    # ---- GYNECOLOGIC ----
    if (c.startswith("C51") or c.startswith("D07.1") or c.startswith("D07.2")
            or c.startswith("D07.3")):
        return ("Gynecologic", "Vulvar")
    if c.startswith("C52"):
        return ("Gynecologic", "Vaginal")
    if c.startswith("C53") or c.startswith("D06"):
        return ("Gynecologic", "Cervical")
    if c.startswith("C54") or c.startswith("C55") or c.startswith("D07.0"):
        return ("Gynecologic", "Uterine / Endometrial")
    if c.startswith("C56") or c.startswith("D07.39"):
        return ("Gynecologic", "Ovarian")
    if c.startswith("C57.0"):
        return ("Gynecologic", "Fallopian / Adnexal")
    if c.startswith("C57") or c.startswith("C58") or c.startswith("D07"):
        return ("Gynecologic", "Other")
    if c.startswith("D39.1"):
        return ("Gynecologic", "Ovarian")
    if c.startswith("D39.0"):
        return ("Gynecologic", "Uterine / Endometrial")
    if c.startswith("D39"):
        return ("Gynecologic", "Other")
    if c.startswith("D25") or c.startswith("D26"):
        return ("Gynecologic", "Uterine / Endometrial")
    if c.startswith("D27"):  # ovarian teratoma / cyst
        return ("Gynecologic", "Ovarian")
    # N-codes — kidney/ureter → GU; rest are female reproductive → Gyn
    if (c.startswith("N17") or c.startswith("N18") or c.startswith("N19")
            or c.startswith("N28") or c.startswith("N20") or c.startswith("N21")):
        return ("GU – Non-Prostate", "Kidney / RCC")
    if c.startswith("N32") or c.startswith("N30"):
        return ("GU – Non-Prostate", "Bladder")
    if c.startswith("N4") or c.startswith("N50") or c.startswith("N51"):
        return ("GU – Non-Prostate", "Penile")
    if c.startswith("N"):
        return ("Gynecologic", "Other")
    # Obstetric → Gyn
    if c.startswith("O"):
        return ("Gynecologic", "Other")
    # Vulvar lichen sclerosus
    if c.startswith("L90.0"):
        return ("Gynecologic", "Vulvar")
    # HPV → cervical (precursor)
    if c.startswith("B97.7"):
        return ("Gynecologic", "Cervical")
    # R87 abnormal cervical cytology
    if c.startswith("R87"):
        return ("Gynecologic", "Cervical")
    # R10.20 adnexal pain → Gyn
    if c.startswith("R10.2") or c.startswith("R10.3"):
        return ("Gynecologic", "Other")
    # CA 125 elevated → ovarian marker
    if c.startswith("R97.1"):
        return ("Gynecologic", "Ovarian")

    # ---- GU (C60-C68, C74) ----
    if c.startswith("C60"):
        return ("GU – Non-Prostate", "Penile")
    if c.startswith("C61"):
        return ("GU – Prostate", "Prostate Cancer")
    if c.startswith("C62"):
        return ("GU – Non-Prostate", "Testicular")
    if c.startswith("C63"):
        return ("GU – Non-Prostate", "Penile")
    if re.match(r"C6[456]", c):
        return ("GU – Non-Prostate", "Kidney / RCC")
    if c.startswith("C67"):
        return ("GU – Non-Prostate", "Bladder")
    if c.startswith("C68"):
        return ("GU – Non-Prostate", "Urethra")
    if c.startswith("C74"):
        return ("GU – Non-Prostate", "Adrenal")
    if c.startswith("D40.0"):
        return ("GU – Prostate", "Prostate Cancer")
    if c.startswith("D40"):
        return ("GU – Non-Prostate", "Testicular")
    if c.startswith("D41.0") or c.startswith("D41.1"):
        return ("GU – Non-Prostate", "Kidney / RCC")
    if c.startswith("D41"):
        return ("GU – Non-Prostate", "Bladder")
    if c.startswith("D49.5"):
        return ("GU – Non-Prostate", "Bladder")

    # ---- THORACIC ----
    if c.startswith("C34") or c.startswith("D02.2") or c.startswith("D38.1"):
        return ("Thoracic", "Lung Cancer")
    if c.startswith("C37"):
        return ("Thoracic", "Thymic")
    if c.startswith("C38"):
        return ("Thoracic", "Mediastinal")
    if c.startswith("C39"):
        return ("Thoracic", "Other")
    if c.startswith("C45"):
        return ("Thoracic", "Mesothelioma")
    if c.startswith("J91") or c.startswith("J94"):
        return ("Thoracic", "Other")  # pleural effusion / mass

    # ---- HEAD AND NECK ----
    if re.match(r"C0[0-6]", c):
        return ("Head and Neck", "Oral Cavity")
    if re.match(r"C0[78]", c):
        return ("Head and Neck", "Salivary Gland")
    if re.match(r"C[01][09]", c):
        return ("Head and Neck", "Oropharynx")
    if c.startswith("C11"):
        return ("Head and Neck", "Nasopharynx")
    if c.startswith("C12") or c.startswith("C13"):
        return ("Head and Neck", "Hypopharynx")
    if c.startswith("C14"):
        return ("Head and Neck", "Unknown Primary/Other")
    if c.startswith("C30") or c.startswith("C31"):
        return ("Head and Neck", "Nasal Cavity / Sinus")
    if c.startswith("C32"):
        return ("Head and Neck", "Larynx")
    if c.startswith("C33"):
        return ("Head and Neck", "Trachea")
    if c.startswith("C73"):
        return ("Head and Neck", "Thyroid")

    # ---- SKIN ----
    if c.startswith("C43") or c.startswith("D03"):
        return ("Skin", "Melanoma")
    if c.startswith("C44") or c.startswith("D04"):
        return ("Skin", "Non-Melanoma Skin Cancer")
    if c.startswith("C4A"):
        return ("Skin", "Merkel Cell")
    if c.startswith("L8"):
        return ("Skin", "Other/Unspecified")

    # ---- CNS ----
    if c.startswith("C70"):
        return ("Central Nervous System", "Meningioma")
    if c.startswith("C71"):
        return ("Central Nervous System", "Glioma / Primary Brain")
    if c.startswith("C72"):
        return ("Central Nervous System", "Spinal Cord")
    if c.startswith("C75"):
        return ("Central Nervous System", "Pituitary / Pineal")
    if c.startswith("D32"):
        return ("Central Nervous System", "Meningioma")
    if c.startswith("D33"):
        return ("Central Nervous System", "Glioma / Primary Brain")
    if (c.startswith("D35.2") or c.startswith("D35.3")
            or c.startswith("D35.4")):
        return ("Central Nervous System", "Pituitary / Pineal")
    if c.startswith("D42") or c.startswith("D43"):
        return ("Central Nervous System", "Glioma / Primary Brain")

    # ---- SARCOMAS ----
    if c.startswith("C40") or c.startswith("C41"):
        return ("Sarcomas", "Bone Sarcoma")
    if c.startswith("C48"):
        return ("Sarcomas", "Retroperitoneal Sarcoma")
    if c.startswith("C49") or c.startswith("D21"):
        return ("Sarcomas", "Soft Tissue Sarcoma")

    # M-codes — pathological fractures often = bone mets
    if c.startswith("M81") or c.startswith("M89") or c.startswith("M85"):
        return ("Metastases & Palliative", "Bone Metastases")

    # D49 unspecified neoplasm — try to match by description
    if c.startswith("D49"):
        if "breast" in desc_l:
            return ("Breast", "Unspecified Laterality")
        if "ovar" in desc_l:
            return ("Gynecologic", "Ovarian")
        if "uter" in desc_l:
            return ("Gynecologic", "Uterine / Endometrial")
        if "prostate" in desc_l:
            return ("GU – Prostate", "Prostate Cancer")

    # Everything else (Z surveillance, R symptoms, I comorbidities,
    # F psych, G nervous-non-cancer, Q congenital, T trauma, free-text admin)
    # → Unknown
    return ("Unknown", "")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print summary without writing overrides",
    )
    parser.add_argument(
        "--source-tag", default="auto_icd_map",
        help="Value written to overrides.source (default: auto_icd_map)",
    )
    args = parser.parse_args()

    # Load app + diag grid data lazily so the script can be imported as a module
    import os
    os.environ.setdefault("PHI_MODE", "off")
    import dash_app  # noqa: F401  bootstrap pages
    import pages.referrals as R
    from data.reviews_db import upsert_diagnosis_override

    rows, _, _ = R._build_diag_grid_data()
    unmapped = [r for r in rows if not r["category"]]

    proposals = []
    for r in unmapped:
        code = r.get("icd_code", "") or ""
        desc = r.get("description", "") or ""
        cat, sub = propose(code, desc)
        # Free-text rows have no ICD code; they're keyed by lowercased text.
        # The override table is keyed on icd_code, so we use the description's
        # lowercased form as the key for free-text (matches _build_diag_grid_data).
        key = code if code else desc.lower().strip()
        if not key:
            continue
        proposals.append((key, cat, sub, r.get("patients", 0), code, desc))

    # Summary
    by_cat = Counter((cat, sub) for _, cat, sub, *_ in proposals)
    by_status = Counter("Unknown" if cat == "Unknown" else "Mapped"
                        for _, cat, _, *_ in proposals)
    refs_by_status = Counter()
    for _, cat, _, pts, *_ in proposals:
        refs_by_status["Unknown" if cat == "Unknown" else "Mapped"] += pts

    print(f"Total uncategorized entries: {len(unmapped):,}")
    print(f"Will write overrides for:    {len(proposals):,}")
    print()
    print(f"  Mapped to existing categories: {by_status['Mapped']:,} entries  "
          f"({refs_by_status['Mapped']:,} referrals)")
    print(f"  Mapped to 'Unknown':           {by_status['Unknown']:,} entries  "
          f"({refs_by_status['Unknown']:,} referrals)")
    print()
    print(f"{'Category / Subcategory':<55s} {'Count':>6s}")
    print("-" * 65)
    for (cat, sub), n in sorted(by_cat.items(), key=lambda x: -x[1]):
        sub_d = sub if sub else "—"
        print(f"  {cat} / {sub_d:<45s} {n:>6,}")

    if args.dry_run:
        print("\n(dry run — no DB writes)")
        return

    print(f"\nWriting {len(proposals):,} overrides with source='{args.source_tag}'…")
    written = 0
    for key, cat, sub, _pts, code, _desc in proposals:
        try:
            upsert_diagnosis_override(
                key, category=cat, subcategory=sub,
                source=args.source_tag,
            )
            written += 1
        except Exception as e:
            print(f"  ERROR on {key!r}: {e}")
    print(f"Done. Wrote {written:,} overrides.")


if __name__ == "__main__":
    main()
