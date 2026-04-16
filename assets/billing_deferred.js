/**
 * billing_deferred.js — Staggered chart rendering for the Billing page.
 *
 * Problem: When 8 stores land simultaneously, 8 clientside callbacks fire and
 * each calls Plotly.react in the same frame, blocking the main thread for
 * 500-1000 ms.
 *
 * Solution:
 *   1. Each callback computes the figure but does NOT return it to Dash.
 *   2. Instead it pushes the figure to a per-chart render map.
 *   3. A requestAnimationFrame loop processes ONE chart per frame.
 *   4. IntersectionObserver defers off-screen charts until they scroll into view.
 *   5. Rapid updates (smoothing slider drag) are coalesced — only the latest
 *      pending figure per chart is rendered.
 *
 * All callbacks return `no_update` so Dash never touches the figure property.
 * Chart export uses DOM (Plotly.downloadImage on .js-plotly-plot), so it
 * always gets the actually-rendered chart regardless.
 */
(function () {
    "use strict";

    /* ---- render queue -------------------------------------------------- */
    var pending  = {};      // chartId → figure (latest wins)
    var running  = false;

    function drain() {
        var ids = Object.keys(pending);
        if (ids.length === 0) { running = false; return; }

        var id  = ids[0];
        var fig = pending[id];
        delete pending[id];

        var el     = document.getElementById(id);
        var plotEl = el && el.querySelector(".js-plotly-plot");
        if (plotEl && typeof Plotly !== "undefined") {
            Plotly.react(plotEl, fig.data, fig.layout, fig.config || {});
        }

        // next chart on the next frame — yields to paint between each
        requestAnimationFrame(drain);
    }

    function enqueue(chartId, fig) {
        pending[chartId] = fig;   // coalesce: latest always wins
        if (!running) {
            running = true;
            requestAnimationFrame(drain);
        }
    }

    /* ---- IntersectionObserver for below-fold charts -------------------- */
    var isVisible    = {};  // chartId → boolean
    var deferredFigs = {};  // chartId → figure waiting for visibility

    var observer = null;
    var observed = {};

    function onIntersect(entries) {
        entries.forEach(function (entry) {
            var id = entry.target.id;
            isVisible[id] = entry.isIntersecting;
            if (entry.isIntersecting && deferredFigs[id]) {
                enqueue(id, deferredFigs[id]);
                delete deferredFigs[id];
            }
        });
    }

    function ensureObserved(chartId) {
        if (observed[chartId]) return;
        if (!observer) {
            if (typeof IntersectionObserver === "undefined") return;
            observer = new IntersectionObserver(onIntersect, { rootMargin: "300px" });
        }
        var el = document.getElementById(chartId);
        if (el) {
            observer.observe(el);
            observed[chartId] = true;
            // First time: assume visible until observer fires
            if (isVisible[chartId] === undefined) isVisible[chartId] = true;
        }
    }

    /**
     * Schedule a figure for rendering.
     *  - If chart is visible (or observer hasn't reported yet), enqueue for
     *    staggered rAF render.
     *  - If chart is off-screen, stash figure and render when it scrolls in.
     */
    function scheduleRender(chartId, fig) {
        if (!fig || fig === window.dash_clientside.no_update) return;
        ensureObserved(chartId);
        if (isVisible[chartId] === false) {
            deferredFigs[chartId] = fig;
        } else {
            enqueue(chartId, fig);
        }
    }

    /* ---- public API ---------------------------------------------------- */
    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.billingDeferred = {

        /**
         * Staggered trend chart (volume / wRVU / dollar).
         * Replaces the old inline _SLICE_AGG_JS.
         */
        renderTrend: function (chartId, storeData, sliceMode, agg,
                               smoothPct, chartType, stackVal) {
            if (!storeData) return window.dash_clientside.no_update;
            var slice = storeData[sliceMode || "category"];
            if (!slice) return window.dash_clientside.no_update;
            var raw = slice[agg || "M"];
            if (!raw) return window.dash_clientside.no_update;

            var fig = window.dash_clientside.census.smoothChartWithType(
                raw, smoothPct, chartType, null, stackVal
            );
            if (fig && fig.layout && fig.layout.margin) fig.layout.margin.l = 36;
            scheduleRender(chartId, fig);
            return window.dash_clientside.no_update;
        },

        /**
         * Staggered cumulative chart (volume / wRVU / dollar).
         * Replaces the old inline _CUM_JS.
         */
        renderCum: function (chartId, rawData, smoothPct, chartType,
                             stackVal, maxPrior) {
            if (!rawData) return window.dash_clientside.no_update;

            var fig = window.dash_clientside.cumulative.renderCumulative(
                rawData, smoothPct, chartType, null, stackVal, maxPrior
            );
            if (fig && fig.layout && fig.layout.margin) fig.layout.margin.l = 36;
            scheduleRender(chartId, fig);
            return window.dash_clientside.no_update;
        },

        /**
         * Staggered payor horizontal bar chart.
         * Replaces the old inline _PAYOR_BAR_JS.
         */
        renderPayor: function (chartId, storeData, mode, unit) {
            if (!storeData) return window.dash_clientside.no_update;
            var d = storeData[mode] || storeData["actual"];
            if (!d || !d.labels || d.labels.length === 0) {
                var empty = {
                    data: [],
                    layout: Object.assign({}, window.dmc_default_layout || {}, {
                        xaxis: { visible: false }, yaxis: { visible: false },
                        annotations: [{ text: "No payor data", xref: "paper", yref: "paper",
                            x: 0.5, y: 0.5, showarrow: false,
                            font: { size: 14, color: "#9CA3AF" } }],
                        height: 300, margin: { l: 40, r: 20, t: 8, b: 2 }
                    })
                };
                scheduleRender(chartId, empty);
                return window.dash_clientside.no_update;
            }

            var labels    = d.labels.slice().reverse();
            var rawValues = d.values.slice().reverse();
            var colors    = d.colors.slice().reverse();
            var isPct     = unit === "pct";
            var total     = 0;
            for (var i = 0; i < rawValues.length; i++) total += rawValues[i];
            var values = isPct
                ? rawValues.map(function (v) { return total > 0 ? v / total * 100 : 0; })
                : rawValues;
            var hoverFmt = isPct
                ? "%{y}: %{x:.1f}%<extra></extra>"
                : "%{y}: %{x:,}<extra></extra>";
            var textVals = isPct
                ? values.map(function (v) { return v.toFixed(1) + "%"; })
                : null;

            var fig = {
                data: [{
                    y: labels, x: values, orientation: "h", type: "bar",
                    marker: { color: colors },
                    text: textVals,
                    textposition: isPct ? "outside" : "none",
                    cliponaxis: false,
                    hovertemplate: hoverFmt
                }],
                layout: Object.assign({}, window.dmc_default_layout || {}, {
                    height: 380,
                    margin: { l: 8, r: 16, t: 8, b: 18 },
                    xaxis: {
                        title: { text: "" },
                        showgrid: true, gridcolor: "#F0F0F0",
                        ticksuffix: isPct ? "%" : ""
                    },
                    yaxis: { showgrid: false, automargin: true, ticksuffix: "  " }
                })
            };
            scheduleRender(chartId, fig);
            return window.dash_clientside.no_update;
        }
    };
})();
