/**
 * Census chart rendering — stacked area/line/bar charts with smoothing.
 * Used by home, operations, and any page needing time-series census charts.
 * Also includes the efficiency wrapper (machine filter + metric toggle).
 * Depends on: 00_utils.js (hexToRgba, rollingAvg, downsample, downsampleAvg,
 *             formatDatesForBars, filterByIndices)
 */

window.dash_clientside = window.dash_clientside || {};

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
        var futureRawValsByName = {};

        // Past data traces (hoverinfo:"skip" — hover handled by summary trace)
        for (var i = 0; i < renderSeries.length; i++) {
            var s = renderSeries[i];
            var displayVals = step > 1 ? downsampleAvg(s.values, step) : s.values.slice();
            // For stacked area, replace nulls with 0 before smoothing so the
            // rolling average creates a smooth ramp at go-live instead of a cliff.
            // In a stacked area, 0 is invisible (contributes nothing to the stack).
            if (stacked && chartType === "area") {
                for (var di = 0; di < displayVals.length; di++) {
                    if (displayVals[di] === null || displayVals[di] === undefined) displayVals[di] = 0;
                }
            }
            // Bar charts use raw values — smoothing creates fractional-height spikes
            var yVals = (smoothPct > 0 && chartType !== "bar") ? rollingAvg(displayVals, windowSize) : displayVals;
            var isVisible = !visibilityMap.hasOwnProperty(s.name) || visibilityMap[s.name] === true;

            rawValsByName[s.name] = displayVals;

            // Sum for total trace (smoothed for rendering, raw for hover) — only when stacked
            // Guard against null values (pre/post-active periods)
            if (stacked && isVisible) {
                for (var k = 0; k < yVals.length; k++) {
                    totals[k] += (yVals[k] || 0);
                    rawTotals[k] += (displayVals[k] || 0);
                }
            }

            // Trim leading/trailing nulls so traces start/end at their active range.
            // Only for non-stacked charts — stacked area needs aligned x-axes.
            var traceDates = displayDates;
            var traceY = yVals;
            var traceRaw = displayVals;
            if (chartType === "line" || (chartType === "area" && !stacked)) {
                var ts = 0, te = yVals.length - 1;
                while (ts < yVals.length && (yVals[ts] === null || yVals[ts] === undefined)) ts++;
                while (te >= 0 && (yVals[te] === null || yVals[te] === undefined)) te--;
                if (ts > 0 || te < yVals.length - 1) {
                    if (ts <= te) {
                        traceDates = displayDates.slice(ts, te + 1);
                        traceY = yVals.slice(ts, te + 1);
                        traceRaw = displayVals.slice(ts, te + 1);
                    } else {
                        traceDates = [];
                        traceY = [];
                        traceRaw = [];
                    }
                }
            }

            var traceObj;
            if (chartType === "bar") {
                // Bar chart (stacked or grouped) — null bars naturally invisible
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
                    x: traceDates,
                    y: traceY,
                    customdata: traceRaw,
                    name: s.name,
                    mode: "lines",
                    line: {color: s.color, width: 2},
                    hoverinfo: stacked ? "skip" : undefined,
                    hovertemplate: stacked ? undefined : s.name + ": %{customdata:.1f}" + (rawData.yTitle && rawData.yTitle.indexOf('%') >= 0 ? "%" : "") + "<extra></extra>"
                };
            } else {
                // Area chart (stacked by default, overlay when stacked:false)
                traceObj = {
                    x: traceDates,
                    y: traceY,
                    customdata: traceRaw,
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
                futureRawValsByName[s.name] = futureVals.slice();

                var isVisible = !visibilityMap.hasOwnProperty(s.name) || visibilityMap[s.name] === true;

                // Sum for future total (guard against nulls)
                if (isVisible) {
                    for (var k = 0; k < futureVals.length; k++) {
                        futureTotals[k] += (futureVals[k] || 0);
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
                    // Line/area: connect to last past point (use trimmed trace's end)
                    if (traces[i].x.length === 0) continue;
                    var lastPastDate = traces[i].x[traces[i].x.length - 1];
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
        var summaryX = chartType === "bar" ? barData.labels.slice() : displayDates.slice();
        var summaryHover = [];
        var summaryY = chartType === "bar"
            ? filterByIndices(totals, barData.validIndices)
            : totals.slice();

        function buildSummaryEntry(rawDate, rawIdx, rawLookup) {
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
                var seriesName = rawData.series[si].name;
                var seriesRawVals = rawLookup[seriesName] || [];
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
            return parts.join("<br>");
        }

        var nPts = chartType === "bar" ? barData.labels.length : displayDates.length;
        for (var idx = 0; idx < nPts; idx++) {
            // Use original ISO date for tooltip (bar labels lack full year info)
            var rawDate = chartType === "bar" ? displayDates[barData.validIndices[idx]] : displayDates[idx];
            var rawIdx = chartType === "bar" ? barData.validIndices[idx] : idx;
            summaryHover.push(buildSummaryEntry(rawDate, rawIdx, rawValsByName));
        }

        if (hasFuture) {
            if (chartType === "bar") {
                for (var fidx = 0; fidx < futureBarData.labels.length; fidx++) {
                    summaryX.push(futureBarData.labels[fidx]);
                    summaryY.push(futureTotals[futureBarData.validIndices[fidx]] || 0);
                    summaryHover.push(buildSummaryEntry(
                        futureDates[futureBarData.validIndices[fidx]],
                        futureBarData.validIndices[fidx],
                        futureRawValsByName
                    ));
                }
            } else {
                for (var fidx = 0; fidx < futureDates.length; fidx++) {
                    summaryX.push(futureDates[fidx]);
                    summaryY.push(futureTotals[fidx] || 0);
                    summaryHover.push(buildSummaryEntry(
                        futureDates[fidx],
                        fidx,
                        futureRawValsByName
                    ));
                }
            }
        }

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
            showlegend: rawData.hideLegend ? false : !stacked,
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
            // Tighten gaps as bar count increases to keep bars visible
            var nBars = displayDates.length + (futureDates ? futureDates.length : 0);
            layout.bargap = nBars > 80 ? 0 : nBars > 40 ? 0.05 : 0.15;
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
        var stacked = rawData.stacked !== false;
        var hasFuture = (rawData.futureDates || []).length > 0;

        // Determine the visible x-range
        var lastDate, startDate, startDateObj;
        if (hasFuture && rawData.futureDates.length > 0) {
            // Include future dates as the end of visible range
            lastDate = rawData.futureDates[rawData.futureDates.length - 1].split('T')[0];
        } else {
            lastDate = rawData.dates[rawData.dates.length - 1].split('T')[0];
        }

        if (days > 0) {
            startDateObj = new Date(rawData.dates[rawData.dates.length - 1].split('T')[0]);
            startDateObj.setDate(startDateObj.getDate() - days);
            startDate = startDateObj.toISOString().split('T')[0];
        }

        // Compute y-axis max from visible data only (using rawData for all chart types)
        var yMax = 0;
        var allDates = rawData.dates.slice();
        var allValues = rawData.series.map(function(s) { return s.values.slice(); });
        if (hasFuture) {
            allDates = allDates.concat(rawData.futureDates);
            allValues = allValues.map(function(vals, i) {
                return vals.concat(rawData.series[i].futureValues || []);
            });
        }
        for (var di = 0; di < allDates.length; di++) {
            var d = allDates[di].split('T')[0];
            if (days > 0 && d < startDate) continue;
            if (days > 0 && d > lastDate) continue;
            if (stacked && chartType !== "line") {
                var stackTotal = 0;
                for (var si = 0; si < allValues.length; si++) {
                    stackTotal += (allValues[si][di] || 0);
                }
                if (stackTotal > yMax) yMax = stackTotal;
            } else {
                for (var si = 0; si < allValues.length; si++) {
                    var val = allValues[si][di] || 0;
                    if (val > yMax) yMax = val;
                }
            }
        }

        fig.layout.xaxis = fig.layout.xaxis || {};
        fig.layout.yaxis = fig.layout.yaxis || {};
        fig.layout.dragmode = 'pan';
        fig.layout.yaxis.fixedrange = true;

        if (chartType === "bar") {
            // Bar charts use category x-axis — set range as category indices
            if (days > 0) {
                var barData = formatDatesForBars(rawData.dates);
                var totalBars = barData.labels.length;
                if (hasFuture) {
                    totalBars += formatDatesForBars(rawData.futureDates).labels.length;
                }
                // Find the first bar index whose date >= startDate
                var startBarIdx = totalBars;
                for (var bi = 0; bi < barData.validIndices.length; bi++) {
                    if (rawData.dates[barData.validIndices[bi]].split('T')[0] >= startDate) {
                        startBarIdx = bi;
                        break;
                    }
                }
                fig.layout.xaxis.range = [startBarIdx - 0.5, totalBars - 0.5];
            } else {
                fig.layout.xaxis.autorange = true;
            }
        } else if (days > 0) {
            fig.layout.xaxis.range = [startDate, lastDate];
        } else {
            fig.layout.xaxis.autorange = true;
        }

        // Set dynamic y-axis range with 10% headroom
        if (yMax > 0) {
            fig.layout.yaxis.range = [0, Math.ceil(yMax * 1.1)];
            fig.layout.yaxis.autorange = false;
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
// Dynamic Y-Axis Scaling for Census Charts on Pan
// ---------------------------------------------------------------------------

window.dash_clientside.censusYAxis = {
    /**
     * Recalculate y-axis range when user pans a census chart horizontally.
     * Only scales UP (never shrinks) to prevent aggressive resizing.
     * Handles both date-axis (area/line) and category-axis (bar) charts.
     * @param {Object} relayoutData - Plotly relayout event data
     * @param {Object} currentFigure - Current figure state
     * @param {Object} rawData - Raw census data from dcc.Store
     */
    updateOnPan: function(relayoutData, currentFigure, rawData, chartType) {
        if (!relayoutData || !currentFigure || !rawData ||
            !rawData.dates || rawData.dates.length === 0) {
            return window.dash_clientside.no_update;
        }

        chartType = chartType || "area";

        // Extract x-axis range from relayout data
        var startRange, endRange;
        if (relayoutData['xaxis.range[0]'] !== undefined &&
            relayoutData['xaxis.range[1]'] !== undefined) {
            startRange = relayoutData['xaxis.range[0]'];
            endRange = relayoutData['xaxis.range[1]'];
        } else if (relayoutData['xaxis.range'] &&
                   relayoutData['xaxis.range'].length === 2) {
            startRange = relayoutData['xaxis.range'][0];
            endRange = relayoutData['xaxis.range'][1];
        } else {
            return window.dash_clientside.no_update;
        }

        var stacked = rawData.stacked !== false;
        // Stacked sum only for stacked area/bar — line is always non-stacked
        var useStackedSum = stacked && chartType !== "line";
        var yMax = 0;

        // Detect bar chart by checking if range values are numeric (category indices)
        var isBarChart = typeof startRange === 'number' ||
                         /^-?\d+(\.\d+)?$/.test(String(startRange));

        if (isBarChart) {
            var barData = formatDatesForBars(rawData.dates);
            var startIdx = Math.max(0, Math.floor(parseFloat(startRange) + 0.5));
            var endIdx = Math.min(barData.validIndices.length - 1,
                                  Math.ceil(parseFloat(endRange) - 0.5));
            for (var bi = startIdx; bi <= endIdx; bi++) {
                var di = barData.validIndices[bi];
                if (di === undefined) continue;
                if (useStackedSum) {
                    var stackTotal = 0;
                    for (var si = 0; si < rawData.series.length; si++) {
                        stackTotal += (rawData.series[si].values[di] || 0);
                    }
                    if (stackTotal > yMax) yMax = stackTotal;
                } else {
                    for (var si = 0; si < rawData.series.length; si++) {
                        var val = rawData.series[si].values[di] || 0;
                        if (val > yMax) yMax = val;
                    }
                }
            }
        } else {
            var startStr = String(startRange).split('T')[0].split(' ')[0];
            var endStr = String(endRange).split('T')[0].split(' ')[0];

            var allDates = rawData.dates.slice();
            var allValues = rawData.series.map(function(s) { return s.values.slice(); });
            if (rawData.futureDates && rawData.futureDates.length > 0) {
                allDates = allDates.concat(rawData.futureDates);
                allValues = allValues.map(function(vals, i) {
                    return vals.concat(rawData.series[i].futureValues || []);
                });
            }

            for (var di = 0; di < allDates.length; di++) {
                var d = allDates[di].split('T')[0];
                if (d < startStr || d > endStr) continue;
                if (useStackedSum) {
                    var stackTotal = 0;
                    for (var si = 0; si < allValues.length; si++) {
                        stackTotal += (allValues[si][di] || 0);
                    }
                    if (stackTotal > yMax) yMax = stackTotal;
                } else {
                    for (var si = 0; si < allValues.length; si++) {
                        var val = allValues[si][di] || 0;
                        if (val > yMax) yMax = val;
                    }
                }
            }
        }

        if (yMax <= 0) return window.dash_clientside.no_update;

        var newYMax = Math.ceil(yMax * 1.1);

        // Skip if y-axis range hasn't changed (prevent relayout loop)
        if (currentFigure.layout && currentFigure.layout.yaxis &&
            currentFigure.layout.yaxis.range &&
            currentFigure.layout.yaxis.range[1] === newYMax) {
            return window.dash_clientside.no_update;
        }

        var newFigure = JSON.parse(JSON.stringify(currentFigure));
        newFigure.layout.yaxis = newFigure.layout.yaxis || {};
        newFigure.layout.yaxis.range = [0, newYMax];
        newFigure.layout.yaxis.autorange = false;

        return newFigure;
    }
};

// ---------------------------------------------------------------------------
// Efficiency chart — machine filter + metric toggle wrapper
// ---------------------------------------------------------------------------

window.dash_clientside.efficiency = {
    /**
     * Internal: prepare filtered data and build figure with unified tooltip.
     */
    _build: function(rawData, smoothPct, chartType, rangeDays, activeMachines, metric, currentFig) {
        // Deep-copy to avoid mutating the store
        var filtered = JSON.parse(JSON.stringify(rawData));

        // 1. Filter series to only active machines
        if (activeMachines && activeMachines.length > 0) {
            filtered.series = filtered.series.filter(function(s) {
                return activeMachines.indexOf(s.name) >= 0;
            });
        } else {
            filtered.series = [];
        }

        // 2. Swap metric if showing raw minutes or beam-on minutes
        var isPercent = true;
        if (metric === "minutes") {
            for (var i = 0; i < filtered.series.length; i++) {
                if (filtered.series[i].rawMinutes) {
                    filtered.series[i].values = filtered.series[i].rawMinutes;
                }
            }
            filtered.yTitle = "Active Minutes";
            isPercent = false;
        } else if (metric === "beam") {
            for (var i = 0; i < filtered.series.length; i++) {
                if (filtered.series[i].beamMinutes) {
                    filtered.series[i].values = filtered.series[i].beamMinutes;
                }
            }
            filtered.yTitle = "Beam On Minutes";
            isPercent = false;
        } else {
            filtered.yTitle = "Utilization %";
        }

        // 3. If no series remain after filtering, return empty figure
        if (filtered.series.length === 0) {
            return {
                data: [],
                layout: {
                    height: filtered.height || 380,
                    xaxis: {visible: false},
                    yaxis: {visible: false},
                    annotations: [{
                        text: "No machines selected",
                        xref: "paper", yref: "paper",
                        x: 0.5, y: 0.5,
                        showarrow: false,
                        font: {size: 14, color: "#9CA3AF"}
                    }],
                    plot_bgcolor: "white",
                    paper_bgcolor: "white"
                }
            };
        }

        // 4. Build figure via census renderer (non-stacked)
        filtered.hideLegend = true;
        var fig = window.dash_clientside.census._buildWithRange(
            filtered, smoothPct, chartType, rangeDays, currentFig
        );

        if (!fig || fig === window.dash_clientside.no_update) return fig;

        // 5. Clamp x-axis to first date with actual data (skip leading nulls)
        //    Prevents empty space before data starts (e.g. Oct 6 2025 cutoff)
        var firstDataIdx = filtered.dates.length;
        for (var si = 0; si < filtered.series.length; si++) {
            var vals = filtered.series[si].values;
            for (var di = 0; di < vals.length; di++) {
                if (vals[di] !== null && vals[di] !== undefined) {
                    if (di < firstDataIdx) firstDataIdx = di;
                    break;
                }
            }
        }
        if (firstDataIdx > 0 && firstDataIdx < filtered.dates.length) {
            var clampDate = filtered.dates[firstDataIdx].split('T')[0];
            if (fig.layout.xaxis && fig.layout.xaxis.range) {
                var currentStart = String(fig.layout.xaxis.range[0]).split('T')[0];
                if (currentStart < clampDate) {
                    fig.layout.xaxis.range[0] = clampDate;
                }
            } else if (fig.layout.xaxis && fig.layout.xaxis.autorange) {
                // "All" range uses autorange — switch to explicit range
                var lastDate = filtered.dates[filtered.dates.length - 1].split('T')[0];
                fig.layout.xaxis.autorange = false;
                fig.layout.xaxis.range = [clampDate, lastDate];
            }
        }

        // 6. Post-process: replace per-trace hover with unified summary tooltip
        var monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

        // Suppress hover on data traces
        for (var t = 0; t < fig.data.length; t++) {
            fig.data[t].hoverinfo = "skip";
            fig.data[t].hovertemplate = undefined;
        }

        // Build summary hover entries per date
        var dates = filtered.dates || [];
        var summaryX = [];
        var summaryY = [];
        var summaryHover = [];

        for (var di = 0; di < dates.length; di++) {
            var dateStr = "";
            var d = new Date(dates[di]);
            if (!isNaN(d)) {
                dateStr = monthNames[d.getMonth()] + " " + d.getDate() + ", " + d.getFullYear();
            }
            var parts = ["<b>" + dateStr + "</b>"];
            var maxVal = 0;
            for (var si = 0; si < filtered.series.length; si++) {
                var s = filtered.series[si];
                var val = s.values[di];
                if (val === null || val === undefined) continue;
                var displayVal = isPercent ? val.toFixed(1) + "%" : Math.round(val) + " min";
                parts.push("<span style='color:" + s.color + "'>\u25A0</span> " + s.name + ": " + displayVal);
                if (val > maxVal) maxVal = val;
            }
            summaryX.push(dates[di]);
            summaryY.push(maxVal);
            summaryHover.push(parts.join("<br>"));
        }

        fig.data.push({
            x: summaryX,
            y: summaryY,
            customdata: summaryHover,
            name: "",
            mode: "lines",
            line: {color: "transparent", width: 0},
            hovertemplate: "%{customdata}<extra></extra>",
            showlegend: false
        });

        return fig;
    },

    /**
     * Filter machines, swap metric, then delegate to census renderer.
     * Debounced for smooth slider interaction.
     */
    renderWithFilters: function(rawData, smoothPct, chartType, rangeDays, activeMachines, metric, currentFig) {
        if (!rawData || !rawData.series) {
            return window.dash_clientside.no_update;
        }

        var chartElId = rawData.chartId || 'ops-chart-efficiency';
        var debounceKey = '_effDebounce_' + chartElId;
        var self = window.dash_clientside.efficiency;

        // Debounce: skip intermediate slider ticks
        if (window[debounceKey]) clearTimeout(window[debounceKey]);
        window[debounceKey] = setTimeout(function() {
            requestAnimationFrame(function() { setTimeout(function() {
                var fig = self._build(rawData, smoothPct, chartType, rangeDays, activeMachines, metric, currentFig);
                if (fig && fig !== window.dash_clientside.no_update) {
                    var el = document.getElementById(chartElId);
                    var plotEl = el && el.querySelector('.js-plotly-plot');
                    if (plotEl) Plotly.react(plotEl, fig.data, fig.layout);
                }
            }, 0); });
        }, 150);

        // First render — render immediately
        var el = document.getElementById(chartElId);
        var plotEl = el && el.querySelector('.js-plotly-plot');
        if (!plotEl || !plotEl.data || !plotEl.data.length) {
            return self._build(rawData, smoothPct, chartType, rangeDays, activeMachines, metric, currentFig);
        }
        return window.dash_clientside.no_update;
    },

    /**
     * Y-axis rescaling on pan — applies same filter/swap before delegating.
     */
    updateOnPan: function(relayoutData, currentFigure, rawData, activeMachines, metric, chartType) {
        if (!rawData || !rawData.series) {
            return window.dash_clientside.no_update;
        }

        var filtered = JSON.parse(JSON.stringify(rawData));

        if (activeMachines && activeMachines.length > 0) {
            filtered.series = filtered.series.filter(function(s) {
                return activeMachines.indexOf(s.name) >= 0;
            });
        }

        if (metric === "minutes") {
            for (var i = 0; i < filtered.series.length; i++) {
                if (filtered.series[i].rawMinutes) {
                    filtered.series[i].values = filtered.series[i].rawMinutes;
                }
            }
        } else if (metric === "beam") {
            for (var i = 0; i < filtered.series.length; i++) {
                if (filtered.series[i].beamMinutes) {
                    filtered.series[i].values = filtered.series[i].beamMinutes;
                }
            }
        }

        return window.dash_clientside.censusYAxis.updateOnPan(
            relayoutData, currentFigure, filtered, chartType
        );
    }
};

// ---------------------------------------------------------------------------
// Bar-mode aggregation guard — disables Daily for long ranges in bar mode
// ---------------------------------------------------------------------------

window.dash_clientside.barAggGuard = {
    /**
     * Disable the "Daily" aggregation option when bar chart type is active
     * and a long time range is selected (6mo, 1y, All).
     * Auto-switches from Daily → Weekly when disabled.
     * @returns [data, value] for the aggregation SegmentedControl
     */
    update: function(chartType, rangeDays, currentAgg) {
        var longRange = ['180', '365', '0'].indexOf(rangeDays) >= 0;
        var dailyDisabled = chartType === 'bar' && longRange;
        var data = [
            {value: 'D', label: 'Daily', disabled: dailyDisabled},
            {value: 'W', label: 'Weekly'},
            {value: 'M', label: 'Monthly'}
        ];
        var agg = currentAgg;
        if (dailyDisabled && currentAgg === 'D') {
            agg = 'W';
        }
        return [data, agg];
    }
};
