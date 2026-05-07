/**
 * Shared date-slider helpers for filter bars.
 * A single MutationObserver rewrites slider thumb labels from raw
 * month-index integers to "Mon YYYY" strings, for all registered
 * date-slider IDs.
 *
 * Usage (Python):
 *   ClientsideFunction(namespace="cvDateSlider", function_name="syncSlider")
 *
 * Depends on: nothing (standalone).
 */

(function() {
    "use strict";

    var MO = ["Jan","Feb","Mar","Apr","May","Jun",
              "Jul","Aug","Sep","Oct","Nov","Dec"];

    // Registry: sliderId -> formatter fn(n) -> string
    var formatters = {};

    function makeIdxFormatter(baseYear) {
        return function(idx) {
            return MO[idx % 12] + " " + (baseYear + Math.floor(idx / 12));
        };
    }

    // Use a WeakMap to remember which slider each label belongs to
    // so we don't re-walk the DOM on every tick.
    var labelToFmt = new WeakMap();

    function findFormatterForLabel(lbl) {
        // Walk up ancestors looking for an element whose id is registered.
        var node = lbl.parentElement;
        while (node && node !== document.body) {
            if (node.id && formatters[node.id]) return formatters[node.id];
            node = node.parentElement;
        }
        return null;
    }

    // Rewrite a single slider label in-place. Idempotent: a label whose
    // textContent is already non-numeric (already rewritten, or a label
    // we don't manage) is left alone — that's also what stops the
    // observer's own characterData mutations from looping.
    function rewriteLabel(lbl) {
        if (!lbl) return;
        var raw = lbl.textContent;
        var n = parseInt(raw, 10);
        if (isNaN(n) || String(n) !== raw.trim()) return;

        var fmt = labelToFmt.get(lbl);
        if (!fmt) {
            fmt = findFormatterForLabel(lbl);
            if (!fmt) return;
            labelToFmt.set(lbl, fmt);
        }
        var next = fmt(n);
        if (next !== raw) lbl.textContent = next;
    }

    var LABEL_SELECTOR = '.mantine-Slider-label, [class*="Slider-label"]';

    function rewriteLabels() {
        var labels = document.querySelectorAll(LABEL_SELECTOR);
        for (var i = 0; i < labels.length; i++) rewriteLabel(labels[i]);
    }

    // Synchronous, scoped rewrite directly inside the MutationObserver
    // callback (no rAF coalesce). MutationObserver callbacks run as
    // microtasks, which drain before the next browser paint — so the
    // raw integer never gets a chance to render. We narrow the work by
    // only inspecting labels actually involved in this mutation batch
    // (added nodes, or characterData updates whose parent is a label),
    // not the full document.
    var observer = new MutationObserver(function(mutations) {
        for (var mi = 0; mi < mutations.length; mi++) {
            var m = mutations[mi];
            if (m.type === "childList") {
                for (var ai = 0; ai < m.addedNodes.length; ai++) {
                    var node = m.addedNodes[ai];
                    if (!node || node.nodeType !== 1) continue;
                    if (node.matches && node.matches(LABEL_SELECTOR)) {
                        rewriteLabel(node);
                    }
                    if (node.querySelectorAll) {
                        var inner = node.querySelectorAll(LABEL_SELECTOR);
                        for (var ii = 0; ii < inner.length; ii++) rewriteLabel(inner[ii]);
                    }
                }
            } else if (m.type === "characterData") {
                // Slider drags update label textContent in place — caught
                // here. Our own rewrites also fire characterData, but
                // rewriteLabel skips non-numeric content so it no-ops.
                var parent = m.target && m.target.parentElement;
                if (parent && parent.matches && parent.matches(LABEL_SELECTOR)) {
                    rewriteLabel(parent);
                }
            }
        }
    });

    function startObserver() {
        // childList for label appearance, characterData for in-place text
        // updates during slider drags (DMC rewrites the same label node).
        observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true
        });
        rewriteLabels();
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", startObserver);
    } else {
        startObserver();
    }
    // Safety-net poll for timing races when assets load after
    // DOMContentLoaded. 1s is plenty — the observer catches real changes.
    setInterval(rewriteLabels, 1000);

    function registerSlider(namespaceName, baseYear, sliderIds) {
        var fmtIdx = makeIdxFormatter(baseYear);
        sliderIds.forEach(function(sid) { formatters[sid] = fmtIdx; });

        window.dash_clientside = window.dash_clientside || {};
        window.dash_clientside[namespaceName] = {
            syncSlider: function(sliderVal, curStart, curEnd) {
                if (!sliderVal || sliderVal.length !== 2) {
                    return [window.dash_clientside.no_update,
                            window.dash_clientside.no_update, ""];
                }
                var label = fmtIdx(sliderVal[0]) + "  \u2014  " + fmtIdx(sliderVal[1]);

                var sYear = baseYear + Math.floor(sliderVal[0] / 12);
                var sMonth = sliderVal[0] % 12 + 1;
                var startDate = sYear + "-" + String(sMonth).padStart(2, "0") + "-01";

                var eYear = baseYear + Math.floor(sliderVal[1] / 12);
                var eMonth = sliderVal[1] % 12 + 1;
                var lastDay = new Date(eYear, eMonth, 0).getDate();
                var endDate = eYear + "-" + String(eMonth).padStart(2, "0") + "-"
                            + String(lastDay).padStart(2, "0");

                var today = new Date();
                var todayStr = today.getFullYear() + "-"
                    + String(today.getMonth() + 1).padStart(2, "0") + "-"
                    + String(today.getDate()).padStart(2, "0");
                if (endDate > todayStr) { endDate = todayStr; }

                // If current start date is not the 1st of a month, a preset
                // callback set exact dates — preserve them, just update label.
                if (curStart && curStart.slice(8, 10) !== "01") {
                    return [window.dash_clientside.no_update,
                            window.dash_clientside.no_update, label];
                }

                if (curStart === startDate && curEnd === endDate) {
                    return [window.dash_clientside.no_update,
                            window.dash_clientside.no_update, label];
                }
                return [startDate, endDate, label];
            }
        };
    }

    // ── Page registrations ───────────────────────────────────────────────
    registerSlider("cvDateSlider",        2004, ["cv-date-slider"]);
    registerSlider("simDateSlider",       2004, ["sim-date-slider"]);
    registerSlider("tasksDateSlider",     2004, ["tasks-date-slider"]);
    registerSlider("otvsDateSlider",      2004, ["otvs-date-slider"]);
    registerSlider("coursesDateSlider",   2004, ["courses-date-slider"]);
    registerSlider("plansDateSlider",     2004, ["plans-date-slider"]);
    registerSlider("machinesDateSlider",  2004, ["machines-date-slider"]);
    registerSlider("proceduresDateSlider", 2004, ["proc-date-slider"]);
    registerSlider("physDateSlider",      2004, ["phys-date-slider"]);
    registerSlider("billingDateSlider",   2004, ["billing-date-slider"]);
    registerSlider("cptDateSlider",       2004, ["cpt-date-slider"]);
    registerSlider("patientsDateSlider",  2004, ["patients-date-slider"]);
    registerSlider("diagDateSlider",      2004, ["diag-date-slider"]);
    registerSlider("referralsDateSlider", 2004, ["referrals-date-slider"]);
    registerSlider("txDateSlider",        2004, ["tx-date-slider"]);

    // Also rewrite workflow sliders (no clientside callback registration needed)
    // — labels alone are handled via the shared registry.
    ["wf-date-slider", "wf-b-date-slider"].forEach(function(sid) {
        formatters[sid] = makeIdxFormatter(2004);
    });

    // Expose factory for future pages
    window._registerDateSlider = registerSlider;

    // ── Physicians after-hours slider: 0-48 scale (half-hour ticks) ───
    function fmtHalfHour(tick) {
        var totalMin = tick * 30;
        var h = Math.floor(totalMin / 60);
        var m = totalMin % 60;
        var suffix = h < 12 || h === 24 ? "AM" : "PM";
        var h12 = h % 12 || 12;
        return h12 + ":" + String(m).padStart(2, "0") + " " + suffix;
    }
    formatters["phys-ah-hours"] = fmtHalfHour;

})();
