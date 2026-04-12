/**
 * Clientside histogram / density rendering for the Tasks page.
 */

window.dash_clientside = window.dash_clientside || {};

window.dash_clientside.histogram = {

    /**
     * Render histogram or density from store data.
     * @param {Object} rawData - {series, stats, sliced}
     * @param {string} chartType - "histogram" or "density"
     * @param {number} bwFactor - KDE bandwidth factor (Scott's rule multiplier)
     * @param {Object} currentFig - existing figure (unused, for Dash wiring)
     */
    render: function(rawData, chartType, bwSlider, currentFig) {
        if (!rawData || !rawData.series || rawData.series.length === 0) {
            return Object.assign({}, window.dash_clientside.census._emptyFig("No completion time data"));
        }

        var stats = rawData.stats;
        var series = rawData.series;
        var sliced = rawData.sliced;
        chartType = chartType || "histogram";
        var bwValue = bwSlider || 0.12;

        // Collect global range for bandwidth calculation
        var allVals = [];
        series.forEach(function(s) { allVals = allVals.concat(s.values); });
        var globalMin = Math.min.apply(null, allVals);
        var globalMax = Math.max.apply(null, allVals);
        var globalRange = globalMax - globalMin || 1;

        // Slider value used directly as fraction of data range
        var bandwidth = globalRange * bwValue;

        var traces = [];

        function fmtVal(v) {
            return Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(1);
        }

        for (var si = 0; si < series.length; si++) {
            var s = series[si];
            var vals = s.values;
            var color = s.color;
            var fillColor = hexToRgba(color, 0.7);
            var lightFill = hexToRgba(color, 0.15);
            var showLegend = sliced;

            if (chartType === "density" && vals.length > 1) {
                var kde = gaussianKDEFixed(vals, bandwidth, globalMin, globalMax);
                traces.push({
                    type: "scatter",
                    x: kde.x,
                    y: kde.y,
                    mode: "lines",
                    fill: "tozeroy",
                    name: s.name,
                    line: {color: color, width: 2},
                    fillcolor: lightFill,
                    showlegend: showLegend,
                    hovertemplate: stats.xTitle + ": %{x:.1f}<br>Density: %{y:.4f}<extra></extra>",
                    hoverlabel: {bgcolor: color, font: {color: "white"}}
                });
            } else {
                traces.push({
                    type: "histogram",
                    x: vals,
                    marker: {color: fillColor, line: {color: color, width: 1}},
                    xbins: {size: 1},
                    name: s.name,
                    showlegend: showLegend,
                    hovertemplate: stats.xTitle + ": %{x}<br>Count: %{y}<extra></extra>",
                    hoverlabel: {bgcolor: color, font: {color: "white"}}
                });
            }
        }

        // Compute display range for dtick
        var allVals = [];
        series.forEach(function(s) { allVals = allVals.concat(s.values); });
        var xMin = Math.min.apply(null, allVals);
        var xMax = Math.max.apply(null, allVals);
        var xSpan = xMax - xMin;
        var dtick = xSpan <= 15 ? 1 : (xSpan <= 30 ? 2 : undefined);

        var layout = {
            xaxis: {
                showgrid: false, autorange: true,
                dtick: dtick, tickangle: 0,
                ticksuffix: stats.tickSuffix,
                spikemode: "across", spikethickness: 1
            },
            yaxis: {gridcolor: "#F0F0F0", gridwidth: 1},
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            margin: {l: 32, r: 12, t: 28, b: 34},
            barmode: "overlay",
            height: 330,
            showlegend: sliced && series.length > 1,
            legend: {
                orientation: "h", y: 1.02, x: 0, xanchor: "left", yanchor: "bottom",
                font: {size: 11}, tracegroupgap: 0, itemwidth: 30
            },
            hovermode: "closest",
            shapes: [{
                type: "line",
                x0: stats.median, x1: stats.median,
                y0: 0, y1: 1, yref: "paper",
                line: {color: stats.accentColor, width: 2, dash: "dash"}
            }],
            annotations: [
                {
                    x: stats.median, y: 1.06, yref: "paper", xref: "x",
                    text: "Median: " + fmtVal(stats.median) + stats.suffix,
                    showarrow: false,
                    font: {size: 11, color: stats.accentColor}
                },
                {
                    text: "n=" + stats.n.toLocaleString() + "  Mean: " + fmtVal(stats.mean) + stats.suffix +
                          "  (IQR: " + fmtVal(stats.q1) + "\u2013" + fmtVal(stats.q3) + stats.suffix + ")",
                    xref: "paper", yref: "paper",
                    x: 0.5, y: 0, xanchor: "center", yanchor: "top",
                    yshift: -18, showarrow: false,
                    font: {size: 12, color: "#9CA3AF"}
                }
            ]
        };

        return {data: traces, layout: layout};
    }
};


/**
 * Gaussian KDE with fixed bandwidth over a shared x grid.
 * Matches the pattern used in courses_chart.js.
 */
function gaussianKDEFixed(data, bandwidth, globalMin, globalMax) {
    var n = data.length;
    if (n < 2) return {x: [], y: []};

    var range = globalMax - globalMin || 1;
    var pad = range * 0.05;
    var xMin = Math.max(0, globalMin - pad);
    var xMax = globalMax + pad;
    var nBins = 100;
    var step = (xMax - xMin) / nBins;

    var x = [], y = [];
    for (var i = 0; i <= nBins; i++) {
        var xi = xMin + i * step;
        var density = 0;
        for (var k = 0; k < n; k++) {
            var z = (xi - data[k]) / bandwidth;
            density += Math.exp(-0.5 * z * z);
        }
        density /= (n * bandwidth * Math.sqrt(2 * Math.PI));
        x.push(Math.round(xi * 100) / 100);
        y.push(density);
    }
    return {x: x, y: y};
}
