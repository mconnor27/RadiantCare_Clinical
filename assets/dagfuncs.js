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
