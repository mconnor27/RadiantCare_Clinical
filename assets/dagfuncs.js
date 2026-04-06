/**
 * Dash AG Grid function namespace for dynamic cell editor params.
 */
var dagfuncs = (window.dashAgGridFunctions = window.dashAgGridFunctions || {});

/**
 * Subcategory values organized by category.
 * Used by the subcategory column editor to show only relevant options.
 */
dagfuncs.DIAG_SUBCATEGORIES = {
    "Benign Diseases": [
        "", "Dupuytren / Plantar", "Gynecomastia", "Hemangioma",
        "Heterotopic Ossification", "Keloid / Scar", "Neurofibromatosis",
        "Orbital Pseudotumor", "Osteoarthritis", "Rheumatoid Arthritis",
    ],
    "Breast": ["", "Left", "Male", "Right", "Unspecified Laterality"],
    "Central Nervous System": [
        "", "AVM", "Craniopharyngioma", "Glioma / Primary Brain",
        "Hemangioblastoma", "Meningioma", "Ocular / Orbit", "Paraganglioma",
        "Pituitary / Pineal", "Primary Brain", "Schwannoma", "Spinal Cord",
    ],
    "GU \u2013 Non-Prostate": [
        "", "Adrenal", "Bladder", "Kidney / RCC", "Penile", "Testicular", "Urethra",
    ],
    "GU \u2013 Prostate": ["", "Prostate Cancer"],
    "Gastrointestinal": [
        "", "Anal", "Biliary", "Colon", "Esophageal",
        "GIST", "Gastric", "Liver / HCC", "Neuroendocrine",
        "Other/Unspecified", "Pancreatic", "Rectal", "Small Intestine",
    ],
    "Gynecologic": [
        "", "Cervical", "Fallopian / Adnexal", "Other", "Ovarian",
        "Uterine / Endometrial", "Vaginal", "Vulvar",
    ],
    "Head and Neck": [
        "", "Hypopharynx", "Larynx", "Lip", "Nasal Cavity / Sinus", "Nasopharynx",
        "Oral Cavity", "Oropharynx", "Salivary Gland", "Thyroid", "Trachea",
        "Unknown Primary/Other",
    ],
    "Hematologic": [
        "", "Hodgkin Lymphoma", "Kaposi Sarcoma", "Langerhans", "Leukemia", "MALT",
        "MDS/PMF/Splenomegaly", "Mantle Cell", "Mycosis Fungoides",
        "Myeloma / Plasmacytoma", "Non-Hodgkin Lymphoma (Diffuse)",
        "Non-Hodgkin Lymphoma (Follicular)", "Non-Hodgkin Lymphoma (Other)",
        "Other/Unspecified", "T-Cell Lymphoma",
    ],
    "Metastases & Palliative": [
        "", "Adrenal Metastases", "Bone Metastases", "Brain Metastases",
        "Liver Metastases", "Lung Metastases", "Lymph Node Metastases",
        "Neuroendocrine Metastases", "Other Metastases", "Skin Metastases",
    ],
    "Sarcomas": [
        "", "Bone Sarcoma", "Other/Unspecified", "Peripheral Nerve Sheath",
        "Retroperitoneal Sarcoma", "Soft Tissue Sarcoma",
    ],
    "Skin": [
        "", "Melanoma", "Merkel Cell", "Non-Melanoma Skin Cancer",
        "Other/Unspecified",
    ],
    "Thoracic": [
        "", "Lung Cancer", "Mediastinal", "Mesothelioma", "Neuroendocrine",
        "Other", "Thymic",
    ],
};

/**
 * Returns subcategory dropdown values filtered by the row's current category.
 */
dagfuncs.getSubcategoryValues = function (params) {
    var cat = params.data && params.data.category;
    if (cat && dagfuncs.DIAG_SUBCATEGORIES[cat]) {
        return { values: dagfuncs.DIAG_SUBCATEGORIES[cat] };
    }
    // Fallback: show all subcategories grouped by category
    var all = [""];
    Object.keys(dagfuncs.DIAG_SUBCATEGORIES).sort().forEach(function (c) {
        all.push("\u2500\u2500 " + c + " \u2500\u2500");
        dagfuncs.DIAG_SUBCATEGORIES[c].forEach(function (s) {
            if (s && all.indexOf(s) === -1) all.push(s);
        });
    });
    return { values: all };
};
