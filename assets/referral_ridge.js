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
        if (!combo || !combo.series || combo.series.length === 0) {
            return window.dash_clientside.no_update;
        }

        var dates = combo.dates;
        var series = combo.series;  // [{name, values, color}, ...] ordered bottom→top
        var height = storeData.height || 720;
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

            // Build hover data
            var hoverDates = [];
            for (var j = 0; j < nDates; j++) {
                var p = parseIsoDate(dates[j]);
                var monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
                hoverDates.push(p.valid ? monthNames[p.month] + " " + p.year : dates[j]);
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
                traces.push({
                    type: "scatter",
                    x: xNum,
                    y: yScaled,
                    mode: "lines",
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
                });
            }
        }

        // X-axis ticks (~8 labels)
        var step = Math.max(1, Math.floor(nDates / 8));
        var tickVals = [];
        var tickLabels = [];
        for (var j = 0; j < nDates; j += step) {
            tickVals.push(j);
            var p = parseIsoDate(dates[j]);
            var monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
            var yr = p.valid ? p.year % 100 : 0;
            tickLabels.push(p.valid ? monthNames[p.month] + " '" + (yr < 10 ? "0" + yr : yr) : dates[j]);
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
            bargap: 0,
        };

        return {data: traces, layout: layout};
    }
};
