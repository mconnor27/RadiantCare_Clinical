/**
 * Custom AG Grid cell renderer components for dash-ag-grid.
 */
var dagcomponentfuncs = (window.dashAgGridComponentFunctions =
    window.dashAgGridComponentFunctions || {});

/**
 * Referral count link — clickable number that triggers detail panel.
 * Uses setData to signal the detail request.
 */
dagcomponentfuncs.ReferralCountLink = function (props) {
    var value = props.value;
    if (value === null || value === undefined) {
        return React.createElement("span", {style: {color: "#9CA3AF"}}, "\u2014");
    }
    function handleClick(e) {
        e.stopPropagation();
        // Write to a hidden Store to trigger the detail callback
        var data = props.data || {};
        var payload = {
            npi: data.npi || "",
            address_key: data.address_key || "",
            name: data.name || "",
            ts: Date.now(),
        };
        if (window.dash_clientside) {
            window.dash_clientside.set_props("referrals-rpm-detail-store", {data: payload});
        }
    }
    return React.createElement(
        "span",
        {
            onClick: handleClick,
            style: {
                color: "#2196F3",
                cursor: "pointer",
                textDecoration: "underline",
                fontSize: "12px",
            },
            title: "View referrals",
        },
        value
    );
};


/**
 * Institution badge — colored pill with X to clear.
 * Uses setData to write the cleared value back (triggers cellValueChanged).
 * Double-click the cell to enter edit mode (dropdown editor).
 */
dagcomponentfuncs.InstitutionBadge = function (props) {
    var value = props.value || "";
    if (!value) {
        return React.createElement(
            "span",
            {
                style: {color: "#9CA3AF", fontSize: "12px", fontStyle: "italic", cursor: "pointer"},
                title: "Double-click to assign institution",
            },
            "— unassigned —"
        );
    }
    // Hash-based color from palette
    var colors = [
        {bg: "#EDE9FE", text: "#6D28D9", x: "#A78BFA"},  // violet
        {bg: "#DBEAFE", text: "#1D4ED8", x: "#60A5FA"},  // blue
        {bg: "#D1FAE5", text: "#047857", x: "#34D399"},  // green
        {bg: "#FEE2E2", text: "#B91C1C", x: "#F87171"},  // red
        {bg: "#FEF3C7", text: "#92400E", x: "#FBBF24"},  // amber
        {bg: "#E0E7FF", text: "#3730A3", x: "#818CF8"},  // indigo
        {bg: "#FCE7F3", text: "#9D174D", x: "#F472B6"},  // pink
        {bg: "#CCFBF1", text: "#0F766E", x: "#2DD4BF"},  // teal
    ];
    var hash = 0;
    for (var i = 0; i < value.length; i++) {
        hash = ((hash << 5) - hash + value.charCodeAt(i)) | 0;
    }
    var c = colors[Math.abs(hash) % colors.length];

    function clearInstitution(e) {
        e.stopPropagation();
        // Write empty value back — triggers cellValueChanged
        var updated = Object.assign({}, props.data, {institution: ""});
        props.setData(updated);
    }

    return React.createElement(
        "div",
        {style: {display: "flex", alignItems: "center", height: "100%", gap: "0px", minWidth: 0}},
        React.createElement(
            "span",
            {
                style: {
                    background: c.bg,
                    color: c.text,
                    padding: "1px 6px 1px 10px",
                    borderRadius: "12px",
                    fontSize: "12px",
                    fontWeight: 600,
                    lineHeight: "22px",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0px",
                    maxWidth: "100%",
                    minWidth: 0,
                },
            },
            React.createElement(
                "span",
                {
                    style: {
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        minWidth: 0,
                    },
                },
                value
            ),
            React.createElement(
                "span",
                {
                    onClick: clearInstitution,
                    style: {
                        cursor: "pointer",
                        color: c.x,
                        fontSize: "14px",
                        fontWeight: "bold",
                        lineHeight: 1,
                        marginLeft: "4px",
                        opacity: 0.7,
                        flexShrink: 0,
                    },
                    title: "Clear institution",
                    onMouseEnter: function(e) { e.target.style.opacity = 1; },
                    onMouseLeave: function(e) { e.target.style.opacity = 0.7; },
                },
                "\u00d7"
            )
        )
    );
};


/**
 * Delete button for institution management grid.
 */
dagcomponentfuncs.InstitutionDelete = function (props) {
    function handleDelete(e) {
        e.stopPropagation();
        var data = Object.assign({}, props.data, {_action: "delete"});
        props.setData(data);
    }
    return React.createElement(
        "div",
        {style: {display: "flex", alignItems: "center", justifyContent: "center", height: "100%"}},
        React.createElement(
            "button",
            {
                onClick: handleDelete,
                style: {
                    background: "transparent",
                    border: "1px solid #E5E7EB",
                    borderRadius: "4px",
                    color: "#9CA3AF",
                    cursor: "pointer",
                    fontSize: "11px",
                    padding: "1px 8px",
                    lineHeight: "20px",
                },
                title: "Delete institution (clears from all physicians)",
                onMouseEnter: function(e) { e.target.style.color = "#EF4444"; e.target.style.borderColor = "#EF4444"; },
                onMouseLeave: function(e) { e.target.style.color = "#9CA3AF"; e.target.style.borderColor = "#E5E7EB"; },
            },
            "Delete"
        )
    );
};


/**
 * Provider name with Google search icon.
 * Uses name_raw (with credentials) for the search query.
 */
dagcomponentfuncs.NameSearch = function (props) {
    var name = props.value || "";
    var data = props.data || {};
    var raw = data.name_raw || name;
    if (!name) {
        return React.createElement("span", {style: {color: "#9CA3AF"}}, "—");
    }
    var query = raw + (data.city ? " " + data.city : "") + (data.state ? " " + data.state : "");
    var searchUrl = "https://www.google.com/search?q=" + encodeURIComponent(query);

    return React.createElement(
        "div",
        {style: {display: "flex", alignItems: "center", height: "100%", gap: "4px", minWidth: 0}},
        React.createElement(
            "span",
            {style: {overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0, flex: 1, fontSize: "12px"}},
            name
        ),
        React.createElement(
            "a",
            {
                href: searchUrl,
                target: "_blank",
                rel: "noopener",
                style: {color: "#6B7280", textDecoration: "none", fontSize: "13px", flexShrink: 0},
                title: "Google: " + raw,
            },
            "\uD83D\uDD0D"
        )
    );
};


/**
 * Provider name with Google search + address map link (for review grid).
 */
dagcomponentfuncs.NameSearchFull = function (props) {
    var name = props.value || "";
    var data = props.data || {};
    var raw = data.name_raw || name;
    if (!name) {
        return React.createElement("span", {style: {color: "#9CA3AF"}}, "—");
    }
    var query = raw + (data.city ? " " + data.city : "") + (data.state ? " " + data.state : "");
    var searchUrl = "https://www.google.com/search?q=" + encodeURIComponent(query);
    var linkStyle = {color: "#6B7280", textDecoration: "none", fontSize: "13px", flexShrink: 0};

    var icons = [
        React.createElement(
            "a", {href: searchUrl, target: "_blank", rel: "noopener", style: linkStyle, title: "Google: " + raw, key: "s"},
            "\uD83D\uDD0D"
        ),
    ];
    var addrParts = [data.address, data.city, data.state, data.zip].filter(Boolean);
    if (addrParts.length > 0) {
        var addrFull = addrParts.join(", ");
        icons.push(
            React.createElement(
                "a", {href: "https://www.google.com/search?q=" + encodeURIComponent(addrFull),
                      target: "_blank", rel: "noopener", style: linkStyle, title: "Search: " + addrFull, key: "m"},
                "\uD83D\uDCCD"
            )
        );
    }

    return React.createElement(
        "div",
        {style: {display: "flex", alignItems: "center", height: "100%", gap: "3px", minWidth: 0}},
        React.createElement(
            "span",
            {style: {overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0, flex: 1, fontSize: "12px"}},
            name
        ),
        React.createElement("span", {style: {display: "flex", gap: "2px", flexShrink: 0}}, icons)
    );
};


/**
 * NPI link — renders NPI as a link to the NPPES registry page.
 */
dagcomponentfuncs.NpiLink = function (props) {
    var npi = (props.value || "").toString();
    // Synthetic name-based key (no ID in source) — render the row as dash so
    // the NPI cell isn't shouting a non-clickable internal key at the user.
    // The Name column carries the actual identity.
    if (!npi || npi.indexOf("name:") === 0) {
        return React.createElement("span", {style: {color: "#9CA3AF"}}, "—");
    }
    // Real 10-digit NPI → NPPES link.
    if (/^\d{10}$/.test(npi)) {
        var url = "https://npiregistry.cms.hhs.gov/provider-view/" + npi;
        return React.createElement(
            "a",
            {
                href: url,
                target: "_blank",
                rel: "noopener",
                style: {color: "#2196F3", textDecoration: "none", fontSize: "12px"},
                title: "View on NPI Registry",
            },
            npi
        );
    }
    // Other stable IDs (state license like A02637 etc.) — show as plain text
    // so the user can still see/edit the identifier, but no broken NPPES link.
    return React.createElement(
        "span",
        {style: {fontSize: "12px"}, title: "Non-NPI provider ID"},
        npi
    );
};


/**
 * Address with Google Maps and Google Search links.
 * Expects props.data to have: address, city, state, zip fields.
 */
dagcomponentfuncs.AddressLinks = function (props) {
    var data = props.data || {};
    var parts = [data.address, data.city, data.state, data.zip].filter(Boolean);
    var full = parts.join(", ");
    if (!full) {
        return React.createElement("span", {style: {color: "#9CA3AF"}}, "—");
    }
    var searchUrl = "https://www.google.com/search?q=" + encodeURIComponent(full);

    var linkStyle = {
        color: "#6B7280",
        textDecoration: "none",
        fontSize: "13px",
        marginLeft: "4px",
    };

    return React.createElement(
        "div",
        {style: {display: "flex", alignItems: "center", height: "100%", gap: "2px", overflow: "hidden"}},
        React.createElement(
            "span",
            {style: {fontSize: "12px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1}},
            full
        ),
        React.createElement(
            "a",
            {href: searchUrl, target: "_blank", rel: "noopener", style: linkStyle, title: "Google Search"},
            "📍"
        ),
        React.createElement(
            "a",
            {href: searchUrl, target: "_blank", rel: "noopener", style: linkStyle, title: "Google Search"},
            "🔍"
        )
    );
};


/**
 * Address with click-to-copy + Google search link.
 * Shows full_address value. Click the text to copy, click the icon to search.
 * Manually edited addresses show in purple italic (handled by cellStyle).
 */
dagcomponentfuncs.AddressCopy = function (props) {
    var value = props.value;
    if (!value) {
        return React.createElement("span", {style: {color: "#9CA3AF"}}, "\u2014");
    }
    var searchUrl = "https://www.google.com/search?q=" + encodeURIComponent(value);

    return React.createElement(
        "div",
        {style: {display: "flex", alignItems: "center", height: "100%", gap: "3px", overflow: "hidden"}},
        React.createElement(
            "span",
            {
                style: {
                    fontSize: "12px",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    flex: 1,
                },
            },
            value
        ),
        React.createElement(
            "a",
            {href: searchUrl, target: "_blank", rel: "noopener",
             onClick: function (e) { e.stopPropagation(); },
             style: {color: "#6B7280", textDecoration: "none", fontSize: "13px"},
             title: "Google Search"},
            "\ud83d\udd0d"
        )
    );
};


/**
 * AddressAutocompleteEditor \u2014 popup editor for the Address column.
 * Mirrors the mobile pattern: free-text input with a ranked dropdown of
 * existing addresses (same NPI first, then any other provider). Pick one
 * to fill the cell; type a fresh address and Enter/Tab commits it.
 */
dagcomponentfuncs.AddressAutocompleteEditor = function (props) {
    var ref = React.useRef(null);
    var _s = React.useState(props.value || "");
    var value = _s[0], setValue = _s[1];
    var _o = React.useState(true);
    var open = _o[0], setOpen = _o[1];

    var npi = (props.data && props.data.npi) || "";
    var rowKey = (props.data && props.data.row_key) || "";

    // Gather all unique addresses from the grid, ranked: same-NPI first
    // (alternative addresses for this provider), then everything else.
    var allAddresses = React.useMemo(function () {
        var sameNpi = [];
        var other = [];
        var seen = {};
        if (props.api) {
            props.api.forEachNode(function (node) {
                var d = node.data;
                if (!d) return;
                var a = (d.full_address || "").trim();
                if (!a || seen[a]) return;
                if (d.row_key === rowKey) return;  // skip the row we're editing
                seen[a] = true;
                if (d.npi === npi) sameNpi.push(a);
                else other.push(a);
            });
        }
        sameNpi.sort();
        other.sort();
        return sameNpi.concat(other);
    }, []);

    var filtered = allAddresses.filter(function (a) {
        return value === "" || a.toLowerCase().indexOf(value.toLowerCase()) !== -1;
    });

    React.useEffect(function () {
        if (ref.current) { ref.current.focus(); ref.current.select(); }
    }, []);

    function commitValue(val) {
        setValue(val);
        setOpen(false);
        if (props.onValueChange) props.onValueChange(val);
        if (props.stopEditing) setTimeout(function () { props.stopEditing(); }, 50);
    }

    var containerStyle = {position: "relative", width: "100%", minWidth: "320px"};
    var inputStyle = {
        width: "100%", height: "36px",
        border: "2px solid #7C2A83", borderRadius: "4px",
        padding: "0 8px", fontSize: "13px",
        boxSizing: "border-box", outline: "none",
    };
    var dropdownStyle = {
        position: "absolute", top: "100%", left: 0, right: 0,
        maxHeight: "240px", overflowY: "auto",
        background: "#fff", border: "1px solid #dee2e6",
        borderRadius: "0 0 6px 6px",
        boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
        zIndex: 9999,
        display: open && filtered.length > 0 ? "block" : "none",
    };
    var itemStyle = {padding: "6px 10px", cursor: "pointer", fontSize: "13px"};
    var groupHeaderStyle = {
        padding: "4px 10px", fontSize: "11px", fontWeight: 600,
        color: "#6B7280", background: "#F9FAFB", textTransform: "uppercase",
    };

    function handleChange(e) {
        setValue(e.target.value);
        setOpen(true);
        if (props.onValueChange) props.onValueChange(e.target.value);
    }

    var sameNpiSet = {};
    allAddresses.slice(0, 9999).forEach(function () {});  // no-op for clarity
    // Re-derive grouping by checking against the rendered nodes again.
    if (props.api) {
        props.api.forEachNode(function (node) {
            if (node.data && node.data.npi === npi && node.data.full_address) {
                sameNpiSet[node.data.full_address] = true;
            }
        });
    }

    var items = [];
    var renderedSameNpiHeader = false;
    var renderedOtherHeader = false;
    filtered.forEach(function (a) {
        var isSame = sameNpiSet[a];
        if (isSame && !renderedSameNpiHeader) {
            items.push(React.createElement("div",
                {key: "_h_same", style: groupHeaderStyle}, "Same NPI"));
            renderedSameNpiHeader = true;
        }
        if (!isSame && !renderedOtherHeader) {
            items.push(React.createElement("div",
                {key: "_h_other", style: groupHeaderStyle}, "Other providers"));
            renderedOtherHeader = true;
        }
        items.push(React.createElement("div", {
            key: a,
            onMouseDown: function (e) { e.preventDefault(); commitValue(a); },
            onMouseEnter: function (e) { e.target.style.background = "#f0e6f6"; },
            onMouseLeave: function (e) { e.target.style.background = "#fff"; },
            style: itemStyle,
        }, a));
    });

    return React.createElement("div", {style: containerStyle},
        React.createElement("input", {
            ref: ref, value: value, onChange: handleChange,
            placeholder: "Pick an existing address or type a new one\u2026",
            onKeyDown: function (e) {
                if (e.key === "Enter") commitValue(value);
                else if (e.key === "Escape") props.stopEditing(true);
                else if (e.key === "Tab") commitValue(value);
            },
            style: inputStyle,
        }),
        React.createElement("div", {style: dropdownStyle}, items)
    );
};


/**
 * Review buttons for CPT Audit table.
 * Shows OK/Fixed/Course OK for unreviewed, or status label + Undo for reviewed.
 */
dagcomponentfuncs.CptReviewButtons = function (props) {
    var data = props.data || {};
    var status = data.ReviewStatus || "";
    var source = data.ReviewSource || "";

    var btnStyle = {
        padding: "1px 8px",
        fontSize: "11px",
        cursor: "pointer",
        borderRadius: "4px",
        background: "transparent",
        fontWeight: 600,
        lineHeight: "20px",
        border: "1px solid",
    };

    function send(action) {
        var payload = Object.assign({}, data, { _action: action, _ts: Date.now() });
        if (window.dash_clientside) {
            window.dash_clientside.set_props("cpt-store-review-action", { data: payload });
        }
    }

    if (status === "OK" || status === "Fixed") {
        var color = status === "OK" ? "#4CAF50" : "#7C2A83";
        var label = "\u2713 " + status;
        if (source === "course") label += " (course)";

        return React.createElement(
            "div",
            { style: { display: "flex", gap: "6px", alignItems: "center", height: "100%" } },
            React.createElement("span", { style: { color: color, fontWeight: 600, fontSize: "12px" } }, label),
            React.createElement(
                "button",
                {
                    onClick: function () {
                        send(source === "course" ? "undo_course" : "undo");
                    },
                    style: Object.assign({}, btnStyle, {
                        color: "#9CA3AF",
                        borderColor: "#D1D5DB",
                        fontSize: "10px",
                        padding: "0px 6px",
                    }),
                },
                "Undo"
            )
        );
    }

    /* Unreviewed — show action buttons */
    return React.createElement(
        "div",
        { style: { display: "flex", gap: "4px", alignItems: "center", height: "100%" } },
        React.createElement(
            "button",
            {
                onClick: function () { send("OK"); },
                style: Object.assign({}, btnStyle, { color: "#4CAF50", borderColor: "#4CAF50" }),
            },
            "OK"
        ),
        React.createElement(
            "button",
            {
                onClick: function () { send("Fixed"); },
                style: Object.assign({}, btnStyle, { color: "#2196F3", borderColor: "#2196F3" }),
            },
            "Fixed"
        ),
        React.createElement(
            "button",
            {
                onClick: function () { send("Course OK"); },
                style: Object.assign({}, btnStyle, { color: "#009688", borderColor: "#009688" }),
            },
            "Course OK"
        )
    );
};

/**
 * EOT Audit override buttons — Waive an open task, Reopen a documented one,
 * Undo either. Sends {CourseKey, _action} to eot-store-override-action;
 * the server callback persists it (reviews_db.eot_overrides) and refreshes.
 */
dagcomponentfuncs.EotOverrideButtons = function (props) {
    var data = props.data || {};
    var status = data.DocStatus || "";

    var btnStyle = {
        padding: "1px 8px",
        fontSize: "11px",
        cursor: "pointer",
        borderRadius: "4px",
        background: "transparent",
        fontWeight: 600,
        lineHeight: "20px",
        border: "1px solid",
    };

    function send(action) {
        var payload = {
            CourseKey: data.CourseKey,
            _action: action,
            _ts: Date.now(),
        };
        if (window.dash_clientside) {
            window.dash_clientside.set_props("eot-store-override-action", { data: payload });
        }
    }

    function undoRow(label, color) {
        return React.createElement(
            "div",
            { style: { display: "flex", gap: "6px", alignItems: "center", height: "100%" } },
            React.createElement("span", { style: { color: color, fontWeight: 600, fontSize: "12px" } }, label),
            React.createElement(
                "button",
                {
                    onClick: function () { send("undo"); },
                    style: Object.assign({}, btnStyle, {
                        color: "#9CA3AF",
                        borderColor: "#D1D5DB",
                        fontSize: "10px",
                        padding: "0px 6px",
                    }),
                },
                "Undo"
            )
        );
    }

    if (status === "Waived") return undoRow("✓ Waived", "#9E9E9E");
    if (status === "Reopened") return undoRow("↺ Reopened", "#1976D2");

    if (status === "Missing" || status === "Pending") {
        return React.createElement(
            "div",
            { style: { display: "flex", gap: "4px", alignItems: "center", height: "100%" } },
            React.createElement(
                "button",
                {
                    onClick: function () { send("waive"); },
                    style: Object.assign({}, btnStyle, { color: "#9E9E9E", borderColor: "#9E9E9E" }),
                },
                "Waive"
            )
        );
    }

    if (status === "Documented") {
        return React.createElement(
            "div",
            { style: { display: "flex", gap: "4px", alignItems: "center", height: "100%" } },
            React.createElement(
                "button",
                {
                    onClick: function () { send("reopen"); },
                    style: Object.assign({}, btnStyle, { color: "#1976D2", borderColor: "#1976D2" }),
                },
                "Reopen"
            )
        );
    }

    return React.createElement("span", null, "");
};

/**
 * Diagnosis patient count link — clickable number that triggers detail panel.
 * Works for both referrals page (referrals-rpm-diag-detail-store)
 * and diagnosis page (diag-mgr-detail-store).
 */
dagcomponentfuncs.DiagCountLink = function (props) {
    var value = props.value;
    if (value === null || value === undefined || value === 0) {
        return React.createElement("span", {style: {color: "#9CA3AF"}}, value === 0 ? "0" : "\u2014");
    }
    function handleClick(e) {
        e.stopPropagation();
        var data = props.data || {};
        var payload = {
            icd_code: data.icd_code || "",
            description: data.description || "",
            category: data.category || "",
            ts: Date.now(),
        };
        var storeId = props.colDef && props.colDef.cellRendererParams && props.colDef.cellRendererParams.storeId;
        if (!storeId) storeId = "referrals-rpm-diag-detail-store";
        if (window.dash_clientside) {
            window.dash_clientside.set_props(storeId, {data: payload});
        }
    }
    return React.createElement(
        "span",
        {
            onClick: handleClick,
            style: {
                color: "#2196F3",
                cursor: "pointer",
                textDecoration: "underline",
                fontSize: "12px",
            },
        },
        value.toLocaleString()
    );
};


/**
 * Payor name link for Insurance Rate Manager — clickable to drill down.
 * Writes to a hidden Store to trigger the detail panel callback.
 */
dagcomponentfuncs.PayorDrilldown = function (props) {
    var value = props.value;
    if (!value) {
        return React.createElement("span", {style: {color: "#9CA3AF"}}, "\u2014");
    }
    function handleClick(e) {
        e.stopPropagation();
        var data = props.data || {};
        var payload = {
            payor: data.payor || value,
            ts: Date.now(),
        };
        if (window.dash_clientside) {
            window.dash_clientside.set_props("billing-irm-drill-store", {data: payload});
        }
    }
    return React.createElement(
        "span",
        {
            onClick: handleClick,
            style: {
                color: "#7C2A83",
                cursor: "pointer",
                fontWeight: 500,
                fontSize: "13px",
            },
            title: "Click to view rate details",
        },
        value
    );
};


/**
 * Custom cell editor with autocomplete for institutions.
 * Shows an input with a filtered dropdown list below it.
 * Supports typing new values AND selecting from existing ones.
 */
dagcomponentfuncs.InstitutionEditor = function (props) {
    var ref = React.useRef(null);
    var _s = React.useState(props.value || "");
    var value = _s[0], setValue = _s[1];
    var _o = React.useState(true);
    var open = _o[0], setOpen = _o[1];

    // Gather all known institutions. Primary source: the institutions
    // catalog mirrored into window.__rpmInstitutions by the clientside
    // callback in pages/referrals.py (populated when the Institutions tab
    // grid loads). Fallback: scan provider-grid rows. The catalog includes
    // unassigned institutions; scanning grid rows misses those entirely.
    var allInstitutions = React.useMemo(function () {
        var fromCatalog = window.__rpmInstitutions;
        if (fromCatalog && fromCatalog.length) {
            return fromCatalog.slice().sort();
        }
        var insts = [];
        var seen = {};
        if (props.api) {
            props.api.forEachNode(function (node) {
                if (node.data && node.data.institution && !seen[node.data.institution]) {
                    seen[node.data.institution] = true;
                    insts.push(node.data.institution);
                }
            });
        }
        return insts.sort();
    }, []);

    // Filter by typed value
    var filtered = allInstitutions.filter(function (inst) {
        return inst.toLowerCase().indexOf(value.toLowerCase()) !== -1;
    });

    React.useEffect(function () {
        if (ref.current) { ref.current.focus(); ref.current.select(); }
    }, []);

    function commitValue(val) {
        setValue(val);
        setOpen(false);
        if (props.onValueChange) {
            props.onValueChange(val);
        }
        if (props.stopEditing) {
            setTimeout(function () { props.stopEditing(); }, 50);
        }
    }

    var containerStyle = {
        position: "relative",
        width: "100%",
        minWidth: "250px",
    };
    var inputStyle = {
        width: "100%",
        height: "36px",
        border: "2px solid #7C2A83",
        borderRadius: "4px",
        padding: "0 8px",
        fontSize: "13px",
        boxSizing: "border-box",
        outline: "none",
    };
    var dropdownStyle = {
        position: "absolute",
        top: "100%",
        left: 0,
        right: 0,
        maxHeight: "200px",
        overflowY: "auto",
        background: "#fff",
        border: "1px solid #dee2e6",
        borderRadius: "0 0 6px 6px",
        boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
        zIndex: 9999,
        display: open && filtered.length > 0 ? "block" : "none",
    };
    var itemStyle = {
        padding: "6px 10px",
        cursor: "pointer",
        fontSize: "13px",
    };

    function handleChange(e) {
        var v = e.target.value;
        setValue(v);
        setOpen(true);
        if (props.onValueChange) {
            props.onValueChange(v);
        }
    }

    return React.createElement("div", {style: containerStyle},
        React.createElement("input", {
            ref: ref,
            value: value,
            onChange: handleChange,
            onKeyDown: function (e) {
                if (e.key === "Enter") { commitValue(value); }
                else if (e.key === "Escape") { props.stopEditing(true); }
                else if (e.key === "Tab") { commitValue(value); }
            },
            style: inputStyle,
        }),
        React.createElement("div", {style: dropdownStyle},
            filtered.map(function (inst) {
                return React.createElement("div", {
                    key: inst,
                    onMouseDown: function (e) { e.preventDefault(); commitValue(inst); },
                    onMouseEnter: function (e) { e.target.style.background = "#f0e6f6"; },
                    onMouseLeave: function (e) { e.target.style.background = "#fff"; },
                    style: itemStyle,
                }, inst);
            })
        )
    );
};


// =========================================================================
// Payor Mapping components
// =========================================================================

/**
 * Colored pill badge for standardized payor names.
 * Shows "— unmapped —" when empty.  Includes × to clear.
 */
dagcomponentfuncs.PayorBadge = function (props) {
    var value = props.value || "";
    if (!value) {
        return React.createElement(
            "span",
            {
                style: {color: "#9CA3AF", fontSize: "12px", fontStyle: "italic", cursor: "pointer"},
                title: "Double-click to assign payor",
            },
            "\u2014 unmapped \u2014"
        );
    }
    var colors = [
        {bg: "#EDE9FE", text: "#6D28D9", x: "#A78BFA"},
        {bg: "#DBEAFE", text: "#1D4ED8", x: "#60A5FA"},
        {bg: "#D1FAE5", text: "#047857", x: "#34D399"},
        {bg: "#FEE2E2", text: "#B91C1C", x: "#F87171"},
        {bg: "#FEF3C7", text: "#92400E", x: "#FBBF24"},
        {bg: "#E0E7FF", text: "#3730A3", x: "#818CF8"},
        {bg: "#FCE7F3", text: "#9D174D", x: "#F472B6"},
        {bg: "#CCFBF1", text: "#0F766E", x: "#2DD4BF"},
    ];
    var hash = 0;
    for (var i = 0; i < value.length; i++) {
        hash = ((hash << 5) - hash + value.charCodeAt(i)) | 0;
    }
    var c = colors[Math.abs(hash) % colors.length];

    function clearPayor(e) {
        e.stopPropagation();
        var updated = Object.assign({}, props.data, {standardized_payor: ""});
        props.setData(updated);
    }

    return React.createElement(
        "div",
        {style: {display: "flex", alignItems: "center", height: "100%", gap: "0px", minWidth: 0}},
        React.createElement(
            "span",
            {
                style: {
                    background: c.bg, color: c.text,
                    padding: "1px 6px 1px 10px", borderRadius: "12px",
                    fontSize: "12px", fontWeight: 600, lineHeight: "22px",
                    display: "inline-flex", alignItems: "center", gap: "0px",
                    maxWidth: "100%", minWidth: 0,
                },
            },
            React.createElement("span", {
                style: {overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0},
            }, value),
            React.createElement("span", {
                onClick: clearPayor,
                style: {
                    cursor: "pointer", color: c.x, fontSize: "14px", fontWeight: "bold",
                    lineHeight: 1, marginLeft: "4px", opacity: 0.7, flexShrink: 0,
                },
                title: "Clear payor mapping",
                onMouseEnter: function(e) { e.target.style.opacity = 1; },
                onMouseLeave: function(e) { e.target.style.opacity = 0.7; },
            }, "\u00d7")
        )
    );
};


/**
 * Colored pill for broad payor category with deterministic colors.
 */
dagcomponentfuncs.BroadCategoryBadge = function (props) {
    var value = props.value || "";
    var colorMap = {
        "Medicare": {bg: "#DBEAFE", text: "#1D4ED8"},
        "Medicaid": {bg: "#D1FAE5", text: "#047857"},
        "Private": {bg: "#FEF3C7", text: "#92400E"},
        "Military/VA": {bg: "#EDE9FE", text: "#6D28D9"},
        "Workers Comp": {bg: "#CCFBF1", text: "#0F766E"},
        "Tribal/IHS": {bg: "#F3E8FF", text: "#7C2D12"},
        "Self Pay": {bg: "#FEE2E2", text: "#B91C1C"},
        "Other/Unknown": {bg: "#F3F4F6", text: "#6B7280"},
    };
    var c = colorMap[value] || colorMap["Other/Unknown"];
    if (!value) {
        return React.createElement("span", {style: {color: "#9CA3AF", fontSize: "12px"}}, "\u2013");
    }
    return React.createElement(
        "div",
        {style: {display: "flex", alignItems: "center", height: "100%"}},
        React.createElement("span", {
            style: {
                background: c.bg, color: c.text,
                padding: "1px 10px", borderRadius: "12px",
                fontSize: "12px", fontWeight: 600, lineHeight: "22px",
                whiteSpace: "nowrap",
            },
        }, value)
    );
};


/**
 * Autocomplete editor for standardized payor names.
 * Canonical payor list passed via cellEditorParams.values.
 */
dagcomponentfuncs.PayorMappingEditor = function (props) {
    var ref = React.useRef(null);
    var _s = React.useState(props.value || "");
    var value = _s[0], setValue = _s[1];
    var _o = React.useState(true);
    var open = _o[0], setOpen = _o[1];

    // Get canonical payors from cellEditorParams or fall back to grid values
    var allPayors = React.useMemo(function () {
        if (props.colDef && props.colDef.cellEditorParams && props.colDef.cellEditorParams.values) {
            return props.colDef.cellEditorParams.values.slice().sort();
        }
        var payors = [];
        var seen = {};
        if (props.api) {
            props.api.forEachNode(function (node) {
                var p = node.data && node.data.standardized_payor;
                if (p && !seen[p]) { seen[p] = true; payors.push(p); }
            });
        }
        return payors.sort();
    }, []);

    var filtered = allPayors.filter(function (p) {
        return p.toLowerCase().indexOf(value.toLowerCase()) !== -1;
    });

    React.useEffect(function () {
        if (ref.current) { ref.current.focus(); ref.current.select(); }
    }, []);

    function commitValue(val) {
        setValue(val);
        setOpen(false);
        if (props.onValueChange) { props.onValueChange(val); }
        if (props.stopEditing) { setTimeout(function () { props.stopEditing(); }, 50); }
    }

    return React.createElement("div", {
        style: {position: "relative", width: "100%", minWidth: "250px"},
    },
        React.createElement("input", {
            ref: ref, value: value,
            onChange: function (e) { setValue(e.target.value); setOpen(true);
                if (props.onValueChange) { props.onValueChange(e.target.value); } },
            onKeyDown: function (e) {
                if (e.key === "Enter") { commitValue(value); }
                else if (e.key === "Escape") { props.stopEditing(true); }
                else if (e.key === "Tab") { commitValue(value); }
            },
            style: {
                width: "100%", height: "36px", border: "2px solid #7C2A83",
                borderRadius: "4px", padding: "0 8px", fontSize: "13px",
                boxSizing: "border-box", outline: "none",
            },
        }),
        React.createElement("div", {
            style: {
                position: "absolute", top: "100%", left: 0, right: 0,
                maxHeight: "400px", overflowY: "auto", background: "#fff",
                border: "1px solid #dee2e6", borderRadius: "0 0 6px 6px",
                boxShadow: "0 4px 12px rgba(0,0,0,0.15)", zIndex: 9999,
                display: open && filtered.length > 0 ? "block" : "none",
            },
        },
            filtered.map(function (p) {
                return React.createElement("div", {
                    key: p,
                    onMouseDown: function (e) { e.preventDefault(); commitValue(p); },
                    onMouseEnter: function (e) { e.target.style.background = "#f0e6f6"; },
                    onMouseLeave: function (e) { e.target.style.background = "#fff"; },
                    style: {padding: "6px 10px", cursor: "pointer", fontSize: "13px"},
                }, p);
            })
        )
    );
};


/**
 * Raw insurance name with Google search icon.
 */
dagcomponentfuncs.RawInsuranceSearch = function (props) {
    var name = props.value || "";
    if (!name) {
        return React.createElement("span", {style: {color: "#9CA3AF"}}, "\u2014");
    }
    var searchUrl = "https://www.google.com/search?q=" + encodeURIComponent(name + " insurance");
    return React.createElement(
        "div",
        {style: {display: "flex", alignItems: "center", height: "100%", gap: "4px", minWidth: 0}},
        React.createElement(
            "span",
            {style: {overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0, flex: 1, fontSize: "12px"}},
            name
        ),
        React.createElement(
            "a",
            {
                href: searchUrl,
                target: "_blank",
                rel: "noopener",
                style: {color: "#6B7280", textDecoration: "none", fontSize: "13px", flexShrink: 0, opacity: 0.6},
                title: "Google: " + name,
                onMouseEnter: function(e) { e.target.style.opacity = 1; },
                onMouseLeave: function(e) { e.target.style.opacity = 0.6; },
            },
            "\uD83D\uDD0D"
        )
    );
};


/**
 * Delete button for payor entity management grid.
 */
dagcomponentfuncs.PayorEntityDelete = function (props) {
    function handleDelete(e) {
        e.stopPropagation();
        var data = Object.assign({}, props.data, {_action: "delete"});
        props.setData(data);
    }
    return React.createElement(
        "div",
        {style: {display: "flex", alignItems: "center", justifyContent: "center", height: "100%"}},
        React.createElement(
            "button",
            {
                onClick: handleDelete,
                style: {
                    background: "transparent",
                    border: "1px solid #E5E7EB",
                    borderRadius: "4px",
                    color: "#9CA3AF",
                    cursor: "pointer",
                    fontSize: "11px",
                    padding: "1px 8px",
                    lineHeight: "20px",
                },
                title: "Delete payor (clears from all mappings)",
                onMouseEnter: function(e) { e.target.style.color = "#EF4444"; e.target.style.borderColor = "#EF4444"; },
                onMouseLeave: function(e) { e.target.style.color = "#9CA3AF"; e.target.style.borderColor = "#E5E7EB"; },
            },
            "Delete"
        )
    );
};


/**
 * Sim Timing — one appointment drawn as a compact timeline strip.
 *
 * Used by the Timelines view of the Simulation Timing detail table. Every row
 * shares one axis (cellRendererParams lo/hi, minutes from each appointment's
 * own booked start), so the strips line up and read as a stack. Row data
 * carries TL = {m: {milestone: minutes}, b: booked length, r: CT clock
 * reliable}. The pinned top row ({_axis: true}) draws the tick labels so the
 * scale stays visible while scrolling. Colours match the timeline chart in
 * assets/sim_timing.js.
 */
dagcomponentfuncs.SimTimelineStrip = function (props) {
    var h = React.createElement;
    var lo = Number(props.lo), hi = Number(props.hi);
    var span = hi - lo;
    if (!(span > 0)) return null;

    var isDark = document.documentElement.getAttribute("data-theme") === "dark";
    var muted = isDark ? "#9BA1AE" : "#6B7280";
    var gridCol = isDark ? "rgba(155,161,174,0.20)" : "rgba(107,114,128,0.16)";
    var zeroCol = isDark ? "#4B5060" : "#C4C8CF";

    function frac(v) {
        return (Math.max(lo, Math.min(hi, v)) - lo) / span;
    }
    function pct(v) { return (frac(v) * 100).toFixed(2) + "%"; }

    var step = span > 300 ? 60 : 30;
    var ticks = [];
    for (var t = Math.ceil(lo / step) * step; t <= hi; t += step) ticks.push(t);

    // Pinned axis row: tick labels only.
    if (props.data && props.data._axis) {
        return h("svg", {width: "100%", height: "100%", style: {display: "block", overflow: "visible"}},
            ticks.map(function (tk) {
                var f = frac(tk);
                var anchor = f < 0.03 ? "start" : (f > 0.97 ? "end" : "middle");
                return h("text", {
                    key: tk, x: pct(tk), y: "65%", textAnchor: anchor,
                    fontSize: 10, fill: muted,
                    fontWeight: tk === 0 ? 600 : 400,
                }, tk === 0 ? "0" : (tk > 0 ? "+" + tk : String(tk)));
            })
        );
    }

    var tl = props.data && props.data.TL;
    if (!tl || !tl.m) return null;

    var COLORS = {
        sched_start: "#9CA3AF", checkin: "#2196F3", ct_first: "#7C2A83",
        ct_done: "#7C2A83", note: "#4CAF50", appt_end: "#F44336",
        sched_end: "#9CA3AF"
    };
    var LABELS = {
        sched_start: "Scheduled Start", checkin: "Check-In",
        ct_first: "CT First Series", ct_done: "CT Complete",
        note: "Note Entered", appt_end: "Appointment End",
        sched_end: "Scheduled End"
    };
    // Booked-slot markers first so the real events sit on top of them.
    var ORDER = ["sched_start", "sched_end", "checkin", "ct_first",
                 "ct_done", "note", "appt_end"];

    var kids = [];
    ticks.forEach(function (tk) {
        kids.push(h("line", {
            key: "g" + tk, x1: pct(tk), x2: pct(tk), y1: "8%", y2: "92%",
            stroke: tk === 0 ? zeroCol : gridCol, strokeWidth: 1,
        }));
    });
    if (tl.b) {
        var x0 = Math.max(lo, 0), x1 = Math.min(hi, tl.b);
        if (x1 > x0) {
            kids.push(h("rect", {
                key: "band", x: pct(x0), width: ((x1 - x0) / span * 100).toFixed(2) + "%",
                y: "24%", height: "52%", rx: 2,
                fill: isDark ? "rgba(124,42,131,0.24)" : "rgba(124,42,131,0.10)",
            }));
        }
    }
    ORDER.forEach(function (k) {
        var v = tl.m[k];
        if (v === undefined || v === null) return;
        var off = v < lo || v > hi;
        var hollow = (k === "ct_first" || k === "ct_done") && !tl.r;
        var tip = LABELS[k] + ": " + (v > 0 ? "+" : "") + Math.round(v) + " min"
            + (hollow ? " (CT clock corrected)" : "")
            + (off ? " (beyond axis)" : "");
        kids.push(h("circle", {
            key: k, cx: pct(v), cy: "50%", r: 4.5,
            fill: hollow ? "none" : COLORS[k],
            stroke: COLORS[k], strokeWidth: 1.5,
            opacity: off ? 0.45 : 1,
        }, h("title", null, tip)));
    });
    return h("svg", {width: "100%", height: "100%", style: {display: "block"}}, kids);
};
