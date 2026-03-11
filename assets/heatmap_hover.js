/**
 * Heatmap hover highlight for any heatmap chart.
 * Depends on: 00_utils.js (window.dash_clientside)
 */

window.dash_clientside = window.dash_clientside || {};

window.dash_clientside.heatmapHover = {
    /**
     * Trigger hover-highlight setup for ops heatmap.
     */
    init: function(fig) {
        if (!fig) return window.dash_clientside.no_update;
        setTimeout(function() {
            window.dash_clientside.heatmapHover._setupById("ops-chart-heatmap");
        }, 150);
        return window.dash_clientside.no_update;
    },

    /**
     * Trigger hover-highlight setup for home availability heatmap.
     */
    initHome: function(fig) {
        if (!fig) return window.dash_clientside.no_update;
        setTimeout(function() {
            window.dash_clientside.heatmapHover._setupById("home-chart-availability");
        }, 150);
        return window.dash_clientside.no_update;
    },

    _setupById: function(id) {
        var wrapper = document.getElementById(id);
        if (!wrapper) {
            requestAnimationFrame(function() {
                window.dash_clientside.heatmapHover._setupById(id);
            });
            return;
        }
        var el = wrapper.querySelector(".js-plotly-plot") || wrapper;
        if (typeof el.on !== "function") {
            if (typeof wrapper.on === "function") { el = wrapper; }
            else {
                requestAnimationFrame(function() {
                    window.dash_clientside.heatmapHover._setupById(id);
                });
                return;
            }
        }

        if (el._hmCleanup) el._hmCleanup();

        // Snapshot the base shapes (separators etc.) — we'll always restore these
        var baseShapes = (el.layout && el.layout.shapes)
            ? JSON.parse(JSON.stringify(el.layout.shapes))
            : [];

        function onHover(data) {
            if (!data.points || !data.points.length) return;
            var pt = data.points[0];
            var col, row;
            if (pt.pointIndex && pt.pointIndex.length === 2) {
                row = pt.pointIndex[0];
                col = pt.pointIndex[1];
            } else {
                return;
            }

            // Use axis refs from trace data (works for any subplot layout)
            var xref = (pt.data && pt.data.xaxis) || "x";
            var yref = (pt.data && pt.data.yaxis) || "y";

            var highlight = {
                type: "rect",
                x0: col - 0.46, x1: col + 0.46,
                y0: row - 0.46, y1: row + 0.46,
                fillcolor: "rgba(255,255,255,0.25)",
                line: {width: 0},
                xref: xref, yref: yref
            };
            var shapes = baseShapes.concat([highlight]);
            Plotly.relayout(el, {shapes: shapes});
        }

        function onUnhover() {
            // Restore base shapes only (removes highlight)
            Plotly.relayout(el, {shapes: baseShapes.slice()});
        }

        el.on("plotly_hover", onHover);
        el.on("plotly_unhover", onUnhover);

        el._hmCleanup = function() {
            el.removeListener("plotly_hover", onHover);
            el.removeListener("plotly_unhover", onUnhover);
        };
    }
};
