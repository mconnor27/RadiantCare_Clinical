// ─── Compact MultiSelect (Referrals Provider filter) ─────────────────────
// Pure functions for use by Dash clientside callbacks. NO DOM observation —
// these only react to MultiSelect value changes via Dash's normal callback
// dispatch (much more reliable than a MutationObserver against Mantine's
// internal rerenders).
//
// Used by referrals.py via:
//   ClientsideFunction(namespace="providerCompact", function_name="wrapClass")
//   ClientsideFunction(namespace="providerCompact", function_name="badge")
window.dash_clientside = window.dash_clientside || {};

window.dash_clientside.providerCompact = {
    // Append " many" to the wrapper className when >= 2 picked, so CSS in
    // custom.css can hide individual pills under that state.
    wrapClass: function(vals) {
        var base = "rc-compact-multi-wrap";
        if (!vals || vals.length === 0) return base;
        if (vals.length >= 2) return base + " has-selection many";
        return base + " has-selection";
    },

    // Return [text, style] for the count badge. Hidden unless >= 2 picked.
    badge: function(vals) {
        if (!vals || vals.length < 2) {
            return ["", {display: "none"}];
        }
        // Badge spans from left padding to where the chevron+clear icons
        // sit, with justify-content center keeping the count text neatly
        // centered. Opaque background ensures the search field placeholder
        // ("All Providers") behind it can't peek through at either edge.
        return [
            vals.length + " selected",
            {
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                position: "absolute",
                left: "6px",
                right: "56px",
                top: "50%",
                transform: "translateY(-50%)",
                height: "26px",
                padding: "0 10px",
                background: "#ede9fe",
                color: "#6d28d9",
                borderRadius: "999px",
                fontSize: "12px",
                fontWeight: 500,
                pointerEvents: "none",
                zIndex: 2,
                whiteSpace: "nowrap"
            }
        ];
    }
};
