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
    var npi = props.value || "";
    if (!npi) {
        return React.createElement("span", {style: {color: "#9CA3AF"}}, "—");
    }
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

    var _React = React;
    var copied = _React.useState(false);
    var isCopied = copied[0];
    var setCopied = copied[1];

    function handleCopy(e) {
        e.stopPropagation();
        navigator.clipboard.writeText(value).then(function () {
            setCopied(true);
            setTimeout(function () { setCopied(false); }, 1500);
        });
    }

    var searchUrl = "https://www.google.com/search?q=" + encodeURIComponent(value);

    return _React.createElement(
        "div",
        {style: {display: "flex", alignItems: "center", height: "100%", gap: "3px", overflow: "hidden"}},
        _React.createElement(
            "span",
            {
                onClick: handleCopy,
                title: isCopied ? "Copied!" : "Click to copy",
                style: {
                    fontSize: "12px",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    flex: 1,
                    cursor: "pointer",
                },
            },
            isCopied ? "\u2705 Copied" : value
        ),
        _React.createElement(
            "a",
            {href: searchUrl, target: "_blank", rel: "noopener",
             style: {color: "#6B7280", textDecoration: "none", fontSize: "13px"},
             title: "Google Search"},
            "\ud83d\udd0d"
        )
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
        props.setData(Object.assign({}, data, { _action: action }));
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

    // Gather all unique institutions from the grid
    var allInstitutions = React.useMemo(function () {
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
