/**
 * billing_deferred.js — Staggered chart rendering for the Billing page.
 *
 * Problem: When 6+ stores land simultaneously, clientside callbacks fire and
 * Plotly renders all charts in the same frame, blocking the main thread.
 *
 * Solution — two-path rendering:
 *
 *   FIRST RENDER (page load / navigate back):
 *     Return a sized empty placeholder to Dash so it creates the Plotly element
 *     without rendering any traces. The real figure goes to the rAF queue and
 *     renders one chart per frame.
 *
 *   SUBSEQUENT UPDATES (filter change / slider drag):
 *     Return no_update to Dash. The real figure goes to the rAF queue.
 *     No flash because the old chart stays visible until replaced.
 *
 *   BELOW-FOLD CHARTS:
 *     IntersectionObserver defers rendering until the chart scrolls into view.
 *
 *   RAPID UPDATES (smoothing slider drag):
 *     Coalesced — only the latest pending figure per chart is rendered.
 */
(function () {
    "use strict";

    window.dash_clientside = window.dash_clientside || {};
    var NO = window.dash_clientside.no_update;

    /* ---- render queue -------------------------------------------------- */
    var pending = {};      // chartId → figure (latest wins)
    var running = false;

    function drain() {
        var ids = Object.keys(pending);
        if (ids.length === 0) { running = false; return; }

        var id  = ids[0];
        var fig = pending[id];
        delete pending[id];

        var el = document.getElementById(id);
        if (el && typeof Plotly !== "undefined") {
            var plotEl = el.querySelector(".js-plotly-plot");
            if (plotEl) {
                Plotly.react(plotEl, fig.data, fig.layout, {displayModeBar: false});
            } else {
                // First render — create Plotly element inside dcc.Graph wrapper
                var target = el.querySelector(".dash-graph") || el;
                Plotly.newPlot(target, fig.data, fig.layout, {displayModeBar: false, responsive: true});
            }
        }

        requestAnimationFrame(drain);
    }

    function enqueue(chartId, fig) {
        pending[chartId] = fig;
        if (!running) {
            running = true;
            requestAnimationFrame(drain);
        }
    }

    /* ---- IntersectionObserver for below-fold charts -------------------- */
    var isVisible    = {};
    var deferredFigs = {};

    var observer = null;
    var observed = {};      // chartId → DOM element reference

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
        var el = document.getElementById(chartId);
        if (!el) return;
        if (observed[chartId] && observed[chartId] !== el) {
            if (observer) observer.unobserve(observed[chartId]);
            delete observed[chartId];
            delete isVisible[chartId];
        }
        if (observed[chartId]) return;
        if (!observer) {
            if (typeof IntersectionObserver === "undefined") return;
            observer = new IntersectionObserver(onIntersect, { rootMargin: "300px" });
        }
        observer.observe(el);
        observed[chartId] = el;
    }

    function hasExistingPlot(chartId) {
        var el = document.getElementById(chartId);
        if (!el) return false;
        var plotEl = el.querySelector(".js-plotly-plot");
        return plotEl && plotEl.data && plotEl.data.length > 0;
    }

    function scheduleRender(chartId, fig) {
        if (!fig || fig === NO) return;
        ensureObserved(chartId);
        if (isVisible[chartId] === false) {
            deferredFigs[chartId] = fig;
        } else {
            enqueue(chartId, fig);
        }
    }

    /**
     * Sized empty placeholder — lets Dash create the chart element without
     * rendering any traces (near-zero cost). Only used on first render.
     */
    function placeholder(fig) {
        if (!fig || !fig.layout) return NO;
        return {
            data: [],
            layout: {
                height: fig.layout.height || 380,
                margin: fig.layout.margin || {l: 36, r: 16, t: 8, b: 30},
                xaxis: {visible: false},
                yaxis: {visible: false},
                paper_bgcolor: "rgba(0,0,0,0)",
                plot_bgcolor: "rgba(0,0,0,0)"
            }
        };
    }

    /* ---- public API ---------------------------------------------------- */
    window.dash_clientside.billingDeferred = {

        renderTrend: function (chartId, storeData, sliceMode, agg,
                               smoothPct, chartType, stackVal) {
            if (!storeData) return NO;
            var slice = storeData[sliceMode || "category"];
            if (!slice) return NO;
            var raw = slice[agg || "M"];
            if (!raw) return NO;

            var fig = window.dash_clientside.census.smoothChartWithType(
                raw, smoothPct, chartType, null, stackVal
            );
            if (fig && fig.layout && fig.layout.margin) fig.layout.margin.l = 36;

            var isFirst = !hasExistingPlot(chartId);
            scheduleRender(chartId, fig);
            // First render: return placeholder so Dash creates the element.
            // Subsequent: return no_update so old chart stays visible until queue runs.
            return isFirst ? placeholder(fig) : NO;
        },

        renderCum: function (chartId, rawData, smoothPct, chartType,
                             stackVal, maxPrior, projectOn) {
            if (!rawData) return NO;

            if (projectOn === false) {
                rawData = JSON.parse(JSON.stringify(rawData));
                if (rawData.current) delete rawData.current.projection;
                delete rawData.projectionTotal;
            }
            var fig = window.dash_clientside.cumulative.renderCumulative(
                rawData, smoothPct, chartType, null, stackVal, maxPrior
            );
            if (fig && fig.layout && fig.layout.margin) fig.layout.margin.l = 36;

            var isFirst = !hasExistingPlot(chartId);
            scheduleRender(chartId, fig);
            return isFirst ? placeholder(fig) : NO;
        }
    };
})();
