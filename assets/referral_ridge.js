/**
 * Referral ridgeline chart — clientside rendering for dimension trend chart.
 * Reads store data + smoothing/chart-type/aggregation settings.
 * Depends on: 00_utils.js (hexToRgba, rollingAvg)
 */

window.dash_clientside = window.dash_clientside || {};

window.dash_clientside.referralRidge = {
    /**
     * Render the trend ridgeline from store data.
     * @param {Object} storeData - {combos: {W:{dates,series}, M:{…}, Y:{…}}, groups, height}
     * @param {number} smoothPct - Smoothing slider 0–30
     * @param {string} chartType - "area", "line", or "bar"
     * @param {string} agg - "W", "M", or "Y"
     * @returns {Object} Plotly figure
     */
    renderTrend: function(storeData, smoothPct, chartType, agg) {
        if (!storeData || !storeData.combos) {
            return window.dash_clientside.no_update;
        }

        agg = agg || "M";
        chartType = chartType || "area";
        var combo = storeData.combos[agg];
        var height = storeData.height || 720;

        // Empty state — mirrors utils.charts.empty_figure styling so this pane
        // matches the comparison pane visually when blank.
        if (!combo || !combo.series || combo.series.length === 0
                || !combo.dates || combo.dates.length === 0) {
            return {
                data: [],
                layout: {
                    height: height,
                    margin: {l: 0, r: 0, t: 0, b: 0},
                    plot_bgcolor: "rgba(0,0,0,0)",
                    paper_bgcolor: "rgba(0,0,0,0)",
                    xaxis: {visible: false},
                    yaxis: {visible: false},
                    annotations: [{
                        text: "No data for selected filters",
                        xref: "paper", yref: "paper", x: 0.5, y: 0.5,
                        showarrow: false,
                        font: {size: 14, color: "#9CA3AF"},
                    }],
                },
            };
        }

        var dates = combo.dates;
        var series = combo.series;  // [{name, values, color}, ...] ordered bottom→top
        var nDates = dates.length;
        var nGroups = series.length;
        var spacing = 1.0;

        // Smoothing window
        var windowSize = Math.max(1, Math.floor(smoothPct || 0) + 1);

        var traces = [];
        var xNum = [];
        for (var k = 0; k < nDates; k++) xNum.push(k);

        for (var i = 0; i < nGroups; i++) {
            var s = series[i];
            var baseline = i * spacing;
            var rawVals = s.values.slice();

            // Apply smoothing
            var vals = windowSize > 1 ? rollingAvg(rawVals, windowSize) : rawVals;

            // Per-row scaling: peak fits within 0.85 * spacing (no overlap)
            var rowMax = 0;
            for (var j = 0; j < vals.length; j++) {
                if (vals[j] > rowMax) rowMax = vals[j];
            }
            var rowScale = rowMax > 0 ? (0.85 * spacing / rowMax) : 0;

            var yScaled = [];
            for (var j = 0; j < vals.length; j++) {
                yScaled.push(vals[j] * rowScale + baseline);
            }

            var color = s.color;
            var fillRgba = hexToRgba(color, 0.35);

            // Build hover data — yearly shows just the year, otherwise "Mon YYYY".
            var hoverDates = [];
            for (var j = 0; j < nDates; j++) {
                var p = parseIsoDate(dates[j]);
                var monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
                if (!p.valid) {
                    hoverDates.push(dates[j]);
                } else if (agg === "Y") {
                    hoverDates.push(String(p.year));
                } else {
                    hoverDates.push(monthNames[p.month] + " " + p.year);
                }
            }

            var customdata = [];
            for (var j = 0; j < nDates; j++) {
                customdata.push([Math.round(rawVals[j]), s.name]);
            }

            if (chartType === "bar") {
                var barBase = [];
                var barHeights = [];
                for (var j = 0; j < vals.length; j++) {
                    barBase.push(baseline);
                    barHeights.push(vals[j] * rowScale);
                }
                traces.push({
                    type: "bar",
                    x: xNum,
                    y: barHeights,
                    base: barBase,
                    marker: {color: color, opacity: 0.7},
                    name: s.name,
                    showlegend: false,
                    customdata: customdata,
                    text: hoverDates,
                    // Hide the per-bar text label — keep it only as hover data.
                    // Without this, Plotly's default "auto" textposition prints
                    // a date on every bar in every row.
                    textposition: "none",
                    hovertemplate:
                        "<b>%{customdata[1]}</b>" +
                        "<br>%{text}" +
                        "<br>Count: %{customdata[0]}" +
                        "<extra></extra>",
                });
            } else {
                if (chartType === "area") {
                    var fillX = xNum.concat(xNum.slice().reverse());
                    var fillY = yScaled.concat(new Array(nDates).fill(baseline));
                    traces.push({
                        type: "scatter",
                        x: fillX,
                        y: fillY,
                        fill: "toself",
                        fillcolor: fillRgba,
                        line: {width: 0, color: "rgba(0,0,0,0)"},
                        hoverinfo: "skip",
                        showlegend: false,
                    });
                }
                // Use lines+markers in yearly view (and any time there's a
                // single point) so the dot is visible — a 1-point line trace
                // renders nothing on its own.
                var useMarkers = agg === "Y" || nDates < 2;
                var lineTrace = {
                    type: "scatter",
                    x: xNum,
                    y: yScaled,
                    mode: useMarkers ? "lines+markers" : "lines",
                    line: {color: color, width: 1.8},
                    name: s.name,
                    showlegend: false,
                    customdata: customdata,
                    text: hoverDates,
                    hovertemplate:
                        "<b>%{customdata[1]}</b>" +
                        "<br>%{text}" +
                        "<br>Count: %{customdata[0]}" +
                        "<extra></extra>",
                };
                if (useMarkers) lineTrace.marker = {color: color, size: 6};
                traces.push(lineTrace);
            }
        }

        // X-axis ticks (~8 labels). Yearly aggregation shows just the year;
        // weekly/monthly use "Mon 'YY".
        var step = Math.max(1, Math.floor(nDates / 8));
        var tickVals = [];
        var tickLabels = [];
        for (var j = 0; j < nDates; j += step) {
            tickVals.push(j);
            var p = parseIsoDate(dates[j]);
            var monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
            if (!p.valid) {
                tickLabels.push(dates[j]);
            } else if (agg === "Y") {
                tickLabels.push(String(p.year));
            } else {
                var yr = p.year % 100;
                tickLabels.push(monthNames[p.month] + " '" + (yr < 10 ? "0" + yr : yr));
            }
        }

        // Y-axis ticks
        var yTickVals = [];
        var yTickText = [];
        for (var i = 0; i < nGroups; i++) {
            yTickVals.push(i * spacing);
            yTickText.push(series[i].name);
        }

        var layout = {
            height: height,
            yaxis: {
                tickvals: yTickVals,
                ticktext: yTickText,
                showgrid: true,
                gridcolor: "rgba(200,200,200,0.45)",
                zeroline: false,
                title: "",
                range: [-0.25 * spacing, (nGroups - 1 + 1.0) * spacing],
                automargin: true,
                tickfont: {size: 11},
            },
            xaxis: {
                tickvals: tickVals,
                ticktext: tickLabels,
                showgrid: false,
                zeroline: false,
                title: "",
            },
            margin: {l: 0, r: 16, t: 16, b: 20},
            plot_bgcolor: "rgba(0,0,0,0)",
            paper_bgcolor: "rgba(0,0,0,0)",
            font: {family: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"},
            hovermode: "closest",
            hoverlabel: {font: {family: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif", size: 12}},
            barmode: "overlay",
            bargap: 0,
        };

        return {data: traces, layout: layout};
    }
};
