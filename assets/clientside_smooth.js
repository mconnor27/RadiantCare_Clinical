/**
 * Clientside LOESS smoothing for charts and sparklines.
 * Enables real-time slider updates without server round-trips.
 */

window.dash_clientside = window.dash_clientside || {};

// ---------------------------------------------------------------------------
// Sparkline smoothing (KPI cards)
// ---------------------------------------------------------------------------

function hexToRgba(hex, alpha) {
    var r = parseInt(hex.slice(1, 3), 16);
    var g = parseInt(hex.slice(3, 5), 16);
    var b = parseInt(hex.slice(5, 7), 16);
    return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
}

function buildSparkline(data, smoothPct, key) {
    if (!data || !data[key]) {
        return window.dash_clientside.no_update;
    }

    var spark = data[key];
    var frac = (smoothPct || 0) * 0.5;  // slider 0-1 maps to frac 0-0.5
    var rawVals = spark.values;
    var yVals = frac > 0 && rawVals.length >= 4 ? loess(rawVals, frac) : rawVals;
    var color = spark.color || "#7C2A83";
    // Use customdata for raw values so hover always shows actual numbers
    var hoverFmt = spark.hover_fmt
        ? spark.hover_fmt.replace(/%\{y/g, "%{customdata")
        : "%{x|%b %d}: %{customdata:,.0f}<extra></extra>";

    // Compute y range for gradient fill
    var yMin = Math.min.apply(null, yVals);
    var yMax = Math.max.apply(null, yVals);
    var yRange = yMax - yMin || 1;

    return {
        data: [{
            x: spark.labels,
            y: yVals,
            customdata: rawVals,
            mode: "lines",
            line: {color: color, width: 1.5},
            fill: "tozeroy",
            fillgradient: {
                type: "vertical",
                start: yMin - yRange * 0.3,
                stop: yMax,
                colorscale: [
                    [0, hexToRgba(color, 0)],
                    [1, hexToRgba(color, 0.2)]
                ]
            },
            fillcolor: hexToRgba(color, 0),
            hovertemplate: hoverFmt
        }],
        layout: {
            margin: {l: 0, r: 0, t: 0, b: 0},
            height: 44,
            plot_bgcolor: "rgba(0,0,0,0)",
            paper_bgcolor: "rgba(0,0,0,0)",
            xaxis: {
                visible: false,
                showspikes: true,
                spikemode: "across",
                spikethickness: 1,
                spikecolor: "#D1D5DB",
                spikedash: "solid"
            },
            yaxis: {
                visible: false,
                range: [yMin - yRange * 0.3, yMax + yRange * 0.05]
            },
            showlegend: false,
            dragmode: false,
            hovermode: "x",
            hoverlabel: {
                bgcolor: color,
                font: {color: "white", size: 10, family: "Inter, sans-serif"},
                bordercolor: color
            }
        }
    };
}

window.dash_clientside.sparklines = {
    smoothConsults: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "consults");
    },
    smoothSims: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "sims");
    },
    smoothTreatments: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "treatments");
    },
    smoothConsultLead: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "consult_lead");
    },
    smoothSimLead: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "sim_lead");
    },
    // Operations page sparklines
    smoothOpsToday: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "today");
    },
    smoothOpsHoursLacey: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "hours_lacey");
    },
    smoothOpsHoursCentralia: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "hours_centralia");
    },
    smoothOpsHoursAberdeen: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "hours_aberdeen");
    },
    smoothOpsLead: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "lead");
    },
    smoothOpsNewStarts: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "newstarts");
    }
};

// ---------------------------------------------------------------------------
// Census chart smoothing
// ---------------------------------------------------------------------------

window.dash_clientside.census = {
    /**
     * Apply smoothing to census chart data and return updated figure.
     * Supports future projections with lighter fill.
     * @param {Object} rawData - {dates, futureDates?, series: [{name, values, futureValues?, color}...], height, yTitle}
     * @param {number} smoothPct - Slider value 0-50, maps to rolling average window
     * @param {string} chartType - "area" (stacked), "line" (non-stacked), or "bar" (stacked bar)
     * @param {Object} currentFig - Current figure (to preserve trace visibility)
     * @returns {Object} Plotly figure
     */
    smoothChartWithType: function(rawData, smoothPct, chartType, currentFig) {
        if (!rawData || !rawData.series) {
            return window.dash_clientside.no_update;
        }

        chartType = chartType || "area";
        var dates = rawData.dates;
        var futureDates = rawData.futureDates || [];
        var height = rawData.height || 380;
        var yTitle = rawData.yTitle || "Unique Patients";
        var hasFuture = futureDates.length > 0;
        var stacked = rawData.stacked !== false;  // default true, opt-out with stacked:false

        // TEMPORARILY DISABLED: Downsampling was causing last data points to be dropped
        // TODO: Fix downsampling to ensure dates and values arrays have matching lengths
        var maxPoints = 10000;  // Effectively disable downsampling
        var step = dates.length > maxPoints ? Math.ceil(dates.length / maxPoints) : 1;
        var displayDates = step > 1 ? downsample(dates, step) : dates;

        // For bar charts, format dates and filter to valid ones only
        var barData = null;
        if (chartType === "bar") {
            barData = formatDatesForBars(displayDates);
        }

        // Build a map of trace visibility from current figure (by name)
        var visibilityMap = {};
        if (currentFig && currentFig.data) {
            for (var j = 0; j < currentFig.data.length; j++) {
                var trace = currentFig.data[j];
                if (trace.name && trace.visible !== undefined) {
                    visibilityMap[trace.name] = trace.visible;
                }
            }
        }

        // Rolling average window: slider 0 = no smoothing, slider 50 = ~50 point window
        var windowSize = Math.max(1, Math.floor(smoothPct) + 1);

        var traces = [];
        var renderSeries = rawData.series.slice();
        var rawValsByName = {};
        if (stacked && rawData.renderOrder && rawData.renderOrder.length) {
            var renderRanks = {};
            for (var ri = 0; ri < rawData.renderOrder.length; ri++) {
                renderRanks[rawData.renderOrder[ri]] = ri;
            }
            renderSeries.sort(function(a, b) {
                var aRank = renderRanks.hasOwnProperty(a.name) ? renderRanks[a.name] : Number.MAX_SAFE_INTEGER;
                var bRank = renderRanks.hasOwnProperty(b.name) ? renderRanks[b.name] : Number.MAX_SAFE_INTEGER;
                return aRank - bRank;
            });
        }
        var totals = new Array(displayDates.length).fill(0);
        var rawTotals = new Array(displayDates.length).fill(0);
        var futureTotals = hasFuture ? new Array(futureDates.length).fill(0) : [];

        // Past data traces (hoverinfo:"skip" — hover handled by summary trace)
        for (var i = 0; i < renderSeries.length; i++) {
            var s = renderSeries[i];
            var displayVals = step > 1 ? downsampleAvg(s.values, step) : s.values.slice();
            var yVals = smoothPct > 0 ? rollingAvg(displayVals, windowSize) : displayVals;
            var isVisible = !visibilityMap.hasOwnProperty(s.name) || visibilityMap[s.name] === true;

            rawValsByName[s.name] = displayVals;

            // Sum for total trace (smoothed for rendering, raw for hover) — only when stacked
            if (stacked && isVisible) {
                for (var k = 0; k < yVals.length; k++) {
                    totals[k] += yVals[k];
                    rawTotals[k] += displayVals[k];
                }
            }

            var traceObj;
            if (chartType === "bar") {
                // Bar chart (stacked or grouped)
                var filteredY = filterByIndices(yVals, barData.validIndices);
                var filteredRaw = filterByIndices(displayVals, barData.validIndices);
                traceObj = {
                    x: barData.labels,
                    y: filteredY,
                    customdata: filteredRaw,
                    name: s.name,
                    type: "bar",
                    marker: {color: s.color, line: {width: 0}},
                    hoverinfo: stacked ? "skip" : undefined,
                    hovertemplate: stacked ? undefined : s.name + ": %{customdata:.1f}" + (rawData.yTitle && rawData.yTitle.indexOf('%') >= 0 ? "%" : "") + "<extra></extra>"
                };
            } else if (chartType === "line") {
                // Line chart (always non-stacked)
                traceObj = {
                    x: displayDates,
                    y: yVals,
                    customdata: displayVals,
                    name: s.name,
                    mode: "lines",
                    line: {color: s.color, width: 2},
                    hoverinfo: stacked ? "skip" : undefined,
                    hovertemplate: stacked ? undefined : s.name + ": %{customdata:.1f}" + (rawData.yTitle && rawData.yTitle.indexOf('%') >= 0 ? "%" : "") + "<extra></extra>"
                };
            } else {
                // Area chart (stacked by default, overlay when stacked:false)
                traceObj = {
                    x: displayDates,
                    y: yVals,
                    customdata: displayVals,
                    name: s.name,
                    mode: "lines",
                    line: {color: s.color, width: stacked ? 1.5 : 2},
                    fillcolor: hexToRgba(s.color, stacked ? 0.5 : 0.15),
                    hoverinfo: stacked ? "skip" : undefined,
                    hovertemplate: stacked ? undefined : s.name + ": %{customdata:.1f}" + (rawData.yTitle && rawData.yTitle.indexOf('%') >= 0 ? "%" : "") + "<extra></extra>"
                };
                if (stacked) {
                    traceObj.stackgroup = "one";
                } else {
                    traceObj.fill = "tozeroy";
                }
            }

            // Preserve visibility if it was explicitly set
            if (visibilityMap.hasOwnProperty(s.name)) {
                traceObj.visible = visibilityMap[s.name];
            }

            traces.push(traceObj);
        }

        // Future projection traces (lighter fill, dotted line, no smoothing)
        if (hasFuture) {
            // For bar charts, format future dates
            var futureBarData = chartType === "bar" ? formatDatesForBars(futureDates) : null;

            for (var i = 0; i < renderSeries.length; i++) {
                var s = renderSeries[i];
                var futureVals = s.futureValues || [];
                if (futureVals.length === 0) continue;

                var isVisible = !visibilityMap.hasOwnProperty(s.name) || visibilityMap[s.name] === true;

                // Sum for future total
                if (isVisible) {
                    for (var k = 0; k < futureVals.length; k++) {
                        futureTotals[k] += futureVals[k];
                    }
                }

                var futureTraceObj;
                if (chartType === "bar") {
                    // Bar chart: lighter opacity bars for future (no smoothing, raw = y)
                    var filteredFutureY = filterByIndices(futureVals, futureBarData.validIndices);
                    futureTraceObj = {
                        x: futureBarData.labels,
                        y: filteredFutureY,
                        customdata: filteredFutureY,
                        name: s.name + " (scheduled)",
                        type: "bar",
                        marker: {color: s.color, opacity: 0.4, line: {width: 0}},
                        showlegend: false,
                        hoverinfo: "skip"
                    };
                } else {
                    // Line/area: connect to last past point
                    var lastPastDate = displayDates[displayDates.length - 1];
                    var lastPastVal = traces[i].y[traces[i].y.length - 1];

                    futureTraceObj = {
                        x: [lastPastDate].concat(futureDates),
                        y: [lastPastVal].concat(futureVals),
                        customdata: [lastPastVal].concat(futureVals),
                        name: s.name + " (scheduled)",
                        mode: "lines",
                        line: {color: s.color, width: 1, dash: "dot"},
                        fillcolor: chartType === "line" ? "transparent" : hexToRgba(s.color, 0.2),
                        stackgroup: chartType === "line" ? undefined : "future",
                        showlegend: false,
                        hoverinfo: "skip"
                    };
                }

                // Preserve visibility (use base name)
                if (visibilityMap.hasOwnProperty(s.name)) {
                    futureTraceObj.visible = visibilityMap[s.name];
                }

                traces.push(futureTraceObj);
            }
        }

        // Build summary hover text per date point (only for stacked mode)
        if (stacked) {
        var monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
        var summaryX = chartType === "bar" ? barData.labels : displayDates;
        var summaryHover = [];
        var nPts = chartType === "bar" ? barData.labels.length : displayDates.length;
        for (var idx = 0; idx < nPts; idx++) {
            var rawDate = chartType === "bar" ? barData.labels[idx] : displayDates[idx];
            var dateStr = "";
            if (rawDate) {
                var d = new Date(rawDate);
                if (!isNaN(d)) {
                    dateStr = monthNames[d.getMonth()] + " " + d.getDate() + ", " + d.getFullYear();
                } else {
                    dateStr = String(rawDate);
                }
            }
            var parts = dateStr ? ["<b>" + dateStr + "</b>"] : [];
            var total = 0;
            for (var si = 0; si < rawData.series.length; si++) {
                var rawIdx = chartType === "bar" ? barData.validIndices[idx] : idx;
                var seriesName = rawData.series[si].name;
                var seriesRawVals = rawValsByName[seriesName] || [];
                var val = Math.round(seriesRawVals[rawIdx] || 0);
                var isVis = !visibilityMap.hasOwnProperty(rawData.series[si].name) ||
                            visibilityMap[rawData.series[si].name] === true;
                if (val > 0 && isVis) {
                    parts.push("<span style='color:" + rawData.series[si].color + "'>\u25A0</span> " + rawData.series[si].name + ": " + val);
                    total += val;
                }
            }
            if (total > 0) {
                parts.push("<b>Total: " + total + "</b>");
            }
            summaryHover.push(parts.join("<br>"));
        }

        var summaryY = chartType === "bar"
            ? filterByIndices(totals, barData.validIndices)
            : totals;

        // Invisible summary trace carries the hover tooltip
        traces.push({
            x: summaryX,
            y: summaryY,
            customdata: summaryHover,
            name: "",
            mode: "lines",
            line: {color: "transparent", width: 0},
            hovertemplate: "%{customdata}<extra></extra>",
            showlegend: false
        });
        }  // end if (stacked)

        var smoothed = smoothPct > 0;
        var layout = {
            height: height,
            xaxis: {showgrid: false, showspikes: false},
            yaxis: {gridcolor: "#E5E7EB"},
            showlegend: !stacked,
            margin: {l: stacked ? 28 : 40, r: 8, t: 8, b: 32},
            plot_bgcolor: "white",
            paper_bgcolor: "white",
            font: {family: "Inter, system-ui, sans-serif", size: 12, color: "#374151"},
            hovermode: "x",
            hoverlabel: {
                align: "left",
                bgcolor: "white",
                bordercolor: "#E5E7EB",
                font: {color: "#374151", size: 12, family: "Inter, system-ui, sans-serif"}
            }
        };

        // Show legend above chart for non-stacked mode
        if (!stacked) {
            layout.legend = {
                orientation: "h",
                yanchor: "bottom",
                y: 1.02,
                xanchor: "left",
                x: 0
            };
            layout.margin.t = 28;
            // Suffix for y-axis
            if (rawData.yTitle && rawData.yTitle.indexOf('%') >= 0) {
                layout.yaxis.ticksuffix = '%';
            }
        }

        // Add barmode for bar charts
        if (chartType === "bar") {
            layout.barmode = stacked ? "stack" : "group";
            layout.bargap = 0.15;
            layout.bargroupgap = stacked ? 0 : 0.05;
            layout.xaxis.type = "category";
            layout.xaxis.tickangle = 0;
            layout.xaxis.nticks = 8;
        }

        return {
            data: traces,
            layout: layout
        };
    },

    // Legacy wrapper for backward compatibility
    smoothChart: function(rawData, smoothPct, currentFig) {
        return window.dash_clientside.census.smoothChartWithType(rawData, smoothPct, "area", currentFig);
    },

    /**
     * Apply smoothing to census chart with time range window support.
     * Same as smoothChartWithType but also sets x-axis range based on rangeDays.
     * All data is included in traces, but initial view is constrained to rangeDays.
     * @param {Object} rawData - {dates, futureDates?, series: [{name, values, futureValues?, color}...], height, yTitle}
     * @param {number} smoothPct - Slider value 0-50, maps to rolling average window
     * @param {string} chartType - "area" (stacked), "line" (non-stacked), or "bar" (stacked bar)
     * @param {string} rangeDays - Time window selector value ("30", "60", "90", "180", "365", "0" for all)
     * @param {Object} currentFig - Current figure (to preserve trace visibility)
     * @returns {Object} Plotly figure with x-axis range set to show selected time window
     */
    _buildWithRange: function(rawData, smoothPct, chartType, rangeDays, currentFig) {
        var fig = window.dash_clientside.census.smoothChartWithType(rawData, smoothPct, chartType, currentFig);

        if (fig === window.dash_clientside.no_update || !rawData || !rawData.dates || rawData.dates.length === 0) {
            return fig;
        }

        var days = parseInt(rangeDays) || 0;
        if (days > 0) {
            var lastDate = rawData.dates[rawData.dates.length - 1].split('T')[0];
            var lastDateObj = new Date(lastDate);
            var startDateObj = new Date(lastDateObj);
            startDateObj.setDate(startDateObj.getDate() - days);
            var startDate = startDateObj.toISOString().split('T')[0];

            fig.layout.xaxis = fig.layout.xaxis || {};
            fig.layout.xaxis.range = [startDate, lastDate];
            fig.layout.dragmode = 'pan';
            fig.layout.yaxis = fig.layout.yaxis || {};
            fig.layout.yaxis.fixedrange = true;
        } else {
            fig.layout.xaxis = fig.layout.xaxis || {};
            fig.layout.xaxis.autorange = true;
            fig.layout.dragmode = 'pan';
            fig.layout.yaxis = fig.layout.yaxis || {};
            fig.layout.yaxis.fixedrange = true;
        }

        return fig;
    },

    smoothChartWithTypeAndRange: function(rawData, smoothPct, chartType, rangeDays, currentFig) {
        if (!rawData || !rawData.dates || rawData.dates.length === 0) {
            return window.dash_clientside.census._buildWithRange(rawData, smoothPct, chartType, rangeDays, currentFig);
        }

        // Chart element ID: use rawData.chartId if provided, fallback to ops-chart-volume
        var chartElId = rawData.chartId || 'ops-chart-volume';
        var debounceKey = '_censusDebounce_' + chartElId;

        // Debounce: skip intermediate slider ticks, yield to browser for paint before render
        if (window[debounceKey]) clearTimeout(window[debounceKey]);
        window[debounceKey] = setTimeout(function() {
            // rAF queues after pending input/paint, setTimeout(0) yields one more frame
            requestAnimationFrame(function() { setTimeout(function() {
                var fig = window.dash_clientside.census._buildWithRange(rawData, smoothPct, chartType, rangeDays, currentFig);
                if (fig && fig !== window.dash_clientside.no_update) {
                    var el = document.getElementById(chartElId);
                    var plotEl = el && el.querySelector('.js-plotly-plot');
                    if (plotEl) Plotly.react(plotEl, fig.data, fig.layout);
                }
            }, 0); });
        }, 150);

        // First render (no existing plot) — render immediately
        var el = document.getElementById(chartElId);
        var plotEl = el && el.querySelector('.js-plotly-plot');
        if (!plotEl || !plotEl.data || !plotEl.data.length) {
            return window.dash_clientside.census._buildWithRange(rawData, smoothPct, chartType, rangeDays, currentFig);
        }
        return window.dash_clientside.no_update;
    }
};

// ---------------------------------------------------------------------------
// Courses namespace — fractions-per-course over time
// ---------------------------------------------------------------------------
window.dash_clientside.courses = {

    _hexToRgba: function(hex, alpha) {
        var r = parseInt(hex.slice(1,3), 16);
        var g = parseInt(hex.slice(3,5), 16);
        var b = parseInt(hex.slice(5,7), 16);
        return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
    },

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
            var fillColor = color.startsWith("#")
                ? window.dash_clientside.courses._hexToRgba(color, 0.2)
                : color.replace(")", ",0.2)").replace("rgb", "rgba");
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
            font: { family: "Inter, system-ui, sans-serif", size: 12, color: "#374151" },
            xaxis: {
                showgrid: false,
                zeroline: false,
                nticks: nticks,
                tickangle: 0,
            },
            yaxis: {
                title: yTitle,
                gridcolor: "#E5E7EB",
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
            var fillColor = color.startsWith("#")
                ? window.dash_clientside.courses._hexToRgba(color, 0.3)
                : color.replace(")", ",0.3)").replace("rgb", "rgba");

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
            font: { family: "Inter, system-ui, sans-serif", size: 12, color: "#374151" },
            xaxis: {
                title: "Fractions Prescribed",
                showgrid: false,
                zeroline: false,
                tickangle: 0,
            },
            yaxis: {
                title: "Density",
                gridcolor: "#E5E7EB",
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

/**
 * LOESS (Locally Estimated Scatterplot Smoothing) implementation.
 * Optimized O(n*k) version using sliding window for sequential time series.
 */
function loess(y, frac) {
    var n = y.length;
    if (n < 4 || frac <= 0) return y.slice();

    var k = Math.max(3, Math.floor(frac * n));
    var halfK = Math.floor(k / 2);
    var result = new Array(n);

    for (var i = 0; i < n; i++) {
        // Sliding window: k nearest neighbors are simply indices around i
        var left = Math.max(0, i - halfK);
        var right = Math.min(n - 1, i + halfK);

        // Adjust window to maintain size k when near edges
        if (right - left + 1 < k) {
            if (left === 0) {
                right = Math.min(n - 1, k - 1);
            } else {
                left = Math.max(0, n - k);
            }
        }

        var maxDist = Math.max(i - left, right - i) || 1;

        // Tricube weighted regression
        var sumW = 0, sumWY = 0, sumWX = 0, sumWXX = 0, sumWXY = 0;
        for (var j = left; j <= right; j++) {
            var dist = Math.abs(j - i);
            var u = dist / maxDist;
            var u3 = u * u * u;
            var w = (1 - u3) * (1 - u3) * (1 - u3);  // tricube: (1-u³)³
            var x = j - i;
            sumW += w;
            sumWY += w * y[j];
            sumWX += w * x;
            sumWXX += w * x * x;
            sumWXY += w * x * y[j];
        }

        // Weighted linear regression at x=0 (current point)
        var denom = sumW * sumWXX - sumWX * sumWX;
        if (Math.abs(denom) < 1e-10) {
            result[i] = sumWY / sumW;
        } else {
            var b0 = (sumWXX * sumWY - sumWX * sumWXY) / denom;
            result[i] = b0;
        }
    }

    return result;
}

function hexToRgba(hex, alpha) {
    var h = hex.replace("#", "");
    var r = parseInt(h.substring(0, 2), 16);
    var g = parseInt(h.substring(2, 4), 16);
    var b = parseInt(h.substring(4, 6), 16);
    return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
}

/**
 * Parse an ISO date string and return {valid, year, month, day} or {valid: false}.
 */
function parseIsoDate(dateStr) {
    if (!dateStr || typeof dateStr !== "string") return {valid: false};

    // Extract just the date part if it has time component
    var datePart = dateStr.split("T")[0];
    var parts = datePart.split("-");

    if (parts.length === 3) {
        var year = parseInt(parts[0], 10);
        var month = parseInt(parts[1], 10) - 1;  // JS months are 0-indexed
        var day = parseInt(parts[2], 10);

        // Validate the parsed values
        if (year >= 1900 && year <= 2100 && month >= 0 && month <= 11 && day >= 1 && day <= 31) {
            return {valid: true, year: year, month: month, day: day};
        }
    }
    return {valid: false};
}

/**
 * Format dates for bar chart x-axis and return {labels, validIndices}.
 * Only includes dates that parse correctly.
 */
function formatDatesForBars(dates) {
    if (!dates || dates.length === 0) return {labels: [], validIndices: []};

    var labels = [];
    var validIndices = [];
    var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    var lastYear = null;

    for (var i = 0; i < dates.length; i++) {
        var parsed = parseIsoDate(dates[i]);
        if (!parsed.valid) continue;  // Skip invalid dates

        validIndices.push(i);

        // Format label: add year on first item or year change
        if (lastYear === null || parsed.year !== lastYear) {
            labels.push(months[parsed.month] + " " + parsed.day + ", " + parsed.year);
            lastYear = parsed.year;
        } else {
            labels.push(months[parsed.month] + " " + parsed.day);
        }
    }
    return {labels: labels, validIndices: validIndices};
}

/**
 * Filter an array to only include items at the specified indices.
 */
function filterByIndices(arr, indices) {
    var result = [];
    for (var i = 0; i < indices.length; i++) {
        result.push(arr[indices[i]]);
    }
    return result;
}

/**
 * Downsample an array by taking every nth element (for dates/labels).
 * Always includes the last element to ensure recent data is shown.
 */
function downsample(arr, step) {
    if (arr.length === 0) return [];
    var result = [];
    for (var i = 0; i < arr.length; i += step) {
        result.push(arr[i]);
    }
    // Always include the last element if not already included
    var lastIdx = arr.length - 1;
    if (result[result.length - 1] !== arr[lastIdx]) {
        result.push(arr[lastIdx]);
    }
    return result;
}

/**
 * Downsample numeric values by averaging buckets of size `step`.
 * This preserves the visual shape better than just sampling.
 * Always includes the last bucket to ensure recent data is shown.
 */
function downsampleAvg(arr, step) {
    if (arr.length === 0) return [];
    var result = [];
    var i = 0;
    for (i = 0; i < arr.length; i += step) {
        var end = Math.min(i + step, arr.length);
        var sum = 0;
        for (var j = i; j < end; j++) {
            sum += arr[j];
        }
        result.push(sum / (end - i));
    }
    // If the last bucket wasn't complete (i.e., we didn't reach exactly arr.length),
    // the loop already handled it. But if step perfectly divides length and we want
    // to ensure the very last value is represented, check if we need to add it.
    // Actually, the loop above already handles partial buckets correctly.
    return result;
}

/**
 * Centered rolling average using prefix sums — O(n).
 * sum(rolling_avg(series)) = rolling_avg(sum(series))
 */
function rollingAvg(arr, windowSize) {
    if (windowSize <= 1) return arr.slice();
    var n = arr.length;
    var result = new Array(n);
    var halfW = Math.floor(windowSize / 2);

    // Build prefix sum array: prefix[i] = arr[0] + ... + arr[i-1]
    var prefix = new Array(n + 1);
    prefix[0] = 0;
    for (var i = 0; i < n; i++) {
        prefix[i + 1] = prefix[i] + arr[i];
    }

    for (var i = 0; i < n; i++) {
        var left = Math.max(0, i - halfW);
        var right = Math.min(n - 1, i + halfW);
        result[i] = (prefix[right + 1] - prefix[left]) / (right - left + 1);
    }
    return result;
}

// ---------------------------------------------------------------------------
// Operating Hours Ribbon Chart (band visualization)
// ---------------------------------------------------------------------------

function hourToTimeStr(hour) {
    if (hour === null || hour === undefined || isNaN(hour)) return "";
    var h = Math.floor(hour);
    var m = Math.round((hour - h) * 60);
    var suffix = h < 12 ? "AM" : "PM";
    var h12 = h <= 12 ? h : h - 12;
    if (h12 === 0) h12 = 12;
    return h12 + ":" + (m < 10 ? "0" : "") + m + " " + suffix;
}

window.dash_clientside.hoursRibbon = {
    /**
     * Build operating hours chart with clientside smoothing.
     * Supports ribbon (band), line, and bar chart types.
     * @param {Object} rawData - {pastSeries, futureSeries, yAxis, today}
     * @param {number} smoothVal - Rolling average window size (0 = no smoothing)
     * @param {string} chartType - "ribbon" (band), "line", or "bar"
     */
    smoothChartWithType: function(rawData, smoothVal, chartType) {
        if (!rawData || !rawData.pastSeries) {
            // Return empty figure
            return {
                data: [],
                layout: {
                    height: 380,
                    annotations: [{
                        text: "No operating hours data available",
                        xref: "paper", yref: "paper",
                        x: 0.5, y: 0.5, showarrow: false,
                        font: {size: 14, color: "#6B7280"}
                    }]
                }
            };
        }

        chartType = chartType || "ribbon";
        var windowSize = Math.max(1, Math.floor(smoothVal) + 1);
        var traces = [];
        var yAxis = rawData.yAxis;
        var today = rawData.today;

        // Build a map of past series end points for connecting to future
        var pastEndPoints = {};

        // Adjust fill opacity based on number of series (higher when single site)
        var numSeries = rawData.pastSeries.length;
        var pastFillOpacity = numSeries === 1 ? 0.35 : 0.15;
        var futureFillOpacity = numSeries === 1 ? 0.15 : 0.06;

        // Downsample to ~500 points max for performance (only for "All" view)
        // Skip downsampling for time-limited views to preserve daily granularity
        var skipDownsample = rawData._skipDownsample || false;
        var maxPoints = skipDownsample ? 999999 : 500;

        // Process past series
        for (var i = 0; i < rawData.pastSeries.length; i++) {
            var s = rawData.pastSeries[i];
            var dates = s.dates;
            var startHours = s.startHours.slice();
            var endHours = s.endHours.slice();

            // Downsample if needed
            var step = dates.length > maxPoints ? Math.ceil(dates.length / maxPoints) : 1;
            if (step > 1) {
                dates = downsample(dates, step);
                startHours = downsampleAvg(startHours, step);
                endHours = downsampleAvg(endHours, step);
            }

            // Apply smoothing after downsampling
            if (smoothVal > 0) {
                startHours = rollingAvg(startHours, windowSize);
                endHours = rollingAvg(endHours, windowSize);
            }

            // Store end point for connecting to future (use downsampled values)
            if (dates.length > 0) {
                pastEndPoints[s.name] = {
                    date: dates[dates.length - 1],
                    start: startHours[startHours.length - 1],
                    end: endHours[endHours.length - 1]
                };
            }

            // Build hover text (use downsampled dates)
            var hoverText = [];
            for (var j = 0; j < dates.length; j++) {
                var d = new Date(dates[j]);
                var dateStr = d.toLocaleDateString("en-US", {month: "short", day: "numeric"});
                hoverText.push("<b>" + s.name + "</b><br>" + dateStr + ": " +
                    hourToTimeStr(startHours[j]) + " - " + hourToTimeStr(endHours[j]));
            }

            var color = s.color;
            var fillColor = hexToRgba(color, pastFillOpacity);

            if (chartType === "bar") {
                // Floating bar chart: bars span from startHours to endHours
                var durations = [];
                var baseHours = [];
                for (var j = 0; j < startHours.length; j++) {
                    durations.push(endHours[j] - startHours[j]);
                    baseHours.push(startHours[j]);
                }
                // Format dates for categorical axis (filter to valid dates)
                var barData = formatDatesForBars(dates);
                var filteredDurations = filterByIndices(durations, barData.validIndices);
                var filteredBase = filterByIndices(baseHours, barData.validIndices);
                var filteredHoverText = filterByIndices(hoverText, barData.validIndices);
                traces.push({
                    x: barData.labels,
                    y: filteredDurations,
                    base: filteredBase,  // Floating bars start at startHours
                    name: s.name,
                    type: "bar",
                    marker: {color: color, opacity: 0.7, line: {width: 0}},
                    hovertemplate: "%{text}<extra></extra>",
                    text: filteredHoverText,
                    textposition: "none"  // Hide text annotations
                });
            } else if (chartType === "line") {
                // Line chart: show start and end times as separate lines
                traces.push({
                    x: dates,
                    y: startHours,
                    name: s.name + " Start",
                    mode: "lines",
                    line: {color: color, width: 2},
                    text: hoverText,
                    hovertemplate: "%{text}<extra></extra>"
                });
                traces.push({
                    x: dates,
                    y: endHours,
                    name: s.name + " End",
                    mode: "lines",
                    line: {color: color, width: 2, dash: "dash"},
                    showlegend: false,
                    hoverinfo: "skip"
                });
            } else {
                // Ribbon (band) chart - default
                // Upper bound trace (end hours) - invisible for fill
                traces.push({
                    x: dates,
                    y: endHours,
                    mode: "lines",
                    line: {width: 0},
                    showlegend: false,
                    hoverinfo: "skip"
                });

                // Lower bound trace (start hours) with fill to previous
                traces.push({
                    x: dates,
                    y: startHours,
                    mode: "lines",
                    line: {width: 0},
                    fill: "tonexty",
                    fillcolor: fillColor,
                    name: s.name,
                    showlegend: true,
                    text: hoverText,
                    hovertemplate: "%{text}<extra></extra>"
                });

                // Edge line - top (end hours)
                traces.push({
                    x: dates,
                    y: endHours,
                    mode: "lines",
                    line: {color: color, width: 1.5},
                    showlegend: false,
                    hoverinfo: "skip"
                });

                // Edge line - bottom (start hours)
                traces.push({
                    x: dates,
                    y: startHours,
                    mode: "lines",
                    line: {color: color, width: 1.5},
                    showlegend: false,
                    hoverinfo: "skip"
                });
            }
        }

        // Process future series (lighter fill for ribbon, lighter opacity bars for bar)
        if (chartType === "ribbon" || chartType === "bar") {
            for (var i = 0; i < rawData.futureSeries.length; i++) {
                var s = rawData.futureSeries[i];
                // No smoothing for future data, but still downsample if large
                var dates = s.dates;
                var startHours = s.startHours.slice();
                var endHours = s.endHours.slice();

                var step = dates.length > maxPoints ? Math.ceil(dates.length / maxPoints) : 1;
                if (step > 1) {
                    dates = downsample(dates, step);
                    startHours = downsampleAvg(startHours, step);
                    endHours = downsampleAvg(endHours, step);
                } else {
                    dates = dates.slice();  // copy to avoid mutation
                }

                // Build hover text
                var hoverText = [];
                for (var j = 0; j < dates.length; j++) {
                    var d = new Date(dates[j]);
                    var dateStr = d.toLocaleDateString("en-US", {month: "short", day: "numeric"});
                    hoverText.push("<b>" + s.name + " (scheduled)</b><br>" + dateStr + ": " +
                        hourToTimeStr(startHours[j]) + " - " + hourToTimeStr(endHours[j]));
                }

                var color = s.color;

                if (chartType === "bar") {
                    // Floating bar chart for future data (lighter opacity)
                    var durations = [];
                    var baseHours = [];
                    for (var j = 0; j < startHours.length; j++) {
                        durations.push(endHours[j] - startHours[j]);
                        baseHours.push(startHours[j]);
                    }
                    var barData = formatDatesForBars(dates);
                    var filteredDurations = filterByIndices(durations, barData.validIndices);
                    var filteredBase = filterByIndices(baseHours, barData.validIndices);
                    var filteredHoverText = filterByIndices(hoverText, barData.validIndices);
                    traces.push({
                        x: barData.labels,
                        y: filteredDurations,
                        base: filteredBase,
                        name: s.name + " (scheduled)",
                        type: "bar",
                        marker: {color: color, opacity: 0.35, line: {width: 0}},
                        hovertemplate: "%{text}<extra></extra>",
                        text: filteredHoverText,
                        textposition: "none",
                        showlegend: false
                    });
                } else {
                    // Ribbon chart - prepend past end point to connect
                    var pastEnd = pastEndPoints[s.name];
                    if (pastEnd && dates.length > 0) {
                        dates.unshift(pastEnd.date);
                        startHours.unshift(pastEnd.start);
                        endHours.unshift(pastEnd.end);
                        // Update hover text for connection point
                        var d = new Date(pastEnd.date);
                        var dateStr = d.toLocaleDateString("en-US", {month: "short", day: "numeric"});
                        hoverText.unshift("<b>" + s.name + "</b><br>" + dateStr + ": " +
                            hourToTimeStr(pastEnd.start) + " - " + hourToTimeStr(pastEnd.end));
                    }

                    var fillColor = hexToRgba(color, futureFillOpacity);

                    // Upper bound trace
                    traces.push({
                        x: dates,
                        y: endHours,
                        mode: "lines",
                        line: {width: 0},
                        showlegend: false,
                        hoverinfo: "skip"
                    });

                    // Lower bound trace with lighter fill
                    traces.push({
                        x: dates,
                        y: startHours,
                        mode: "lines",
                        line: {width: 0},
                        fill: "tonexty",
                        fillcolor: fillColor,
                        name: s.name + " (scheduled)",
                        showlegend: false,
                        text: hoverText,
                        hovertemplate: "%{text}<extra></extra>"
                    });

                    // Edge line - top (dashed for future)
                    traces.push({
                        x: dates,
                        y: endHours,
                        mode: "lines",
                        line: {color: color, width: 1, dash: "dot"},
                        showlegend: false,
                        hoverinfo: "skip"
                    });

                    // Edge line - bottom (dashed for future)
                    traces.push({
                        x: dates,
                        y: startHours,
                        mode: "lines",
                        line: {color: color, width: 1, dash: "dot"},
                        showlegend: false,
                        hoverinfo: "skip"
                    });
                }
            }
        }

        // Build layout with today line as shape (shifted back 1 day since data lags)
        var todayDate = new Date(today);
        todayDate.setDate(todayDate.getDate() - 1);
        var adjustedToday = todayDate.toISOString().split('T')[0];

        var shapes = [{
            type: "line",
            x0: adjustedToday,
            x1: adjustedToday,
            y0: 0,
            y1: 1,
            xref: "x",
            yref: "paper",
            line: {color: "rgba(124, 42, 131, 0.4)", width: 1, dash: "dash"}
        }];

        var layout = {
            height: 380,
            font: {family: "Inter, system-ui, sans-serif", size: 11},
            plot_bgcolor: "#FFFFFF",
            paper_bgcolor: "#FFFFFF",
            margin: {l: 36, r: 8, t: 8, b: 32},
            showlegend: false,
            hovermode: "x unified",
            xaxis: {showgrid: false},
            yaxis: {
                range: [yAxis.min, yAxis.max],
                tickvals: yAxis.tickvals,
                ticktext: yAxis.ticktext,
                gridcolor: "#E5E7EB"
            },
            shapes: shapes
        };

        // Add barmode for overlapping bars (categorical x-axis for no gaps)
        if (chartType === "bar") {
            layout.barmode = "overlay";
            layout.bargap = 0.15;  // Small gap to distinguish from ribbon chart
            layout.bargroupgap = 0;
            layout.xaxis.type = "category";
            layout.xaxis.tickangle = 0;  // Horizontal labels
            layout.xaxis.nticks = 8;  // Sparse labels
        }

        return {
            data: traces,
            layout: layout
        };
    },

    // Legacy wrapper for backward compatibility
    smoothChart: function(rawData, smoothVal) {
        return window.dash_clientside.hoursRibbon.smoothChartWithType(rawData, smoothVal, "ribbon");
    },

    /**
     * Build operating hours chart with time range window support.
     * Same as smoothChartWithType but also sets x-axis range based on rangeDays.
     * All data is included in traces, but initial view is constrained to rangeDays.
     * @param {Object} rawData - {pastSeries, futureSeries, yAxis, today}
     * @param {number} smoothVal - Rolling average window size (0 = no smoothing)
     * @param {string} chartType - "ribbon" (band), "line", or "bar"
     * @param {string} rangeDays - Time window selector value ("30", "60", "90", "180", "365", "0" for all)
     * @returns {Object} Plotly figure with x-axis range set to show selected time window
     */
    _buildWithRange: function(rawData, smoothVal, chartType, rangeDays) {
        window._ribbonChartData = rawData;

        var days = parseInt(rangeDays) || 0;
        rawData._skipDownsample = (days > 0);

        var fig = window.dash_clientside.hoursRibbon.smoothChartWithType(rawData, smoothVal, chartType);

        if (days > 0) {
            var lastDate = null;
            for (var i = 0; i < rawData.pastSeries.length; i++) {
                var s = rawData.pastSeries[i];
                if (s.dates && s.dates.length > 0) {
                    var d = s.dates[s.dates.length - 1];
                    if (!lastDate || d > lastDate) lastDate = d;
                }
            }
            if (rawData.futureSeries) {
                for (var i = 0; i < rawData.futureSeries.length; i++) {
                    var s = rawData.futureSeries[i];
                    if (s.dates && s.dates.length > 0) {
                        var d = s.dates[s.dates.length - 1];
                        if (!lastDate || d > lastDate) lastDate = d;
                    }
                }
            }

            if (lastDate) {
                lastDate = lastDate.split('T')[0];
                var lastDateObj = new Date(lastDate);
                var startDateObj = new Date(lastDateObj);
                startDateObj.setDate(startDateObj.getDate() - days);
                var startDate = startDateObj.toISOString().split('T')[0];

                var minHour = 24, maxHour = 0;
                var allSeries = rawData.pastSeries.concat(rawData.futureSeries || []);
                for (var i = 0; i < allSeries.length; i++) {
                    var s = allSeries[i];
                    for (var j = 0; j < s.dates.length; j++) {
                        var date = s.dates[j].split('T')[0];
                        if (date >= startDate && date <= lastDate) {
                            if (s.startHours[j] < minHour) minHour = s.startHours[j];
                            if (s.endHours[j] > maxHour) maxHour = s.endHours[j];
                        }
                    }
                }

                var yMin = Math.max(0, Math.floor(minHour * 2) / 2 - 0.5);
                var yMax = Math.min(24, Math.ceil(maxHour * 2) / 2 + 0.5);

                var tickvals = [], ticktext = [];
                for (var h = Math.ceil(yMin); h <= Math.floor(yMax); h++) {
                    tickvals.push(h);
                    ticktext.push(h === 0 ? "12am" : h < 12 ? h + "am" : h === 12 ? "12pm" : (h - 12) + "pm");
                }

                fig.layout.xaxis = fig.layout.xaxis || {};
                fig.layout.xaxis.range = [startDate, lastDate];
                fig.layout.xaxis.fixedrange = false;
                fig.layout.yaxis = fig.layout.yaxis || {};
                fig.layout.yaxis.range = [yMin, yMax];
                fig.layout.yaxis.tickvals = tickvals;
                fig.layout.yaxis.ticktext = ticktext;
                fig.layout.yaxis.fixedrange = true;
                fig.layout.dragmode = 'pan';
            }
        } else {
            fig.layout.xaxis = fig.layout.xaxis || {};
            fig.layout.xaxis.autorange = true;
            fig.layout.xaxis.fixedrange = false;
            fig.layout.yaxis = fig.layout.yaxis || {};
            fig.layout.yaxis.fixedrange = true;
            fig.layout.dragmode = 'pan';
        }

        return fig;
    },

    smoothChartWithTypeAndRange: function(rawData, smoothVal, chartType, rangeDays) {
        // Calendar mode: no debounce needed
        if (rangeDays === "thisweek") {
            window._ribbonChartData = rawData;
            var calFig = window.dash_clientside.hoursRibbon.renderCalendarWeek(rawData);
            setTimeout(window.dash_clientside.hoursRibbon._setupCalendarHover, 150);
            return calFig;
        }

        if (!rawData || !rawData.pastSeries || rawData.pastSeries.length === 0) {
            return window.dash_clientside.hoursRibbon.smoothChartWithType(rawData, smoothVal, chartType);
        }

        // Debounce: skip intermediate slider ticks, yield to browser for paint before render
        if (window._ribbonDebounce) clearTimeout(window._ribbonDebounce);
        window._ribbonDebounce = setTimeout(function() {
            requestAnimationFrame(function() { setTimeout(function() {
                var fig = window.dash_clientside.hoursRibbon._buildWithRange(rawData, smoothVal, chartType, rangeDays);
                if (fig && fig !== window.dash_clientside.no_update) {
                    var el = document.getElementById('ops-chart-ribbon');
                    var plotEl = el && el.querySelector('.js-plotly-plot');
                    if (plotEl) Plotly.react(plotEl, fig.data, fig.layout);
                }
            }, 0); });
        }, 150);

        // First render (no existing plot) — render immediately
        var el = document.getElementById('ops-chart-ribbon');
        var plotEl = el && el.querySelector('.js-plotly-plot');
        if (!plotEl || !plotEl.data || !plotEl.data.length) {
            return window.dash_clientside.hoursRibbon._buildWithRange(rawData, smoothVal, chartType, rangeDays);
        }
        return window.dash_clientside.no_update;
    },

    /**
     * Render a weekly calendar view of operating hours.
     * Shows Mon-Fri columns with time-of-day on Y-axis and colored bands
     * per department representing operating windows (first start to last end).
     *
     * @param {Object} rawData - {pastSeries, futureSeries, yAxis, today}
     * @returns {Object} Plotly figure
     */
    renderCalendarWeek: function(rawData) {
        var calHeight = (rawData && rawData.height) || 570;
        if (!rawData || (!rawData.pastSeries && !rawData.futureSeries)) {
            return {
                data: [],
                layout: {
                    height: calHeight,
                    annotations: [{
                        text: "No operating hours data available",
                        xref: "paper", yref: "paper",
                        x: 0.5, y: 0.5, showarrow: false,
                        font: {size: 14, color: "#6B7280"}
                    }]
                }
            };
        }

        // Calculate current week Mon-Fri
        var now = new Date();
        var dayOfWeek = now.getDay(); // 0=Sun, 1=Mon, ..., 6=Sat
        var mondayOffset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek;
        var monday = new Date(now);
        monday.setDate(now.getDate() + mondayOffset);
        monday.setHours(0, 0, 0, 0);

        // Build day labels and date strings for Mon-Fri
        var dayLabels = [];
        var dayDateStrs = []; // YYYY-MM-DD format for matching
        var dayNames = ["Mon", "Tue", "Wed", "Thu", "Fri"];
        for (var i = 0; i < 5; i++) {
            var d = new Date(monday);
            d.setDate(monday.getDate() + i);
            var mm = String(d.getMonth() + 1).padStart(2, "0");
            var dd = String(d.getDate()).padStart(2, "0");
            var yyyy = d.getFullYear();
            dayLabels.push(dayNames[i] + " " + mm + "/" + dd);
            dayDateStrs.push(yyyy + "-" + mm + "-" + dd);
        }

        // Today's date string
        var todayMm = String(now.getMonth() + 1).padStart(2, "0");
        var todayDd = String(now.getDate()).padStart(2, "0");
        var todayStr = now.getFullYear() + "-" + todayMm + "-" + todayDd;

        // Collect all series (past + future)
        var allSeries = [];
        if (rawData.pastSeries) allSeries = allSeries.concat(rawData.pastSeries);
        if (rawData.futureSeries) allSeries = allSeries.concat(rawData.futureSeries);

        // Build lookup: deptName -> [{col, startHour, endHour, count, isFuture}]
        var deptBands = {};
        var deptColors = {};
        for (var si = 0; si < allSeries.length; si++) {
            var s = allSeries[si];
            if (!s.dates || s.dates.length === 0) continue;
            deptColors[s.name] = s.color;

            for (var j = 0; j < s.dates.length; j++) {
                var dateStr = s.dates[j].split("T")[0];
                var col = dayDateStrs.indexOf(dateStr);
                if (col === -1) continue;

                if (!deptBands[s.name]) deptBands[s.name] = [];
                deptBands[s.name].push({
                    col: col,
                    startHour: s.startHours[j],
                    endHour: s.endHours[j],
                    count: (s.counts && s.counts[j]) ? s.counts[j] : 0,
                    isFuture: !!s.isFuture
                });
            }
        }

        // Determine department order and lane widths
        var deptNames = Object.keys(deptBands);
        if (deptNames.length === 0) {
            // Try to get dept names from series even if no data this week
            for (var si = 0; si < allSeries.length; si++) {
                if (deptNames.indexOf(allSeries[si].name) === -1) {
                    deptNames.push(allSeries[si].name);
                    deptColors[allSeries[si].name] = allSeries[si].color;
                }
            }
        }
        var numDepts = Math.max(deptNames.length, 1);
        var totalWidth = 0.85;
        var deptWidth = totalWidth / numDepts;
        var gapWidth = 0.02;

        // Calculate dept offsets (centered within each day column)
        var deptOffset = {};
        for (var d = 0; d < deptNames.length; d++) {
            deptOffset[deptNames[d]] = -totalWidth / 2 + d * deptWidth;
        }

        // Calculate Y-axis range from this week's data
        var minHour = 24, maxHour = 0;
        for (var dn in deptBands) {
            var bands = deptBands[dn];
            for (var b = 0; b < bands.length; b++) {
                if (bands[b].startHour < minHour) minHour = bands[b].startHour;
                if (bands[b].endHour > maxHour) maxHour = bands[b].endHour;
            }
        }
        if (minHour >= maxHour) { minHour = 7; maxHour = 18; }
        var yMin = Math.floor(minHour) - 0.5;
        var yMax = Math.ceil(maxHour) + 0.5;
        yMin = Math.max(0, yMin);
        yMax = Math.min(24, yMax);

        // Build shapes
        var shapes = [];

        // Today column highlight
        var todayCol = dayDateStrs.indexOf(todayStr);
        if (todayCol !== -1) {
            shapes.push({
                type: "rect",
                x0: todayCol - 0.48, x1: todayCol + 0.48,
                y0: yMin, y1: yMax,
                fillcolor: "rgba(124, 42, 131, 0.05)",
                line: {width: 0},
                xref: "x", yref: "y", layer: "below"
            });
        }

        // Horizontal gridlines at each hour
        for (var h = Math.ceil(yMin); h <= Math.floor(yMax); h++) {
            shapes.push({
                type: "line",
                x0: -0.5, x1: 4.5, y0: h, y1: h,
                line: {color: "#E5E7EB", width: 0.5},
                xref: "x", yref: "y", layer: "below"
            });
        }

        // Vertical day separators
        for (var d = 0; d < 4; d++) {
            shapes.push({
                type: "line",
                x0: d + 0.5, x1: d + 0.5, y0: yMin, y1: yMax,
                line: {color: "#E5E7EB", width: 1},
                xref: "x", yref: "y", layer: "below"
            });
        }

        // Department operating window bands (shapes for visuals, scatter for hover)
        var annotations = [];
        var hoverX = [], hoverY = [], hoverText = [], hoverBandIdx = [];
        var bandShapeMap = []; // bandIndex -> shapeIndex

        for (var dn in deptBands) {
            var color = deptColors[dn] || "#7C2A83";
            var offset = deptOffset[dn] || 0;
            var bands = deptBands[dn];
            var bandWidth = deptWidth - gapWidth;

            for (var b = 0; b < bands.length; b++) {
                var band = bands[b];
                var fillOpacity = band.isFuture ? 0.12 : 0.4;
                var borderDash = band.isFuture ? "dot" : "solid";
                var borderWidth = band.isFuture ? 1 : 1.5;

                var shapeIdx = shapes.length;
                shapes.push({
                    type: "rect",
                    x0: band.col + offset,
                    x1: band.col + offset + bandWidth,
                    y0: band.startHour, y1: band.endHour,
                    fillcolor: hexToRgba(color, fillOpacity),
                    line: {color: color, width: borderWidth, dash: borderDash},
                    xref: "x", yref: "y"
                });

                var bandIdx = bandShapeMap.length;
                bandShapeMap.push(shapeIdx);

                // Count annotation
                if (band.count > 0) {
                    annotations.push({
                        x: band.col + offset + bandWidth / 2,
                        y: (band.startHour + band.endHour) / 2,
                        text: "<b>" + band.count + "</b>",
                        showarrow: false,
                        font: {size: 11, color: color},
                        xref: "x", yref: "y",
                        opacity: band.isFuture ? 0.5 : 0.8
                    });
                }

                // Build tooltip once for this band
                var label = band.isFuture ? "<b>" + dn + " (scheduled)</b>" : "<b>" + dn + "</b>";
                var timeStr = hourToTimeStr(band.startHour) + " – " + hourToTimeStr(band.endHour);
                var countStr = band.count > 0 ? "<br>" + band.count + " appointments" : "";
                var tooltipText = label + "<br>" + timeStr + countStr;

                // Create multiple hover points spanning the band height.
                // A single center point causes hover to snap to the wrong band
                // when the cursor is near the top/bottom of a tall rectangle.
                var cx = band.col + offset + bandWidth / 2;
                var bandHeight = band.endHour - band.startHour;
                var numPoints = Math.max(3, Math.ceil(bandHeight));
                for (var p = 0; p < numPoints; p++) {
                    var t = numPoints === 1 ? 0.5 : p / (numPoints - 1);
                    hoverX.push(cx);
                    hoverY.push(band.startHour + t * bandHeight);
                    hoverText.push(tooltipText);
                    hoverBandIdx.push(bandIdx);
                }
            }
        }

        // Store shape info for hover highlight handler
        window._calendarShapeInfo = bandShapeMap.map(function(si) {
            var orig = shapes[si].fillcolor;
            var hover = orig.replace(/[\d.]+\)$/, function(m) {
                return Math.min(0.85, parseFloat(m) + 0.25) + ")";
            });
            return {idx: si, orig: orig, hover: hover};
        });
        window._calendarBandMap = hoverBandIdx; // point index -> band index
        window._calendarLastHovered = -1;

        // Invisible scatter points distributed within each band for hover tooltips
        var traces = [];
        if (hoverX.length > 0) {
            traces.push({
                x: hoverX, y: hoverY,
                mode: "markers",
                marker: {size: 1, color: "rgba(0,0,0,0)"},
                text: hoverText,
                hovertemplate: "%{text}<extra></extra>",
                showlegend: false
            });
        }

        // Y-axis tick labels
        var tickvals = [];
        var ticktext = [];
        for (var h = Math.ceil(yMin); h <= Math.floor(yMax); h++) {
            tickvals.push(h);
            if (h === 0) ticktext.push("12am");
            else if (h < 12) ticktext.push(h + "am");
            else if (h === 12) ticktext.push("12pm");
            else ticktext.push((h - 12) + "pm");
        }

        var layout = {
            height: calHeight,
            font: {family: "Inter, system-ui, sans-serif", size: 11},
            plot_bgcolor: "#FFFFFF",
            paper_bgcolor: "#FFFFFF",
            margin: {l: 44, r: 8, t: 32, b: 8},
            showlegend: false,
            hovermode: "closest",
            hoverdistance: -1,
            dragmode: false,
            xaxis: {
                tickvals: [0, 1, 2, 3, 4],
                ticktext: dayLabels,
                range: [-0.5, 4.5],
                showgrid: false,
                fixedrange: true,
                side: "top",
                zeroline: false
            },
            yaxis: {
                range: [yMax, yMin], // Reversed: morning at top
                tickvals: tickvals,
                ticktext: ticktext,
                showgrid: false,
                fixedrange: true,
                zeroline: false
            },
            shapes: shapes,
            annotations: annotations
        };

        return {data: traces, layout: layout};
    },

    /**
     * Attach plotly_hover / plotly_unhover listeners that brighten the
     * hovered shape rectangle via Plotly.relayout (lightweight, no re-render).
     */
    _setupCalendarHover: function() {
        // Find the actual Plotly div — Dash wraps it inside dcc.Graph
        // Check both home page and operations page element IDs
        var wrapper = document.getElementById("home-chart-hours")
                   || document.getElementById("ops-chart-ribbon");
        if (!wrapper) {
            console.log("[CalHover] wrapper not found, retrying…");
            requestAnimationFrame(window.dash_clientside.hoursRibbon._setupCalendarHover);
            return;
        }

        // The Plotly div is the child with class "js-plotly-plot", or the wrapper itself
        var el = wrapper.querySelector(".js-plotly-plot") || wrapper;
        console.log("[CalHover] wrapper:", wrapper.tagName, wrapper.className);
        console.log("[CalHover] plotly el:", el.tagName, el.className);
        console.log("[CalHover] el._fullData?", !!el._fullData, "el.on?", typeof el.on);

        if (!el._fullData && !el.on) {
            // Not ready yet
            console.log("[CalHover] not ready, retrying…");
            requestAnimationFrame(window.dash_clientside.hoursRibbon._setupCalendarHover);
            return;
        }

        // Also check if .on exists (Plotly adds it after newPlot)
        if (typeof el.on !== "function") {
            console.log("[CalHover] el.on is not a function — trying wrapper…");
            // Maybe Dash puts Plotly on the wrapper directly
            if (typeof wrapper.on === "function") {
                el = wrapper;
                console.log("[CalHover] using wrapper instead, wrapper.on?", typeof wrapper.on);
            } else {
                console.log("[CalHover] neither element has .on(), retrying…");
                requestAnimationFrame(window.dash_clientside.hoursRibbon._setupCalendarHover);
                return;
            }
        }

        // Tear down previous listeners
        if (el._calCleanup) el._calCleanup();

        var info = window._calendarShapeInfo;
        if (!info || !info.length) {
            console.log("[CalHover] no _calendarShapeInfo, aborting");
            return;
        }
        console.log("[CalHover] attaching listeners, " + info.length + " shapes");

        function onHover(data) {
            if (!data.points || !data.points.length) return;
            var ptIdx = data.points[0].pointIndex;
            // Map point index to band index (multiple points per band)
            var bandIdx = (window._calendarBandMap && window._calendarBandMap[ptIdx] !== undefined)
                ? window._calendarBandMap[ptIdx] : ptIdx;
            if (bandIdx === window._calendarLastHovered) return;

            // Restore previous
            if (window._calendarLastHovered >= 0 && window._calendarLastHovered < info.length) {
                var prev = info[window._calendarLastHovered];
                var u = {};
                u["shapes[" + prev.idx + "].fillcolor"] = prev.orig;
                Plotly.relayout(el, u);
            }

            // Highlight current
            if (bandIdx < info.length) {
                var curr = info[bandIdx];
                var u2 = {};
                u2["shapes[" + curr.idx + "].fillcolor"] = curr.hover;
                Plotly.relayout(el, u2);
                window._calendarLastHovered = bandIdx;
            }
        }

        function onUnhover() {
            console.log("[CalHover] UNHOVER");
            if (window._calendarLastHovered >= 0 && window._calendarLastHovered < info.length) {
                var prev = info[window._calendarLastHovered];
                var u = {};
                u["shapes[" + prev.idx + "].fillcolor"] = prev.orig;
                Plotly.relayout(el, u);
                window._calendarLastHovered = -1;
            }
        }

        el.on("plotly_hover", onHover);
        el.on("plotly_unhover", onUnhover);
        console.log("[CalHover] listeners attached successfully");

        el._calCleanup = function() {
            el.removeListener("plotly_hover", onHover);
            el.removeListener("plotly_unhover", onUnhover);
            window._calendarLastHovered = -1;
        };
    }
};

// ---------------------------------------------------------------------------
// Dynamic Y-Axis Scaling for Ribbon Chart on Pan
// ---------------------------------------------------------------------------

// Store reference to raw data for y-axis calculations (set by smoothChartWithTypeAndRange)
window._ribbonChartData = null;

// Helper function to calculate y-axis range from x-axis range
function calculateRibbonYAxis(startDate, endDate) {
    if (!window._ribbonChartData) return null;

    // Convert to YYYY-MM-DD format
    var startStr = (typeof startDate === 'string') ? startDate.split('T')[0] : new Date(startDate).toISOString().split('T')[0];
    var endStr = (typeof endDate === 'string') ? endDate.split('T')[0] : new Date(endDate).toISOString().split('T')[0];

    var rawData = window._ribbonChartData;

    // Calculate y-axis range from visible data (both past and future)
    var minHour = 24, maxHour = 0;
    for (var i = 0; i < rawData.pastSeries.length; i++) {
        var s = rawData.pastSeries[i];
        for (var j = 0; j < s.dates.length; j++) {
            var date = s.dates[j].split('T')[0];
            if (date >= startStr && date <= endStr) {
                if (s.startHours[j] < minHour) minHour = s.startHours[j];
                if (s.endHours[j] > maxHour) maxHour = s.endHours[j];
            }
        }
    }

    // Also include future series in y-axis calculation
    if (rawData.futureSeries && rawData.futureSeries.length > 0) {
        for (var i = 0; i < rawData.futureSeries.length; i++) {
            var s = rawData.futureSeries[i];
            for (var j = 0; j < s.dates.length; j++) {
                var date = s.dates[j].split('T')[0];
                if (date >= startStr && date <= endStr) {
                    if (s.startHours[j] < minHour) minHour = s.startHours[j];
                    if (s.endHours[j] > maxHour) maxHour = s.endHours[j];
                }
            }
        }
    }

    if (minHour === 24 || maxHour === 0) return null;

    // Round to nearest half-hour with padding
    var yMin = Math.floor(minHour * 2) / 2 - 0.5;
    var yMax = Math.ceil(maxHour * 2) / 2 + 0.5;
    yMin = Math.max(0, yMin);
    yMax = Math.min(24, yMax);

    // Generate tick values
    var tickvals = [];
    var ticktext = [];
    for (var h = Math.ceil(yMin); h <= Math.floor(yMax); h++) {
        tickvals.push(h);
        if (h === 0) {
            ticktext.push("12am");
        } else if (h < 12) {
            ticktext.push(h + "am");
        } else if (h === 12) {
            ticktext.push("12pm");
        } else {
            ticktext.push((h - 12) + "pm");
        }
    }

    return {
        range: [yMin, yMax],
        tickvals: tickvals,
        ticktext: ticktext
    };
}

// Note: Continuous updates during drag (plotly_relayouting) are not supported
// in Dash's clientside callback architecture. Y-axis updates on mouseup only.

// Clientside callback function to handle y-axis updates on pan (final update on mouseup)
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.ribbonYAxis = {
    updateYAxisOnPan: function(relayoutData, currentFigure) {
        // Skip in calendar mode (no panning, fixed axes)
        if (currentFigure && currentFigure.layout &&
            currentFigure.layout.xaxis && currentFigure.layout.xaxis.side === "top") {
            return window.dash_clientside.no_update;
        }

        // If no relayout data or no raw data, return current figure unchanged
        if (!relayoutData || !window._ribbonChartData || !currentFigure) {
            return window.dash_clientside.no_update;
        }

        // Extract x-axis range from relayout data
        var startDate, endDate;
        if (relayoutData['xaxis.range[0]'] !== undefined && relayoutData['xaxis.range[1]'] !== undefined) {
            startDate = relayoutData['xaxis.range[0]'];
            endDate = relayoutData['xaxis.range[1]'];
        } else if (relayoutData['xaxis.range'] && relayoutData['xaxis.range'].length === 2) {
            startDate = relayoutData['xaxis.range'][0];
            endDate = relayoutData['xaxis.range'][1];
        } else {
            return window.dash_clientside.no_update;
        }

        var yAxisConfig = calculateRibbonYAxis(startDate, endDate);
        if (!yAxisConfig) {
            return window.dash_clientside.no_update;
        }

        // Create updated figure with new y-axis range
        var newFigure = JSON.parse(JSON.stringify(currentFigure));
        newFigure.layout.yaxis.range = yAxisConfig.range;
        newFigure.layout.yaxis.tickvals = yAxisConfig.tickvals;
        newFigure.layout.yaxis.ticktext = yAxisConfig.ticktext;

        return newFigure;
    }
};

// ---------------------------------------------------------------------------
// Click Outside to Close Settings Panels
// ---------------------------------------------------------------------------

(function() {
    document.addEventListener('click', function(e) {
        // Find all open settings panels
        var panels = document.querySelectorAll('.chart-settings-panel');
        panels.forEach(function(panel) {
            if (panel.style.display === 'block') {
                // Check if click is outside the settings container
                var container = panel.closest('.chart-settings-container');
                if (container && !container.contains(e.target)) {
                    panel.style.display = 'none';
                }
            }
        });
    });
})();

// ---------------------------------------------------------------------------
// PNG Export Utility
// ---------------------------------------------------------------------------

window.dash_clientside.chartExport = {
    /**
     * Export a Plotly chart to PNG.
     * @param {number} n_clicks - Button click count (trigger)
     * @param {string} graphId - ID of the dcc.Graph component
     * @param {string} filename - Filename for the exported PNG
     */
    exportPng: function(n_clicks, graphId, filename) {
        if (!n_clicks) return window.dash_clientside.no_update;

        var graphEl = document.getElementById(graphId);
        if (!graphEl) {
            console.warn("Chart not found:", graphId);
            return window.dash_clientside.no_update;
        }

        filename = filename || graphId;
        Plotly.downloadImage(graphEl, {
            format: "png",
            width: 1200,
            height: 600,
            filename: filename
        });

        return window.dash_clientside.no_update;
    }
};

// ---------------------------------------------------------------------------
// Heatmap Hover Highlight
// ---------------------------------------------------------------------------

window.dash_clientside.heatmapHover = {
    /**
     * Trigger hover-highlight setup after heatmap figure updates.
     * Called as a clientside callback with the figure as input.
     */
    init: function(fig) {
        if (!fig) return window.dash_clientside.no_update;
        setTimeout(window.dash_clientside.heatmapHover._setup, 150);
        return window.dash_clientside.no_update;
    },

    _setup: function() {
        var wrapper = document.getElementById("ops-chart-heatmap");
        if (!wrapper) {
            requestAnimationFrame(window.dash_clientside.heatmapHover._setup);
            return;
        }
        var el = wrapper.querySelector(".js-plotly-plot") || wrapper;
        if (typeof el.on !== "function") {
            if (typeof wrapper.on === "function") { el = wrapper; }
            else { requestAnimationFrame(window.dash_clientside.heatmapHover._setup); return; }
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

            // Determine axis refs for the hovered subplot (3 facet rows)
            var yref = ["y", "y2", "y3"][pt.curveNumber] || "y";

            var highlight = {
                type: "rect",
                x0: col - 0.46, x1: col + 0.46,
                y0: row - 0.46, y1: row + 0.46,
                fillcolor: "rgba(255,255,255,0.25)",
                line: {width: 0},
                xref: "x", yref: yref
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
