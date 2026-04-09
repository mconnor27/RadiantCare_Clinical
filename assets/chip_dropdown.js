// ─── Chip Dropdown Toggle (click-to-open, click-outside-to-close) ────────
// Shared across all pages. Auto-discovers trigger/panel pairs by convention:
//   trigger button: any element with ID ending in "-trigger"
//   panel:          sibling element with class "wf-chip-dropdown"
// Both must share a common wrapper div with style="display: inline-block".
(function() {
    function findPairs() {
        var panels = document.querySelectorAll(".wf-chip-dropdown");
        var pairs = [];
        panels.forEach(function(panel) {
            var wrapper = panel.closest("[style*='inline-block']");
            if (!wrapper) return;
            var btn = wrapper.querySelector("[id$='-trigger']");
            if (!btn) return;
            pairs.push([btn, panel]);
        });
        return pairs;
    }

    function closeAll(exceptPanel) {
        findPairs().forEach(function(p) {
            if (p[1] !== exceptPanel) p[1].style.display = "none";
        });
        // Also close any open subcategory side panels
        document.querySelectorAll(".wf-subcat-panel").forEach(function(sp) {
            if (sp !== exceptPanel) sp.style.display = "none";
        });
    }

    var _clearInProgress = false;
    document.addEventListener("click", function(e) {
        // Handle clear buttons: stop propagation so trigger button doesn't fire,
        // and programmatically clear the associated chip group inputs
        var clearBtn = e.target.closest && e.target.closest(".wf-filter-clear-btn");
        if (clearBtn && !_clearInProgress) {
            e.stopPropagation();
            e.preventDefault();
            closeAll();
            // Find the sibling chip-dropdown panel and deselect all checked chips
            var wrapper = clearBtn.closest("[style*='inline-block']");
            if (wrapper) {
                // Clear both category and subcategory panels
                wrapper.querySelectorAll(".wf-chip-dropdown, .wf-subcat-panel").forEach(function(panel) {
                    panel.querySelectorAll("input[type='radio']:checked, input[type='checkbox']:checked").forEach(function(inp) {
                        inp.click();  // deselect via native click so React state updates
                    });
                });
            }
            // Re-dispatch so Dash sees the n_clicks increment (with guard to avoid loop)
            _clearInProgress = true;
            setTimeout(function() {
                clearBtn.dispatchEvent(new MouseEvent("click", {bubbles: true}));
                _clearInProgress = false;
            }, 0);
            return;
        }
        // Check if click is on a trigger button
        var pairs = findPairs();
        for (var i = 0; i < pairs.length; i++) {
            var btn = pairs[i][0];
            var panel = pairs[i][1];
            if (btn.contains(e.target)) {
                var open = panel.style.display !== "none";
                closeAll();  // close everything first
                panel.style.display = open ? "none" : "block";
                return;
            }
        }
        // Check if click is inside an open panel (keep it open)
        for (var j = 0; j < pairs.length; j++) {
            if (pairs[j][1].contains(e.target)) return;
        }
        // Also check subcategory side panels
        var subcatPanels = document.querySelectorAll(".wf-subcat-panel");
        for (var k = 0; k < subcatPanels.length; k++) {
            if (subcatPanels[k].contains(e.target)) return;
        }
        // Click outside — close all
        closeAll();
    });
})();


// ---------------------------------------------------------------------------
// Filter cross-check: hide chips whose values aren't available in the data
// ---------------------------------------------------------------------------
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.filterSync = {
    /**
     * applyFilterOptions: reads a filter-options store and hides
     * chip elements that are not in the available options set.
     * Returns a dummy value (written to a hidden div).
     */
    applyFilterOptions: function(options) {
        if (!options) return "";

        // Support multiple pages via _prefix key (default: "workflow" for backward compat)
        var prefix = options._prefix || "workflow";
        var configs = [
            {groupId: prefix + "-filter-department", key: "departments"},
            {groupId: prefix + "-filter-physician",  key: "physicians"},
            {groupId: prefix + "-filter-technique",  key: "techniques"},
            // bodySystems: categories are now accordion items, not chips — no cross-filter needed
            {groupId: prefix + "-filter-subcategory", key: "subcategories"}
        ];

        configs.forEach(function(cfg) {
            var available = new Set(options[cfg.key] || []);
            var group = document.getElementById(cfg.groupId);
            if (!group) return;

            // DMC Chips render as wrapper divs containing an <input> + <label>
            var chips = group.querySelectorAll(
                '[class*="Chip-root"], [class*="chip-root"]'
            );
            if (chips.length === 0) {
                // Fallback: try label elements directly
                chips = group.querySelectorAll("label");
            }
            chips.forEach(function(chip) {
                var input = chip.querySelector("input");
                if (!input) return;
                var val = input.value;
                if (available.size === 0 || available.has(val)) {
                    chip.style.display = "";
                    chip.style.opacity = "";
                    chip.style.pointerEvents = "";
                } else {
                    chip.style.display = "none";
                }
            });
        });

        return "";
    }
};
