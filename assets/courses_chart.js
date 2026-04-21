/**
 * Courses page chart renderers — fractions-per-course and KDE density.
 * Depends on: 00_utils.js (hexToRgba, rollingAvg)
 */

window.dash_clientside = window.dash_clientside || {};

function _coursesTheme() {
    var isDark = document.documentElement.getAttribute("data-theme") === "dark";
    return {
        isDark: isDark,
        font: isDark ? "#E6E7EC" : "#374151",
        grid: isDark ? "#262932" : "#E5E7EB",
        areaFillOpacity: function(base) {
            if (!isDark) return base;
            if (base <= 0.20) return base + 0.15;
            if (base <= 0.30) return base + 0.10;
            return base;
        },
    };
}

window.dash_clientside.courses = {

    /**
     * Render fractions-per-course chart from store data.
     * @param {Object} rawData - {labels, values, counts, yTitle, height, color}
     * @param {string} chartType - "bar", "line", or "area"
     * @param {number} smoothPct - Smoothing slider value (0 = none)
     * @param {Object} currentFig - preserve trace visibility
     */
    renderFractions: function(rawData, chartType, smoothPct, currentFig) {
        if (!rawData || !rawData.labels || rawData.labels.length === 0) {
            return window.dash_clientside.no_update;
        }

        chartType = chartType || "bar";
        smoothPct = smoothPct || 0;
        var labels = rawData.labels;
        var values = rawData.values;
        var height = rawData.height || 380;
        var yTitle = rawData.yTitle || "Avg Fractions";
        var color = rawData.color || "#7C2A83";
        var counts = rawData.counts || [];

        // Apply smoothing (rolling average)
        var windowSize = Math.max(1, Math.floor(smoothPct) + 1);
        var yVals = smoothPct > 0 ? rollingAvg(values, windowSize) : values;

        var traceBase = {
            x: labels,
            y: yVals,
            name: "Avg Fractions",
            customdata: counts.length ? counts : undefined,
            hovertemplate: counts.length
                ? "<b>%{x}</b><br>Avg Fractions: %{y:.1f}<br>Courses: %{customdata}<extra></extra>"
                : "<b>%{x}</b><br>Avg Fractions: %{y:.1f}<extra></extra>",
        };

        var trace;
        if (chartType === "bar") {
            trace = Object.assign({}, traceBase, {
                type: "bar",
                marker: { color: color, opacity: 0.85 },
            });
        } else if (chartType === "area") {
            var fillColor = hexToRgba(color, _coursesTheme().areaFillOpacity(0.2));
            trace = Object.assign({}, traceBase, {
                type: "scatter",
                mode: "lines",
                fill: "tozeroy",
                line: { color: color, width: 2 },
                fillcolor: fillColor,
            });
        } else {
            trace = Object.assign({}, traceBase, {
                type: "scatter",
                mode: "lines+markers",
                line: { color: color, width: 2 },
                marker: { color: color, size: 5 },
            });
        }

        // Sparse x-axis labels: show ~12-15 ticks max, horizontal
        var nticks = Math.min(labels.length, 15);

        var layout = {
            height: height,
            margin: { l: 48, r: 16, t: 8, b: 48 },
            plot_bgcolor: "rgba(0,0,0,0)",
            paper_bgcolor: "rgba(0,0,0,0)",
            font: { family: "Inter, system-ui, sans-serif", size: 12, color: _coursesTheme().font },
            xaxis: {
                showgrid: false,
                zeroline: false,
                nticks: nticks,
                tickangle: 0,
            },
            yaxis: {
                title: yTitle,
                gridcolor: _coursesTheme().grid,
                gridwidth: 1,
                zeroline: false,
            },
            hovermode: "x unified",
            dragmode: "pan",
        };

        return { data: [trace], layout: layout };
    },

    /**
     * Render density comparison chart for fraction distributions.
     * @param {Object} rawData - {period1: {label, values, color}, period2?: {label, values, color}}
     * @param {number} bwSlider - Bandwidth slider (0-20). 0 = auto, higher = smoother.
     */
    renderDensity: function(rawData, bwSlider) {
        if (!rawData || !rawData.period1 || !rawData.period1.values || rawData.period1.values.length === 0) {
            return window.dash_clientside.no_update;
        }

        bwSlider = bwSlider || 6;  // default matches smooth_default

        // Collect global min/max across both periods for consistent x grid
        var allVals = [];
        var periods = ["period1", "period2"];
        for (var i = 0; i < periods.length; i++) {
            var p = rawData[periods[i]];
            if (p && p.values && p.values.length > 0) {
                allVals = allVals.concat(p.values);
            }
        }
        var globalMin = Math.min.apply(null, allVals);
        var globalMax = Math.max.apply(null, allVals);
        var globalRange = globalMax - globalMin || 1;

        var traces = [];

        for (var i = 0; i < periods.length; i++) {
            var key = periods[i];
            var pd = rawData[key];
            if (!pd || !pd.values || pd.values.length === 0) continue;

            var vals = pd.values;
            var color = pd.color;
            var fillColor = hexToRgba(color, _coursesTheme().areaFillOpacity(0.3));

            // Bandwidth: slider maps 1-20 to fraction of range (0.5% to 10%)
            var bwFrac = Math.max(0.005, bwSlider * 0.005);
            var bandwidth = globalRange * bwFrac;

            // Build KDE using gaussian kernel over shared x grid
            var nBins = 100;
            var pad = globalRange * 0.05;  // 5% padding on each side
            var step = (globalRange + 2 * pad) / nBins;
            var xGrid = [];
            var yGrid = [];

            for (var j = 0; j <= nBins; j++) {
                var x = (globalMin - pad) + j * step;
                xGrid.push(Math.round(x * 10) / 10);
                var density = 0;
                for (var k = 0; k < vals.length; k++) {
                    var z = (x - vals[k]) / bandwidth;
                    density += Math.exp(-0.5 * z * z);
                }
                density /= (vals.length * bandwidth * Math.sqrt(2 * Math.PI));
                yGrid.push(density);
            }

            traces.push({
                x: xGrid,
                y: yGrid,
                type: "scatter",
                mode: "lines",
                fill: "tozeroy",
                name: pd.label + " (n=" + vals.length + ")",
                line: { color: color, width: 2 },
                fillcolor: fillColor,
                hovertemplate: "<b>" + pd.label + "</b><br>Fractions: %{x:.0f}<br>Density: %{y:.4f}<extra></extra>",
            });
        }

        var layout = {
            height: 380,
            margin: { l: 48, r: 16, t: 8, b: 48 },
            plot_bgcolor: "rgba(0,0,0,0)",
            paper_bgcolor: "rgba(0,0,0,0)",
            font: { family: "Inter, system-ui, sans-serif", size: 12, color: _coursesTheme().font },
            xaxis: {
                title: "Fractions Prescribed",
                showgrid: false,
                zeroline: false,
                tickangle: 0,
            },
            yaxis: {
                title: "Density",
                gridcolor: _coursesTheme().grid,
                gridwidth: 1,
                zeroline: false,
            },
            legend: {
                orientation: "h",
                yanchor: "bottom",
                y: 1.02,
                xanchor: "left",
                x: 0,
            },
            hovermode: "x unified",
        };

        return { data: traces, layout: layout };
    }
};
