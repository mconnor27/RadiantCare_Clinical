/**
 * 00_chart_deferred.js — Reusable staggered + below-fold chart rendering.
 *
 * Generalized from billing_deferred.js. Any page's chart clientside callback
 * can wrap its figure through this helper to get the same behavior billing
 * has enjoyed since launch:
 *
 *   - FIRST RENDER: returns an empty sized placeholder to Dash (near-zero
 *     cost). The real figure goes to a requestAnimationFrame queue that
 *     renders at most one chart per frame, so multiple charts landing in
 *     the same tick don't all block the main thread together.
 *
 *   - BELOW-FOLD: charts below the viewport wait for IntersectionObserver
 *     to intersect before their queued figure actually renders. Massively
 *     reduces initial paint work on pages with many stacked charts.
 *
 *   - SUBSEQUENT UPDATES: returns no_update so the old chart stays visible
 *     until the new figure is swapped in by the queue — no flash.
 *
 *   - RAPID UPDATES (slider drags): only the latest figure per chart in
 *     the queue survives; earlier pending figures are overwritten.
 *
 * Public API: window.dash_clientside.chartDeferred.wrap(chartId, figure)
 *   Returns the value to send back to Dash (placeholder / no_update).
 *   Schedules the real render via rAF + IntersectionObserver.
 *
 * Prefixed with "00_" so Dash loads it before any page-specific JS that
 * may reference window.dash_clientside.chartDeferred.
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

    function wrapSingle(chartId, fig) {
        if (!fig || fig === NO) return NO;
        var isFirst = !hasExistingPlot(chartId);
        scheduleRender(chartId, fig);
        return isFirst ? placeholder(fig) : NO;
    }

    /* ---- public API ---------------------------------------------------- */
    window.dash_clientside.chartDeferred = {

        /**
         * wrap(chartId, figureOrArray) — use at the tail end of any chart
         * clientside callback that returns a Plotly figure (or an array of
         * outputs whose first element is the figure).
         *
         * Single output: wraps the figure, returns placeholder/no_update.
         * Multi-output: wraps element [0] (the figure), passes through the
         *   rest of the array unchanged.
         */
        wrap: function (chartId, figOrArr) {
            if (Array.isArray(figOrArr)) {
                // Multi-output callback — first element is the figure,
                // subsequent elements are other props (titles, styles, etc.)
                figOrArr[0] = wrapSingle(chartId, figOrArr[0]);
                return figOrArr;
            }
            return wrapSingle(chartId, figOrArr);
        },

        // Low-level helpers for pages that want to customize placeholder.
        _enqueue: enqueue,
        _scheduleRender: scheduleRender,
        _hasExistingPlot: hasExistingPlot,
        _placeholder: placeholder
    };
})();
