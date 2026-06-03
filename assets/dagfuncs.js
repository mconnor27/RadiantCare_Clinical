/**
 * Dash AG Grid function namespace for dynamic cell editor params.
 */
var dagfuncs = (window.dashAgGridFunctions = window.dashAgGridFunctions || {});

/**
 * Diagnosis taxonomy — populated dynamically from Python via a dcc.Store.
 * The store callback sets window._diagTaxonomy = {category: [subcategories]}.
 * Falls back to empty if not yet loaded.
 */
dagfuncs._getDiagTaxonomy = function () {
    return window._diagTaxonomy || {};
};



/**
 * Returns document.body as popup parent so dropdowns render above modals.
 */
dagfuncs.setPopupParent = function () {
    return document.body;
};


/**
 * Parse an "MM/DD/YYYY" string into a sortable YYYYMMDD integer.
 * Returns null for blank/unparseable values.
 */
dagfuncs._parseMDY = function (s) {
    if (!s || typeof s !== "string") return null;
    var parts = s.split("/");
    if (parts.length !== 3) return null;
    var m = parseInt(parts[0], 10);
    var d = parseInt(parts[1], 10);
    var y = parseInt(parts[2], 10);
    if (isNaN(m) || isNaN(d) || isNaN(y)) return null;
    return y * 10000 + m * 100 + d;
};


/**
 * Comparator for columns holding "MM/DD/YYYY" date strings. Sorts
 * chronologically instead of lexically (the default text sort compares the
 * MM/DD prefix first, so 01/02/2026 wrongly precedes 01/03/2015). Blanks
 * sort to the bottom of an ascending list.
 */
dagfuncs.compareMDY = function (a, b) {
    var pa = dagfuncs._parseMDY(a);
    var pb = dagfuncs._parseMDY(b);
    if (pa === null && pb === null) return 0;
    if (pa === null) return 1;
    if (pb === null) return -1;
    return pa - pb;
};


/**
 * Returns institution dropdown values with type-to-filter.
 * Collects all unique institutions from the grid data.
 */
dagfuncs.getInstitutionValues = function (params) {
    var institutions = [""];
    var seen = {};
    if (params.api) {
        params.api.forEachNode(function (node) {
            if (node.data && node.data.institution && !seen[node.data.institution]) {
                seen[node.data.institution] = true;
                institutions.push(node.data.institution);
            }
        });
    }
    institutions.sort(function (a, b) {
        if (a === "") return -1;
        if (b === "") return 1;
        return a.localeCompare(b);
    });
    return { values: institutions, allowTyping: true, filterList: true, searchType: "matchAny" };
};


/**
 * Returns subcategory dropdown values filtered by the row's current category.
 */
dagfuncs.getSubcategoryValues = function (params) {
    var taxonomy = dagfuncs._getDiagTaxonomy();
    var cat = params.data && (params.data.ai_category || params.data.category);
    if (cat && taxonomy[cat]) {
        return { values: [""].concat(taxonomy[cat]) };
    }
    // Fallback: show all subcategories grouped by category
    var all = [""];
    Object.keys(taxonomy).sort().forEach(function (c) {
        all.push("\u2500\u2500 " + c + " \u2500\u2500");
        (taxonomy[c] || []).forEach(function (s) {
            if (s && all.indexOf(s) === -1) all.push(s);
        });
    });
    return { values: all };
};
