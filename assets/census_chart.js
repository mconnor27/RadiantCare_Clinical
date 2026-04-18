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
    smoothChartWithType: function(rawData, smoothPct, chartType, currentFig, stackOverride) {
        if (!rawData || !rawData.series || rawData.series.length === 0) {
            if (rawData && rawData.emptyMessage) {
                return {
                    data: [],
                    layout: Object.assign({}, window._defaultLayout || {}, {
                        height: rawData.height || 320,
                        xaxis: {visible: false},
                        yaxis: {visible: false},
                        annotations: [{
                            text: rawData.emptyMessage,
                            xref: "paper", yref: "paper",
                            x: 0.5, y: 0.5,
                            showarrow: false,
                            font: {size: 14, color: "#9CA3AF"}
                        }]
                    })
                };
            }
            return window.dash_clientside.no_update;
        }

        chartType = chartType || "area";
        var dates = rawData.dates;
        var futureDates = rawData.futureDates || [];
        var yTitle = rawData.yTitle || "Unique Patients";
        var hasFuture = futureDates.length > 0;
        // stackOverride: "stacked" | "grouped" | undefined
        var stacked;
        if (stackOverride === "grouped") {
            stacked = false;
        } else if (stackOverride === "stacked") {
            stacked = true;
        } else {
            stacked = rawData.stacked !== false;  // default true
        }
        // Single-series (e.g. "Total" dim) has nothing to stack against — render
        // as overlay so the fill uses the lighter 0.15 alpha instead of 0.5.
        if (stacked && rawData.series && rawData.series.length <= 1) {
            stacked = false;
        }

        // TEMPORARILY DISABLED: Downsampling was causing last data points to be dropped
        // TODO: Fix downsampling to ensure dates and values arrays have matching lengths
        var maxPoints = 10000;  // Effectively disable downsampling
        var step = dates.length > maxPoints ? Math.ceil(dates.length / maxPoints) : 1;
        var displayDates = step > 1 ? downsample(dates, step) : dates;

        // Detect aggregation level for smart x-axis formatting and hover labels
        var aggLevel = detectAggLevel(displayDates);

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
        var COLORWAY = ["#7C2A83", "#2196F3", "#F44336", "#4CAF50", "#FF9800", "#00BCD4", "#9C27B0", "#795548"];
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

        // Pre-compute individual smoothed values for each series (needed for
        // manual cumulative stacking and totals).
        var seriesSmoothed = [];
        var seriesDisplay = [];
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
            seriesSmoothed.push(yVals);
            seriesDisplay.push(displayVals);
        }

        // Past data traces (hoverinfo:"skip" — hover handled by summary trace)
        for (var i = 0; i < renderSeries.length; i++) {
            var s = renderSeries[i];
            var displayVals = seriesDisplay[i];
            var yVals = seriesSmoothed[i];
            var isVisible = !visibilityMap.hasOwnProperty(s.name) || visibilityMap[s.name] === true;

            rawValsByName[s.name] = displayVals;

            // Sum for total trace (smoothed for rendering, raw for hover)
            // Guard against null values (pre/post-active periods)
            if (isVisible) {
                for (var k = 0; k < yVals.length; k++) {
                    if (stacked) {
                        totals[k] += (yVals[k] || 0);
                        rawTotals[k] += (displayVals[k] || 0);
                    } else {
                        // For non-stacked, track the max across series for summary trace positioning
                        totals[k] = Math.max(totals[k], (yVals[k] || 0));
                        rawTotals[k] = Math.max(rawTotals[k], (displayVals[k] || 0));
                    }
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
                    marker: {color: s.color, line: {color: "rgba(255,255,255,0.6)", width: 0.5}},
                    hoverinfo: "skip"
                };
            } else if (chartType === "line") {
                // Line chart — hover handled by summary trace
                traceObj = {
                    x: traceDates,
                    y: traceY,
                    customdata: traceRaw,
                    name: s.name,
                    mode: traceDates.length <= 3 ? "lines+markers" : "lines",
                    line: {color: s.color, width: 2},
                    connectgaps: true,
                    hoverinfo: "skip"
                };
                if (traceDates.length <= 3) traceObj.marker = {size: 8};
            } else if (stacked) {
                // Stacked area — use stackgroup for proper legend toggling.
                // Colors are reassigned in _buildWithRange after visibility
                // filtering, with template:{} to prevent Plotly auto-coloring.
                traceObj = {
                    x: traceDates,
                    y: traceY,
                    customdata: traceRaw,
                    name: s.name,
                    mode: "lines",
                    line: {color: s.color, width: 1.5},
                    fillcolor: hexToRgba(s.color, 0.5),
                    stackgroup: "one",
                    connectgaps: true,
                    hoverinfo: "skip"
                };
            } else {
                // Overlay area (non-stacked)
                traceObj = {
                    x: traceDates,
                    y: traceY,
                    customdata: traceRaw,
                    name: s.name,
                    mode: traceDates.length <= 3 ? "lines+markers" : "lines",
                    line: {color: s.color, width: 2},
                    fillcolor: hexToRgba(s.color, 0.15),
                    fill: "tozeroy",
                    connectgaps: true,
                    hoverinfo: "skip"
                };
                if (traceDates.length <= 3) traceObj.marker = {size: 8};
            }

            // Link main trace with its future projection via legendgroup
            traceObj.legendgroup = s.name;

            // Hide series with no data (all zero/null).
            // For grouped bars, set visible:false so Plotly doesn't allocate
            // bar width to invisible series.
            var hasData = false;
            for (var hd = 0; hd < s.values.length; hd++) {
                if (s.values[hd] > 0) { hasData = true; break; }
            }
            if (!hasData) {
                traceObj.showlegend = false;
                if (chartType === "bar" && !stacked) {
                    traceObj.visible = false;
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
                        marker: {color: s.color, opacity: 0.4, line: {color: "rgba(255,255,255,0.6)", width: 0.5}},
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
                        connectgaps: true,
                        line: {color: s.color, width: 1, dash: "dot"},
                        fillcolor: chartType === "line" ? "transparent" : hexToRgba(s.color, 0.2),
                        showlegend: false,
                        hoverinfo: "skip"
                    };
                    if (chartType !== "line") {
                        futureTraceObj.stackgroup = "future";
                    }
                }

                // Link to main trace so legend toggle hides both
                futureTraceObj.legendgroup = s.name;

                traces.push(futureTraceObj);
            }
        }

        // Build summary hover text per date point (unified tooltip for all modes)
        var monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
        var summaryX = chartType === "bar" ? barData.labels.slice() : displayDates.slice();
        var summaryHover = [];
        var summaryY = chartType === "bar"
            ? filterByIndices(totals, barData.validIndices)
            : totals.slice();

        // Detect if values are fractional (e.g. median days, percentages) vs integer counts
        var isPercent = rawData.yTitle && rawData.yTitle.indexOf('%') >= 0;
        var isDollar = rawData.yTitle && rawData.yTitle.indexOf('$') >= 0;
        var isFractional = isPercent || (rawData.yTitle && (
            rawData.yTitle.toLowerCase().indexOf('median') >= 0 ||
            rawData.yTitle.toLowerCase().indexOf('rate') >= 0 ||
            rawData.yTitle.toLowerCase().indexOf('per ') >= 0 ||
            rawData.yTitle.toLowerCase().indexOf('days') >= 0
        ));
        var isDays = rawData.yTitle && rawData.yTitle.toLowerCase().indexOf('days') >= 0;
        var valueSuffix = isPercent ? "%" : isDays ? " days" : "";

        function formatVal(v) {
            if (v === null || v === undefined || isNaN(v)) return isDollar ? "$0" : "0";
            if (isDollar) return "$" + Math.round(v).toLocaleString();
            if (isFractional) return v.toFixed(1) + valueSuffix;
            return Math.round(v) + valueSuffix;
        }

        function buildSummaryEntry(rawDate, rawIdx, rawLookup) {
            var dateStr = "";
            if (rawDate) {
                // Parse ISO date string manually to avoid UTC timezone shift
                var parsed = parseIsoDate(rawDate);
                if (parsed.valid) {
                    if (aggLevel === "Y") {
                        dateStr = String(parsed.year);
                    } else if (aggLevel === "M") {
                        dateStr = monthNames[parsed.month] + " " + parsed.year;
                    } else {
                        dateStr = monthNames[parsed.month] + " " + parsed.day + ", " + parsed.year;
                    }
                } else {
                    dateStr = String(rawDate);
                }
            }
            var parts = dateStr ? ["<b>" + dateStr + "</b>"] : [];
            var total = 0;
            var visCount = 0;
            for (var si = 0; si < rawData.series.length; si++) {
                var seriesName = rawData.series[si].name;
                var seriesRawVals = rawLookup[seriesName] || [];
                var rawVal = seriesRawVals[rawIdx];
                var isVis = !visibilityMap.hasOwnProperty(rawData.series[si].name) ||
                            visibilityMap[rawData.series[si].name] === true;
                if (rawVal !== null && rawVal !== undefined && rawVal !== 0 && isVis) {
                    parts.push("<span style='color:" + rawData.series[si].color + "'>\u25A0</span> " + rawData.series[si].name + ": " + formatVal(rawVal));
                    total += rawVal;
                    visCount++;
                }
            }
            // Only show total line for stacked charts with multiple visible series
            if (stacked && visCount > 1 && total > 0) {
                parts.push("<b>Total: " + formatVal(total) + "</b>");
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

        if (chartType === "bar") {
            // For bar charts, attach summary hover directly to each bar trace
            // so hovering any bar in a grouped set triggers the tooltip.
            var pastLen = barData ? barData.labels.length : 0;
            var pastHover = summaryHover.slice(0, pastLen);
            var futureHover = summaryHover.slice(pastLen);
            for (var bt = 0; bt < traces.length; bt++) {
                if (traces[bt].type === "bar") {
                    traces[bt].hoverinfo = undefined;
                    var isFuture = traces[bt].name && traces[bt].name.indexOf("(scheduled)") >= 0;
                    traces[bt].customdata = isFuture ? futureHover : pastHover;
                    traces[bt].hovertemplate = "%{customdata}<extra></extra>";
                }
            }
        } else {
            // Line/area: invisible summary hover trace
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
        }

        var smoothed = smoothPct > 0;

        var layout = {
            template: {},
            xaxis: {showgrid: false, showspikes: false, nticks: 12},
            yaxis: {gridcolor: "#E5E7EB"},
            showlegend: rawData.hideLegend ? false : true,
            legend: {
                orientation: "h",
                yanchor: "bottom",
                y: 1.02,
                xanchor: "left",
                x: 0
            },
            margin: {l: stacked ? 28 : 40, r: 8, t: rawData.hideLegend ? 4 : 8, b: 20},
            plot_bgcolor: "white",
            paper_bgcolor: "white",
            font: {family: "Inter, system-ui, sans-serif", size: 12, color: "#374151"},
            hovermode: chartType === "bar" ? "closest" : "x",
            hoverlabel: {
                align: "left",
                bgcolor: "white",
                bordercolor: "#E5E7EB",
                font: {color: "#374151", size: 12, family: "Inter, system-ui, sans-serif"}
            }
        };

        // Prefix/suffix for y-axis on percentage or dollar charts
        if (rawData.yTickSuffix) {
            layout.yaxis.ticksuffix = rawData.yTickSuffix;
        } else if (!stacked && rawData.yTitle && rawData.yTitle.indexOf('%') >= 0) {
            layout.yaxis.ticksuffix = '%';
        }
        if (isDollar) {
            layout.yaxis.tickprefix = '$';
        }

        // Add barmode for bar charts
        if (chartType === "bar") {
            // Use "stack" for single-series to avoid grouped dead space
            var visibleSeriesCount = renderSeries.filter(function(s) {
                var hasData = false;
                for (var vi = 0; vi < s.values.length; vi++) { if (s.values[vi] > 0) { hasData = true; break; } }
                return hasData;
            }).length;
            layout.barmode = stacked ? "stack" : (visibleSeriesCount <= 1 ? "stack" : "group");
            // Scale gaps by bar count, then bump up for coarser aggregation
            var nBars = barData.labels.length + (futureDates ? formatDatesForBars(futureDates).labels.length : 0);
            var baseGap;
            if (nBars > 80) {
                baseGap = 0;
            } else if (nBars > 40) {
                baseGap = 0.08;
            } else {
                baseGap = 0.15;
            }
            // Coarser aggregation → wider gaps (fewer bars = more room)
            if (aggLevel === "M" && baseGap < 0.2) baseGap = Math.max(baseGap, 0.2);
            if (aggLevel === "Y" && baseGap < 0.25) baseGap = Math.max(baseGap, 0.25);
            if (aggLevel === "W" && baseGap < 0.15) baseGap = 0.15;
            layout.bargap = baseGap;
            layout.bargroupgap = stacked ? 0 : 0;
            layout.xaxis.type = "category";
            layout.xaxis.tickangle = 0;
            // Scale tick count to bar density — labels are already abbreviated
            // by formatDatesForBars so we just need enough spacing
            if (aggLevel === "Y") {
                layout.xaxis.nticks = Math.min(nBars, 20);
            } else if (aggLevel === "M") {
                layout.xaxis.nticks = nBars > 36 ? 6 : nBars > 24 ? 8 : nBars > 12 ? 10 : nBars;
            } else {
                layout.xaxis.nticks = nBars > 50 ? 6 : nBars > 24 ? 8 : nBars > 12 ? 10 : nBars;
            }
            layout.xaxis.automargin = true;
            layout.margin.r = 20;
        } else {
            // Line/area charts — keep Plotly's native datetime axis
            // Just control tick density and format
            if (aggLevel === "Y") {
                // Yearly: force year-only tick format
                layout.xaxis.tickformat = "%Y";
                layout.xaxis.dtick = "M12";
            }
            layout.xaxis.tickangle = 0;
            layout.xaxis.automargin = true;
        }

        // Dynamic y-axis range with 10% headroom
        // Use stacked totals only when visually stacked (area/bar); for line mode use individual trace max
        var yMaxSCWT = 0;
        if (stacked && chartType !== "line") {
            for (var yi = 0; yi < totals.length; yi++) {
                if (totals[yi] > yMaxSCWT) yMaxSCWT = totals[yi];
            }
        } else {
            for (var ti = 0; ti < traces.length; ti++) {
                var tr = traces[ti];
                // Skip only the invisible summary trace
                if (tr.line && tr.line.color === "transparent") continue;
                var isVis = !tr.name || !visibilityMap.hasOwnProperty(tr.name) || visibilityMap[tr.name] === true;
                if (!isVis) continue;
                var yArr = tr.y || [];
                for (var yj = 0; yj < yArr.length; yj++) {
                    if (yArr[yj] !== null && yArr[yj] !== undefined && yArr[yj] > yMaxSCWT) yMaxSCWT = yArr[yj];
                }
            }
        }
        if (rawData.yRange) {
            // Explicit fixed range takes precedence (e.g., [0, 100] for percentages)
            layout.yaxis.range = rawData.yRange;
            layout.yaxis.autorange = false;
        } else if (yMaxSCWT > 0) {
            var headroom = (rawData.showBarTotals && chartType === "bar") ? 1.13 : 1.1;
            layout.yaxis.range = [0, Math.ceil(yMaxSCWT * headroom)];
            layout.yaxis.autorange = false;
        }

        // Bar total annotations on top of stacked bars
        if (rawData.showBarTotals && chartType === "bar" && stacked) {
            var barTotalAnnotations = [];
            var barXLabels = barData.labels;
            for (var ai = 0; ai < barXLabels.length; ai++) {
                var origIdx = barData.validIndices[ai];
                var t = totals[origIdx];
                if (t > 0) {
                    barTotalAnnotations.push({
                        x: barXLabels[ai], y: t,
                        text: "<b>" + formatVal(t) + "</b>",
                        showarrow: false, yshift: 8,
                        font: {size: 11, color: "#374151", family: "Inter, system-ui, sans-serif"}
                    });
                }
            }
            layout.annotations = barTotalAnnotations;
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
    _buildWithRange: function(rawData, smoothPct, chartType, rangeDays, currentFig, stackOverride) {
        var fig = window.dash_clientside.census.smoothChartWithType(rawData, smoothPct, chartType, currentFig, stackOverride);

        if (fig === window.dash_clientside.no_update || !rawData || !rawData.dates || rawData.dates.length === 0) {
            return fig;
        }

        var days = parseInt(rangeDays) || 0;
        var stacked = stackOverride === "grouped" ? false : stackOverride === "stacked" ? true : rawData.stacked !== false;
        if (stacked && rawData.series && rawData.series.length <= 1) stacked = false;
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
            var _lp = parseIsoDate(rawData.dates[rawData.dates.length - 1]);
            startDateObj = _lp.valid ? new Date(_lp.year, _lp.month, _lp.day - days) : new Date();
            startDate = localDateToIso(startDateObj);
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

        // Set dynamic y-axis range with 10% headroom (skip if explicit range set)
        if (rawData.yRange) {
            fig.layout.yaxis.range = rawData.yRange;
            fig.layout.yaxis.autorange = false;
        } else if (yMax > 0) {
            fig.layout.yaxis.range = [0, Math.ceil(yMax * 1.1)];
            fig.layout.yaxis.autorange = false;
        }

        // Hide legend entries for series with no data in the visible range
        var seriesHasData = {};
        for (var si = 0; si < rawData.series.length; si++) {
            var sName = rawData.series[si].name;
            var hasAny = false;
            for (var di = 0; di < allDates.length; di++) {
                var d = allDates[di].split('T')[0];
                if (days > 0 && d < startDate) continue;
                if (days > 0 && d > lastDate) continue;
                if (allValues[si][di] > 0) { hasAny = true; break; }
            }
            seriesHasData[sName] = hasAny;
        }
        for (var ti = 0; ti < fig.data.length; ti++) {
            var tName = fig.data[ti].name;
            if (tName && seriesHasData.hasOwnProperty(tName)) {
                if (!seriesHasData[tName]) {
                    fig.data[ti].showlegend = false;
                    // For grouped bars, fully hide so Plotly doesn't allocate width
                    if (chartType === "bar" && !stacked) {
                        fig.data[ti].visible = false;
                    }
                } else if (fig.data[ti].visible === false) {
                    // Re-show if it was previously hidden but now has data
                    fig.data[ti].visible = true;
                    fig.data[ti].showlegend = true;
                }
            }
        }

        // Dynamic color reassignment: after time-range visibility filtering,
        // assign distinct COLORWAY colors to only the visible traces.
        // Hidden traces get transparent lines so they don't bleed through.
        if (rawData.dynamicColors) {
            var COLORWAY = ["#7C2A83", "#2196F3", "#F44336", "#4CAF50", "#FF9800", "#00BCD4", "#9C27B0", "#795548"];
            var colorMap = {};  // name → reassigned color (for tooltip fix)
            var visIdx = 0;
            for (var ci = 0; ci < fig.data.length; ci++) {
                var tr = fig.data[ci];
                if (!tr.name) continue;
                if (tr.showlegend === false) {
                    tr.line = tr.line || {};
                    tr.line.color = "rgba(0,0,0,0)";
                    tr.line.width = 0;
                    if (tr.fillcolor) tr.fillcolor = "rgba(0,0,0,0)";
                    continue;
                }
                var c = COLORWAY[visIdx % COLORWAY.length];
                visIdx++;
                colorMap[tr.name] = c;
                tr.line = tr.line || {};
                tr.line.color = c;
                if (tr.marker) tr.marker.color = c;
                if (tr.fillcolor) {
                    tr.fillcolor = hexToRgba(c, chartType === "area" && stacked ? 0.5 : 0.15);
                }
                if (tr.type === "bar" && tr.marker) {
                    tr.marker.color = c;
                }
            }
            // Fix tooltip colors in the summary trace (first trace with hovertemplate)
            for (var ti = 0; ti < fig.data.length; ti++) {
                var tr = fig.data[ti];
                if (tr.hovertemplate && tr.customdata) {
                    for (var hi = 0; hi < tr.customdata.length; hi++) {
                        var html = tr.customdata[hi];
                        if (typeof html === "string") {
                            for (var name in colorMap) {
                                if (colorMap.hasOwnProperty(name)) {
                                    // Replace color in: <span style='color:#OLD'>■</span> Name
                                    var re = new RegExp("color:#[0-9a-fA-F]{6}('>\\u25A0</span> " + name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ")");
                                    html = html.replace(re, "color:" + colorMap[name] + "$1");
                                }
                            }
                            tr.customdata[hi] = html;
                        }
                    }
                    break;  // only one summary trace
                }
            }
        }

        return fig;
    },

    smoothChartWithTypeAndRange: function(rawData, smoothPct, chartType, rangeDays, stackOverride, currentFig) {
        if (!rawData || !rawData.dates || rawData.dates.length === 0) {
            return window.dash_clientside.census._buildWithRange(rawData, smoothPct, chartType, rangeDays, currentFig, stackOverride);
        }

        // Chart element ID: use rawData.chartId if provided, fallback to ops-chart-volume
        var chartElId = rawData.chartId || 'ops-chart-volume';
        var debounceKey = '_censusDebounce_' + chartElId;

        // Debounce: skip intermediate slider ticks, yield to browser for paint before render
        if (window[debounceKey]) clearTimeout(window[debounceKey]);
        window[debounceKey] = setTimeout(function() {
            // rAF queues after pending input/paint, setTimeout(0) yields one more frame
            requestAnimationFrame(function() { setTimeout(function() {
                var fig = window.dash_clientside.census._buildWithRange(rawData, smoothPct, chartType, rangeDays, currentFig, stackOverride);
                if (fig && fig !== window.dash_clientside.no_update) {
                    var el = document.getElementById(chartElId);
                    var plotEl = el && el.querySelector('.js-plotly-plot');
                    if (plotEl) Plotly.react(plotEl, fig.data, fig.layout, {displayModeBar: false});
                }
            }, 0); });
        }, 150);

        // First render (no existing plot) — render immediately
        var el = document.getElementById(chartElId);
        var plotEl = el && el.querySelector('.js-plotly-plot');
        if (!plotEl || !plotEl.data || !plotEl.data.length) {
            return window.dash_clientside.census._buildWithRange(rawData, smoothPct, chartType, rangeDays, currentFig, stackOverride);
        }
        return window.dash_clientside.no_update;
    },

    /**
     * Render variant without a per-card range picker — the server has already
     * filtered the store to the desired date window, so we show everything in it.
     */
    smoothChartNoRange: function(rawData, smoothPct, chartType, stackOverride, currentFig) {
        return window.dash_clientside.census.smoothChartWithTypeAndRange(
            rawData, smoothPct, chartType, "0", stackOverride, currentFig
        );
    },

    smoothCumulativeNoRange: function(rawData, smoothPct, currentFig) {
        return window.dash_clientside.census.smoothCumulativeWithRange(
            rawData, smoothPct, "0", currentFig
        );
    },

    /**
     * Tighten a figure's horizontal legend so it packs more entries per row.
     * The home page's 4-card grid makes each chart narrow; the default legend
     * spacing wraps at 4-5 entries. Only used by home — other pages keep the
     * standard entry width.
     */
    _homeCompactLegend: function(fig) {
        if (!fig || fig === window.dash_clientside.no_update) return fig;
        if (!fig.layout) fig.layout = {};

        // Left margin is pinned to a constant so Total/Dept/MD slices all
        // align. The shared `_buildWithRange` uses `l: stacked ? 28 : 40`,
        // which makes Total mode (single series, unstacked) wider than
        // Dept/MD (stacked) — a visible hop when toggling.
        var legendShown = fig.layout.showlegend !== false;
        if (!legendShown) {
            // No legend → reclaim the top space. Plotly.react deep-merges
            // layout.legend across renders, so an `Object.assign({}, lg, {yref:
            // "container", y: 0.99, …})` from a prior sliced render sticks
            // around even when we later pass `legend: {}`. Explicitly write
            // back the Plotly defaults for every key the sliced branch mutates
            // so the merged config matches a fresh render.
            fig.layout.showlegend = false;
            fig.layout.legend = {
                orientation: "v",
                xref: "paper", xanchor: "auto", x: 1.02,
                yref: "paper", yanchor: "auto", y: 1,
                entrywidth: null,
                entrywidthmode: "pixels",
                tracegroupgap: 10,
                itemsizing: "trace",
                indentation: 0,
                itemwidth: 30
            };
            var m = fig.layout.margin || {};
            fig.layout.margin = {
                l: 36,
                r: (m.r != null) ? m.r : 8,
                t: 10,
                b: (m.b != null) ? m.b : 20,
                // Disable Plotly's autoexpand, which otherwise leaves the prior
                // render's expanded top margin in place when we shrink t.
                autoexpand: false
            };
            // Unique uirevision per branch so Plotly discards preserved layout
            // state from the other branch on toggle.
            fig.layout.uirevision = "home-nolegend";
            fig.layout.autosize = true;
            return fig;
        }

        var lg = fig.layout.legend || {};
        fig.layout.legend = Object.assign({}, lg, {
            orientation: "h",
            // Anchor the legend to the container (fixed CSS height) rather
            // than the plot area. This avoids the "legend jumps after first
            // interaction" bug — plot-area coords depend on Plotly measuring
            // the plot, which isn't finalized on the first render.
            xanchor: "left", x: 0,
            yref: "container", yanchor: "top", y: 0.99,
            entrywidth: 0,
            entrywidthmode: "pixels",
            tracegroupgap: 0,
            itemsizing: "constant",
            indentation: 0,
            itemwidth: 15
        });
        // Top margin holds the legend comfortably. 46px fits either a single
        // row (18px) with breathing room or a wrapped 2-row legend (~36px
        // tall) without clipping row 2 into the plot area.
        fig.layout.margin = Object.assign({}, fig.layout.margin || {}, {t: 46, l: 36});
        // Pair with the no-legend uirevision so Plotly re-lays out the plot
        // area when the user toggles between Total and sliced modes.
        fig.layout.uirevision = "home-legend";

        // Home-only: replace the line-segment legend swatch with a small square
        // color chip. Plotly's built-in `itemwidth` is clamped to ~30px so the
        // line swatch can't be shortened natively; instead, we hide each line
        // trace from the legend and add a marker-only proxy trace (symbol:
        // "square") that shows up as a compact colored square. The proxy shares
        // `legendgroup` with the real trace so legend clicks still toggle
        // visibility on the actual line. Bar traces already render a square
        // swatch natively, so we skip them.
        if (fig.data && fig.data.length) {
            var proxies = [];
            for (var i = 0; i < fig.data.length; i++) {
                var t = fig.data[i];
                if (!t || !t.name) continue;
                if (t.showlegend === false) continue;
                if (t.type === "bar") continue;
                var color = (t.line && t.line.color) ||
                            (t.marker && t.marker.color);
                if (typeof color !== "string") continue;  // skip per-point arrays
                var group = t.legendgroup || t.name;
                t.showlegend = false;
                t.legendgroup = group;
                // Shorten 4-digit year labels to 2-digit with apostrophe
                // ("2026" → "'26") so more fit on one row. Leave non-year
                // names (MD surnames, department names) unchanged.
                var displayName = t.name;
                var yrMatch = String(displayName).match(/^(\d{4})$/);
                if (yrMatch) displayName = "'" + yrMatch[1].slice(-2);
                proxies.push({
                    type: "scatter",
                    mode: "markers",
                    x: [null], y: [null],
                    name: displayName,
                    marker: {symbol: "square", size: 11, color: color,
                             line: {width: 0}},
                    showlegend: true,
                    legendgroup: group,
                    legendrank: t.legendrank,
                    hoverinfo: "skip"
                });
            }
            if (proxies.length) fig.data = fig.data.concat(proxies);
        }
        return fig;
    },

    /**
     * Home trend wrapper — runs the standard `smoothChartNoRange` and then
     * tightens the legend so 5-6 MDs (or other dimension values) fit on one row.
     */
    homeTrend: function(rawData, smoothPct, chartType, stackOverride, currentFig) {
        var fig = window.dash_clientside.census.smoothChartNoRange(
            rawData, smoothPct, chartType, stackOverride, currentFig
        );
        fig = window.dash_clientside.census._homeCompactLegend(fig);

        // Home-scoped x-axis override:
        //  - Line/area: Plotly's date axis auto-adds a "year" parent label
        //    (e.g. "2026") when tickformat omits the year. Switch to a
        //    category axis with explicit tickvals/ticktext to suppress it.
        //  - Bar: existing category labels ("3/16 '26") are too dense for
        //    the narrow home-card width. Thin to ~7 ticks with readable
        //    "Jan 11" labels (year suffix only on year transitions).
        if (fig && fig !== window.dash_clientside.no_update && fig.layout
            && rawData && rawData.dates && rawData.dates.length) {
            var hDates = rawData.dates;
            var nH = hDates.length;
            var firstH = parseIsoDate(hDates[0]);
            var lastH = parseIsoDate(hDates[nH - 1]);
            var spanDaysH = 0;
            if (firstH.valid && lastH.valid) {
                spanDaysH = Math.round(
                    (Date.UTC(lastH.year, lastH.month, lastH.day) -
                     Date.UTC(firstH.year, firstH.month, firstH.day)) / 86400000
                );
            }
            // For multi-year views (>5y) fall back to just "2026" style.
            var useYearOnlyH = spanDaysH > 1825;
            var aggLevelH = (typeof detectAggLevel === "function") ? detectAggLevel(hDates) : "D";
            var monthNamesH = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

            // Bar mode: traces use the formatted bar-label strings as their
            // x-values (from formatDatesForBars). Map our stride indices to
            // those strings so tickvals match the category axis.
            var barLabelsArr = null;
            if (chartType === "bar" && typeof formatDatesForBars === "function") {
                var fb = formatDatesForBars(hDates);
                barLabelsArr = fb.labels || null;
            }

            var strideH = Math.max(1, Math.round(nH / 7));
            var hTickVals = [], hTickText = [];
            for (var hi = 0; hi < nH; hi += strideH) {
                var hp = parseIsoDate(hDates[hi]);
                if (!hp.valid) continue;
                var lblH;
                if (useYearOnlyH) {
                    lblH = String(hp.year);
                } else if (chartType === "bar" && aggLevelH === "M") {
                    // Monthly bars: "Apr" alone (the 1st-of-month day adds noise).
                    lblH = monthNamesH[hp.month];
                } else {
                    lblH = monthNamesH[hp.month] + " " + hp.day;
                }
                if (chartType === "bar") {
                    if (barLabelsArr && barLabelsArr[hi] !== undefined) {
                        hTickVals.push(barLabelsArr[hi]);
                        hTickText.push(lblH);
                    }
                } else {
                    hTickVals.push(hDates[hi]);
                    hTickText.push(lblH);
                }
            }

            fig.layout.xaxis = fig.layout.xaxis || {};
            fig.layout.xaxis.tickmode = "array";
            fig.layout.xaxis.tickvals = hTickVals;
            fig.layout.xaxis.ticktext = hTickText;
            fig.layout.xaxis.tickformat = null;
            fig.layout.xaxis.dtick = null;
            // Pin bottom padding so Total and sliced modes match. Plotly's
            // default automargin otherwise expands the bottom by a few px when
            // the legend changes, producing visibly uneven plot heights in a
            // side-by-side row of home cards.
            fig.layout.xaxis.automargin = false;
            fig.layout.margin = Object.assign({}, fig.layout.margin || {}, {b: 24});
            if (chartType !== "bar") {
                fig.layout.xaxis.type = "category";
                fig.layout.xaxis.categoryorder = "array";
                fig.layout.xaxis.categoryarray = hDates;
            }
            // Bar mode already has type:"category" + categoryarray from
            // smoothChartWithType — leave it alone.
        }

        // Plotly.react (invoked by dcc.Graph) sometimes preserves the prior
        // render's plot-area geometry even when margin/legend change and
        // uirevision flips. After Dash applies the figure, call
        // Plotly.Plots.resize on every home trend plot to force a fresh
        // plot-area computation from the new margin.
        if (typeof window !== "undefined" && window.Plotly && window.Plotly.Plots) {
            setTimeout(function() {
                try {
                    var els = document.querySelectorAll('[id^="home-chart-"][id$="-trend"]');
                    for (var i = 0; i < els.length; i++) {
                        var p = els[i].querySelector(".js-plotly-plot") || els[i];
                        if (p && p._fullLayout) window.Plotly.Plots.resize(p);
                    }
                } catch (e) {}
            }, 80);
        }
        return fig;
    },

    /**
     * Home cumulative dispatcher — routes prior-mode stores (current_year YoY)
     * to the shared cumulative.renderCumulative, and slice-mode stores (other
     * presets) to the per-series cumulative line renderer. Accepts chartType,
     * grouping, and prior-periods so both paths feel like the other pages'
     * cumulative cards.
     */
    homeCumulative: function(rawData, smoothPct, chartType, maxPrior, projectOn, currentFig) {
        if (!rawData) return window.dash_clientside.no_update;
        chartType = chartType || "line";
        // Home cum cards are unidimensional — force "stacked" so bar mode still
        // renders per-period total annotations.
        var stackVal = "stacked";

        if (rawData.mode === "prior") {
            // Projection is rendered automatically by renderCumulative; suppress
            // it by stripping the projection fields when the toggle is off.
            if (!projectOn) {
                rawData = JSON.parse(JSON.stringify(rawData));
                if (rawData.current) delete rawData.current.projection;
                delete rawData.projectionTotal;
            }
            return window.dash_clientside.census._homeCompactLegend(
                window.dash_clientside.cumulative.renderCumulative(
                    rawData, smoothPct, chartType, currentFig, stackVal, maxPrior
                )
            );
        }

        // Slice mode: cumsum each series clientside, render via unified
        // chart-with-type so area/line pick up their usual treatment.
        // Bar mode on a single-period cumulative isn't meaningful — fall back to line.
        var renderType = (chartType === "bar") ? "line" : chartType;
        var data = JSON.parse(JSON.stringify(rawData));
        for (var si = 0; si < data.series.length; si++) {
            var vals = data.series[si].values;
            var cum = 0;
            for (var di = 0; di < vals.length; di++) {
                if (vals[di] === null || vals[di] === undefined) {
                    vals[di] = null;  // propagate gaps
                } else {
                    cum += vals[di];
                    vals[di] = cum;
                }
            }
        }
        data.stacked = false;  // cumulative progression doesn't stack
        return window.dash_clientside.census._homeCompactLegend(
            window.dash_clientside.census.smoothChartWithTypeAndRange(
                data, smoothPct, renderType, "0", "grouped", currentFig
            )
        );
    },

    /**
     * Cumulative variant: rebase each series to a running total that resets at the
     * start of the visible range, then render as a non-stacked line chart.
     * Pre-range values are nulled so no line is drawn before the rebase point.
     */
    smoothCumulativeWithRange: function(rawData, smoothPct, rangeDays, currentFig) {
        if (!rawData || !rawData.dates || rawData.dates.length === 0) {
            return window.dash_clientside.census._buildWithRange(
                rawData, smoothPct, "line", rangeDays, currentFig, "grouped"
            );
        }

        // Deep-copy so we don't mutate the store payload
        var data = JSON.parse(JSON.stringify(rawData));

        // Determine startIdx based on rangeDays relative to last date
        var days = parseInt(rangeDays) || 0;
        var startIdx = 0;
        var dates = data.dates;
        if (days > 0 && dates.length > 0) {
            var lp = parseIsoDate(dates[dates.length - 1]);
            if (lp.valid) {
                var startObj = new Date(lp.year, lp.month, lp.day - days);
                var startIso = localDateToIso(startObj);
                startIdx = dates.length;
                for (var i = 0; i < dates.length; i++) {
                    if (dates[i].split('T')[0] >= startIso) { startIdx = i; break; }
                }
            }
        }

        // Rebuild values: null before startIdx, cumulative sum from startIdx onward
        for (var si = 0; si < data.series.length; si++) {
            var vals = data.series[si].values;
            var cum = 0;
            for (var di = 0; di < vals.length; di++) {
                if (di < startIdx) {
                    vals[di] = null;
                } else {
                    cum += (typeof vals[di] === "number" && !isNaN(vals[di])) ? vals[di] : 0;
                    vals[di] = cum;
                }
            }
        }

        // No future projection for cumulative (keeps the visible window meaningful)
        data.futureDates = [];

        // Force non-stacked line rendering
        data.stacked = false;

        var chartElId = data.chartId || currentFig && currentFig.layout && currentFig.layout._chartElId;
        // Inject chartId so _buildWithRange/debounce targets right element
        return window.dash_clientside.census._buildWithRange(
            data, smoothPct, "line", rangeDays, currentFig, "grouped"
        );
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
    updateOnPan: function(relayoutData, currentFigure, rawData, chartType, stackOverride) {
        if (!relayoutData || !currentFigure || !rawData ||
            !rawData.dates || rawData.dates.length === 0) {
            return window.dash_clientside.no_update;
        }

        // Staleness guard: relayoutData fires during Plotly's own react (not
        // just user pans). If the captured State(figure) doesn't contain every
        // series in rawData, it's the pre-toggle figure — deep-copying and
        // patching it would overwrite the fresh figure produced by homeTrend
        // with the prior render's layout (including its margin). Bail out.
        var figNames = {};
        for (var _fi = 0; _fi < (currentFigure.data || []).length; _fi++) {
            var _nm = currentFigure.data[_fi].name;
            if (_nm) figNames[_nm] = true;
        }
        for (var _si = 0; _si < rawData.series.length; _si++) {
            if (!figNames[rawData.series[_si].name]) {
                return window.dash_clientside.no_update;
            }
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

        var stacked = stackOverride === "grouped" ? false : stackOverride === "stacked" ? true : rawData.stacked !== false;
        // Stacked sum only for stacked area/bar — line is always non-stacked
        var useStackedSum = stacked && chartType !== "line";
        var yMax = 0;

        // Track which series have data in the visible range
        var seriesHasData = new Array(rawData.series.length).fill(false);

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
                        var val = rawData.series[si].values[di] || 0;
                        stackTotal += val;
                        if (val > 0) seriesHasData[si] = true;
                    }
                    if (stackTotal > yMax) yMax = stackTotal;
                } else {
                    for (var si = 0; si < rawData.series.length; si++) {
                        var val = rawData.series[si].values[di] || 0;
                        if (val > yMax) yMax = val;
                        if (val > 0) seriesHasData[si] = true;
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
                        var val = allValues[si][di] || 0;
                        stackTotal += val;
                        if (val > 0) seriesHasData[si] = true;
                    }
                    if (stackTotal > yMax) yMax = stackTotal;
                } else {
                    for (var si = 0; si < allValues.length; si++) {
                        var val = allValues[si][di] || 0;
                        if (val > yMax) yMax = val;
                        if (val > 0) seriesHasData[si] = true;
                    }
                }
            }
        }

        if (yMax <= 0) return window.dash_clientside.no_update;

        var newYMax = Math.ceil(yMax * 1.1);

        // Build a name→hasData map from rawData series
        var seriesDataMap = {};
        for (var si = 0; si < rawData.series.length; si++) {
            seriesDataMap[rawData.series[si].name] = seriesHasData[si];
        }

        // Check if anything actually changed (y-axis + legend visibility)
        var yChanged = !(currentFigure.layout && currentFigure.layout.yaxis &&
            currentFigure.layout.yaxis.range &&
            currentFigure.layout.yaxis.range[1] === newYMax);
        var legendChanged = false;
        if (currentFigure.data) {
            for (var ti = 0; ti < currentFigure.data.length; ti++) {
                var tName = currentFigure.data[ti].name;
                if (tName && seriesDataMap.hasOwnProperty(tName)) {
                    var shouldShow = seriesDataMap[tName];
                    var currentlyShown = currentFigure.data[ti].showlegend !== false;
                    if (shouldShow !== currentlyShown) { legendChanged = true; break; }
                }
            }
        }

        if (!yChanged && !legendChanged) {
            return window.dash_clientside.no_update;
        }

        var newFigure = JSON.parse(JSON.stringify(currentFigure));
        newFigure.layout.yaxis = newFigure.layout.yaxis || {};
        newFigure.layout.yaxis.range = [0, newYMax];
        newFigure.layout.yaxis.autorange = false;

        // Update legend visibility based on visible data
        for (var ti = 0; ti < newFigure.data.length; ti++) {
            var tName = newFigure.data[ti].name;
            if (tName && seriesDataMap.hasOwnProperty(tName)) {
                newFigure.data[ti].showlegend = seriesDataMap[tName];
            }
        }

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
        if (firstDataIdx > 0 && firstDataIdx < filtered.dates.length && chartType !== "bar") {
            // Skip for bar charts — they use category indices, not date ranges
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
            var _dp = parseIsoDate(dates[di]);
            if (_dp.valid) {
                dateStr = monthNames[_dp.month] + " " + _dp.day + ", " + _dp.year;
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
                    if (plotEl) Plotly.react(plotEl, fig.data, fig.layout, {displayModeBar: false});
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

// ---------------------------------------------------------------------------
// Cumulative overlay chart — prior periods or slice-by mode
// ---------------------------------------------------------------------------

window.dash_clientside.cumulative = {
    /**
     * Wrapper that strips projection fields when the per-card "Project to year
     * end" toggle is off, then delegates to renderCumulative. This lets every
     * page's cum chart callback wire a shared projection toggle without
     * re-implementing the strip logic.
     */
    renderWithProjectToggle: function(rawData, smoothPct, chartType, stackVal, maxPrior, projectOn, currentFig) {
        if (!projectOn && rawData) {
            rawData = JSON.parse(JSON.stringify(rawData));
            if (rawData.current) delete rawData.current.projection;
            delete rawData.projectionTotal;
        }
        return window.dash_clientside.cumulative.renderCumulative(
            rawData, smoothPct, chartType, currentFig, stackVal, maxPrior
        );
    },
    /**
     * Render a cumulative visit volume chart.
     * Supports two modes:
     *   - "prior": current period (bold purple) + up to 5 prior periods (thin gray)
     *   - "slice": multiple colored cumulative lines per dimension
     *
     * @param {Object} rawData - Data from _prepare_cumulative_data
     * @param {number} smoothPct - Unused (cumulative data is inherently smooth)
     * @param {string} chartType - "line" or "area"
     * @param {Object} currentFig - Current figure (to preserve visibility)
     * @returns {Object} Plotly figure
     */
    renderCumulative: function(rawData, smoothPct, chartType, currentFig, stackVal, maxPrior) {
        if (!rawData) {
            return {data: [], layout: Object.assign({}, window.dmc_default_layout || {}, {
                xaxis: {visible: false}, yaxis: {visible: false},
                annotations: [{text: "No data for selected filters", xref: "paper", yref: "paper",
                    x: 0.5, y: 0.5, showarrow: false, font: {size: 14, color: "#9CA3AF"}}],
                height: 350, margin: {l: 40, r: 20, t: 20, b: 40}
            })};
        }

        chartType = chartType || "line";

        // Build visibility map from current figure
        var visibilityMap = {};
        if (currentFig && currentFig.data) {
            for (var j = 0; j < currentFig.data.length; j++) {
                var trace = currentFig.data[j];
                if (trace.name && trace.visible !== undefined) {
                    visibilityMap[trace.name] = trace.visible;
                }
            }
        }

        var traces = [];
        var yTitle = rawData.yTitle || "Cumulative Visits";
        var isDollar = yTitle.indexOf('$') >= 0;
        function fmtVal(v) {
            if (v === null || v === undefined || isNaN(v)) return isDollar ? "$0" : "0";
            return isDollar ? "$" + Math.round(v).toLocaleString() : Math.round(v).toLocaleString();
        }

        // LOESS smoothing for cumulative charts: pin endpoints to raw values,
        // ensure no value drops below 0.
        var loessFrac = smoothPct > 0 ? Math.min(smoothPct, 1.0) : 0;

        function loessClamped(raw, frac) {
            if (frac <= 0 || !raw || raw.length < 4) return raw;
            var smoothed = loess(raw, frac);
            var first = -1, last = -1;
            for (var i = 0; i < raw.length; i++) {
                if (raw[i] !== null && raw[i] !== undefined) {
                    if (first < 0) first = i;
                    last = i;
                }
            }
            if (first < 0) return smoothed;
            smoothed[first] = raw[first];
            smoothed[last] = raw[last];
            for (var j = 0; j < smoothed.length; j++) {
                if (smoothed[j] < 0) smoothed[j] = 0;
            }
            return smoothed;
        }

        if (rawData.mode === "prior") {
            // --- Prior Periods Mode ---
            var dayIndices = rawData.dayIndices || [];
            var tickPositions = rawData.tickPositions || [];
            var tickLabels = rawData.tickLabels || [];
            var current = rawData.current || {};
            var prior = rawData.prior || [];

            // Limit prior periods to slider value
            if (maxPrior && maxPrior > 0 && prior.length > maxPrior) {
                prior = prior.slice(0, maxPrior);
            }

            if (chartType === "bar") {
                // --- Bar: stacked bars per period, broken down by slice ---
                // Use numeric indices as x-values to prevent Plotly from coercing
                // year-only labels like "2021" to numbers on the axis.
                var bd = rawData.sliceBreakdown || {};
                var periods = bd.periods || [];
                var slices = bd.slices || [];
                // Trim bar breakdown to maxPrior + 1 (current + N priors)
                // Periods are oldest-first, so keep the LAST maxBars entries (most recent)
                var maxBars = (maxPrior && maxPrior > 0) ? maxPrior + 1 : periods.length;
                var trimStart = 0;
                if (periods.length > maxBars) {
                    trimStart = periods.length - maxBars;
                    periods = periods.slice(trimStart);
                    slices = slices.map(function(s) {
                        return Object.assign({}, s, {values: s.values.slice(trimStart)});
                    });
                }
                // Remove slices that have no data in the displayed periods
                slices = slices.filter(function(s) {
                    return s.values.some(function(v) { return v > 0; });
                });
                // Reassign colors from colorway based on visible slices only,
                // so we avoid duplicate colors when the original indices had gaps.
                // Preserve department colors (assigned by name, not index).
                var DEPT_COLORS = {"Lacey": "#2196F3", "Centralia": "#F44336", "Aberdeen": "#4CAF50"};
                var CW = ["#7C2A83", "#2196F3", "#F44336", "#4CAF50", "#FF9800", "#00BCD4", "#9C27B0", "#795548"];
                var cwIdx = 0;
                for (var ci = 0; ci < slices.length; ci++) {
                    if (DEPT_COLORS[slices[ci].name]) {
                        slices[ci].color = DEPT_COLORS[slices[ci].name];
                    } else {
                        slices[ci].color = CW[cwIdx % CW.length];
                        cwIdx++;
                    }
                }
                var barIndices = periods.map(function(_, i) { return i; });

                // Compute per-period totals and summary HTML for hover
                var barTotals = [];
                var barTotalYs = [];
                if (slices.length > 0 && periods.length > 0) {
                    for (var pi = 0; pi < periods.length; pi++) {
                        var parts = ["<b>" + periods[pi] + "</b>"];
                        var total = 0;
                        for (var sj = 0; sj < slices.length; sj++) {
                            var val = slices[sj].values[pi] || 0;
                            if (val > 0) {
                                parts.push("<span style='color:" + slices[sj].color + "'>\u25A0</span> " +
                                    slices[sj].name + ": " + fmtVal(val));
                                total += val;
                            }
                        }
                        if (slices.length > 1) {
                            parts.push("<b>Total: " + fmtVal(total) + "</b>");
                        }
                        barTotals.push(parts.join("<br>"));
                        barTotalYs.push(total);
                    }
                    // Put summary hover on every bar so any bar in a group triggers the tooltip
                    for (var si = 0; si < slices.length; si++) {
                        var sl = slices[si];
                        traces.push({
                            x: barIndices, y: sl.values, name: sl.name,
                            type: "bar", marker: {color: sl.color},
                            customdata: barTotals,
                            hovertemplate: "%{customdata}<extra></extra>"
                        });
                    }
                }

                // Dynamic y-range + annotations for totals on top
                var isGrouped = stackVal === "grouped";
                var yMaxBar = 0;
                var barAnnotations = [];
                for (var pi = 0; pi < periods.length; pi++) {
                    var colTotal = barTotalYs[pi] || 0;
                    if (isGrouped) {
                        // In grouped mode, y-max is the tallest individual slice
                        for (var gs = 0; gs < slices.length; gs++) {
                            var sv = (slices[gs].values[pi] || 0);
                            if (sv > yMaxBar) yMaxBar = sv;
                        }
                    } else {
                        if (colTotal > yMaxBar) yMaxBar = colTotal;
                        barAnnotations.push({
                            x: pi, y: colTotal,
                            text: "<b>" + fmtVal(colTotal) + "</b>",
                            showarrow: false, yshift: 8,
                            font: {size: 11, color: "#374151", family: "Inter, system-ui, sans-serif"}
                        });
                    }
                }

                // Current_year projection: transparent overlay bar + faint annotation
                // at the projected year-end total.
                var projTotal = rawData.projectionTotal;
                if (projTotal && projTotal.remainder > 0) {
                    var pIdx = projTotal.periodIdx - trimStart;
                    if (pIdx >= 0 && pIdx < periods.length) {
                        var projY = periods.map(function(_, i) { return i === pIdx ? projTotal.remainder : 0; });
                        var projColor = (rawData.current && rawData.current.color) || "#7C2A83";
                        traces.push({
                            x: barIndices, y: projY,
                            name: (rawData.current && rawData.current.label ? rawData.current.label : "") + " (projected)",
                            type: "bar",
                            marker: {color: projColor, opacity: 0.25, line: {width: 0}},
                            showlegend: false,
                            hovertemplate: "Projected year-end: <b>" + fmtVal(projTotal.endVal) + "</b><extra></extra>"
                        });
                        if (projTotal.endVal > yMaxBar) yMaxBar = projTotal.endVal;
                        if (!isGrouped) {
                            barAnnotations.push({
                                x: pIdx, y: projTotal.endVal,
                                text: "<i>" + fmtVal(projTotal.endVal) + "</i>",
                                showarrow: false, yshift: 8,
                                font: {size: 10, color: "#6B7280", family: "Inter, system-ui, sans-serif"}
                            });
                        }
                    }
                }

                return {
                    data: traces,
                    layout: {
                        barmode: isGrouped ? "group" : "stack",
                        xaxis: {
                            showgrid: false, showspikes: false,
                            type: "linear",
                            tickvals: barIndices, ticktext: periods,
                            tickangle: 0, autorange: true,
                            categoryorder: null, categoryarray: null
                        },
                        yaxis: {
                            gridcolor: "#E5E7EB", title: "",
                            tickprefix: isDollar ? '$' : '',
                            range: [0, Math.ceil(yMaxBar * 1.13)],
                            autorange: false
                        },
                        bargap: 0.15,
                        showlegend: slices.length > 1,
                        legend: {
                            orientation: "h", yanchor: "bottom", y: 1.02,
                            xanchor: "left", x: 0,
                            tracegroupgap: 0
                        },
                        margin: {l: 36, r: 16, t: 28, b: 20},
                        plot_bgcolor: "white",
                        paper_bgcolor: "white",
                        font: {family: "Inter, system-ui, sans-serif", size: 12, color: "#374151"},
                        hovermode: "closest",
                        hoverlabel: {
                            align: "left", bgcolor: "white", bordercolor: "#E5E7EB",
                            font: {color: "#374151", size: 12, family: "Inter, system-ui, sans-serif"}
                        },
                        annotations: barAnnotations
                    }
                };
            }

            // --- Line / Area mode ---
            // Collect raw values per trace for summary hover
            var lineValsByName = {};

            // Prior period traces (thin lines with spectrum colors) — LOESS smoothed display
            for (var i = 0; i < prior.length; i++) {
                var p = prior[i];
                var priorColor = p.color || "#D1D5DB";
                lineValsByName[p.label] = p.values;  // raw for hover
                var displayVals = loessFrac > 0 ? loessClamped(p.values, loessFrac) : p.values;
                var traceObj = {
                    x: dayIndices, y: displayVals, name: p.label,
                    mode: "lines",
                    connectgaps: true,
                    line: {color: priorColor, width: 1.5},
                    legendrank: i + 1,
                    hoverinfo: "skip",
                    opacity: 0.7
                };
                if (chartType === "area") {
                    traceObj.fill = "tozeroy";
                    traceObj.fillcolor = hexToRgba(priorColor, 0.08);
                }
                if (visibilityMap.hasOwnProperty(p.label)) {
                    traceObj.visible = visibilityMap[p.label];
                }
                traces.push(traceObj);
            }

            // Current period trace (bold, on top) — LOESS smoothed display
            var currentVals = current.values || [];
            var trimmedX = [];
            var trimmedY = [];
            for (var k = 0; k < currentVals.length; k++) {
                if (currentVals[k] !== null && currentVals[k] !== undefined) {
                    trimmedX.push(k);
                    trimmedY.push(currentVals[k]);
                }
            }
            lineValsByName[current.label || "Current"] = trimmedY;  // raw for hover
            var displayCurrentY = loessFrac > 0 ? loessClamped(trimmedY, loessFrac) : trimmedY;

            var currentTrace = {
                x: trimmedX, y: displayCurrentY,
                name: current.label || "Current",
                mode: "lines",
                connectgaps: true,
                line: {color: current.color || "#7C2A83", width: 3},
                legendrank: 0,
                hoverinfo: "skip"
            };
            if (chartType === "area") {
                currentTrace.fill = "tozeroy";
                currentTrace.fillcolor = hexToRgba(current.color || "#7C2A83", 0.15);
            }
            if (visibilityMap.hasOwnProperty(current.label)) {
                currentTrace.visible = visibilityMap[current.label];
            }
            traces.push(currentTrace);

            // Current_year projection: dashed extension from (startIdx, startVal)
            // to (endIdx, endVal). Emitted by apply_current_year_projection.
            // Fine dash pattern ("3px,3px") reads as a visibly "projected" line
            // without looking heavy like the default "dash" style.
            //
            // NOTE: do NOT set legendgroup here. Plotly reserves a legend slot
            // for any trace with a legendgroup even when showlegend=false, which
            // pushes the total legend width over the plot width and forces the
            // horizontal legend to wrap into a vertical stack.
            if (current.projection) {
                var cp = current.projection;
                traces.push({
                    x: [cp.startIdx, cp.endIdx],
                    y: [cp.startVal, cp.endVal],
                    name: (current.label || "Current") + " (projected)",
                    mode: "lines",
                    line: {color: current.color || "#7C2A83", width: 2.5, dash: "3px,3px"},
                    showlegend: false,
                    hovertemplate: "Projected year-end: <b>" + fmtVal(cp.endVal) + "</b><extra></extra>"
                });
            }

            // Summary hover trace — current period first, then prior (oldest last)
            var allTraceEntries = [{name: current.label || "Current", color: current.color || "#7C2A83"}];
            for (var pi = 0; pi < prior.length; pi++) {
                allTraceEntries.push({name: prior[pi].label, color: prior[pi].color || "#D1D5DB"});
            }

            var summaryXL = [];
            var summaryYL = [];
            var summaryHL = [];
            var monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
            var _sp = rawData.startDate ? parseIsoDate(rawData.startDate) : null;
            for (var di = 0; di < dayIndices.length; di++) {
                var dateLabel = "";
                if (_sp && _sp.valid) {
                    var dd = new Date(_sp.year, _sp.month, _sp.day + di);
                    dateLabel = monthNames[dd.getMonth()] + " " + dd.getDate();
                }
                var parts = ["<b>" + (dateLabel || "Day " + di) + "</b>"];
                var ptMax = 0;
                for (var tn = 0; tn < allTraceEntries.length; tn++) {
                    var entry = allTraceEntries[tn];
                    var vals = lineValsByName[entry.name] || [];
                    var isVis = !visibilityMap.hasOwnProperty(entry.name) || visibilityMap[entry.name] === true;
                    var v = di < vals.length ? vals[di] : null;
                    if (v !== null && v !== undefined && isVis) {
                        parts.push("<span style='color:" + entry.color + "'>\u25A0</span> " +
                            entry.name + ": " + fmtVal(v));
                        if (v > ptMax) ptMax = v;
                    }
                }
                summaryXL.push(di);
                summaryYL.push(ptMax);
                summaryHL.push(parts.join("<br>"));
            }
            traces.push({
                x: summaryXL, y: summaryYL, customdata: summaryHL,
                name: "", mode: "lines", line: {color: "transparent", width: 0},
                hovertemplate: "%{customdata}<extra></extra>",
                showlegend: false
            });

            // Endpoint annotations — oldest prior first, current last (later = drawn on top)
            var annotations = [];
            // Prior period endpoint annotations (oldest → most recent).
            // Home page opts out via hidePriorEndpointLabels to keep the small
            // cumulative cards uncluttered — only the current (purple) endpoint shows.
            if (!rawData.hidePriorEndpointLabels) {
            for (var ai = prior.length - 1; ai >= 0; ai--) {
                var pVals = prior[ai].values || [];
                var pColor = prior[ai].color || "#D1D5DB";
                var isVisible = !visibilityMap.hasOwnProperty(prior[ai].label) || visibilityMap[prior[ai].label] === true;
                if (!isVisible || pVals.length === 0) continue;
                // Find last non-null value
                var pEndVal = null, pEndX = null;
                for (var pxi = pVals.length - 1; pxi >= 0; pxi--) {
                    if (pVals[pxi] !== null && pVals[pxi] !== undefined) {
                        pEndVal = pVals[pxi]; pEndX = pxi; break;
                    }
                }
                if (pEndVal !== null) {
                    annotations.push({
                        x: pEndX, y: pEndVal,
                        text: fmtVal(pEndVal),
                        showarrow: false,
                        xanchor: "left", yanchor: "middle",
                        xshift: 6,
                        font: {color: pColor, size: 11, family: "Inter, system-ui, sans-serif"}
                    });
                }
            }
            }
            // Current period endpoint label — placed to the TOP-LEFT of the
            // endpoint so it sits in the blank space above the solid line rather
            // than overlapping the dashed projection that extends to the upper right.
            if (trimmedY.length > 0) {
                var endVal = trimmedY[trimmedY.length - 1];
                var endX = trimmedX[trimmedX.length - 1];
                if (endVal !== null && endVal !== undefined) {
                    var endFmt = fmtVal(endVal);
                    annotations.push({
                        x: endX,
                        y: endVal,
                        text: "<b>" + endFmt + "</b>",
                        showarrow: false,
                        xanchor: "right",
                        yanchor: "bottom",
                        xshift: -4,
                        yshift: 4,
                        font: {color: current.color || "#7C2A83", size: 13, family: "Inter, system-ui, sans-serif"}
                    });
                }
            }

            // Compute dynamic y-range from visible traces
            var yMaxLine = 0;
            for (var ti = 0; ti < traces.length; ti++) {
                var t = traces[ti];
                if (t.line && t.line.color === "transparent") continue; // skip summary
                var isVis = !t.name || !visibilityMap.hasOwnProperty(t.name) || visibilityMap[t.name] === true;
                if (!isVis) continue;
                var yArr = t.y || [];
                for (var yi = 0; yi < yArr.length; yi++) {
                    if (yArr[yi] !== null && yArr[yi] !== undefined && yArr[yi] > yMaxLine) yMaxLine = yArr[yi];
                }
            }

            return {
                data: traces,
                layout: {
                    xaxis: {
                        showgrid: false,
                        showspikes: false,
                        type: "linear",
                        tickvals: tickPositions,
                        ticktext: tickLabels,
                        tickangle: 0,
                        // Clear bar-mode properties (Plotly.react merges layouts)
                        categoryorder: null, categoryarray: null
                    },
                    yaxis: {
                        gridcolor: "#E5E7EB", title: "",
                        tickprefix: isDollar ? '$' : '',
                        range: [0, Math.ceil(yMaxLine * 1.1)],
                        autorange: false
                    },
                    showlegend: true,
                    legend: {
                        orientation: "h",
                        yanchor: "bottom",
                        y: 1.02,
                        xanchor: "left",
                        x: 0,
                        tracegroupgap: 0
                    },
                    margin: {l: 36, r: 16, t: 28, b: 20},
                    plot_bgcolor: "white",
                    paper_bgcolor: "white",
                    font: {family: "Inter, system-ui, sans-serif", size: 12, color: "#374151"},
                    hovermode: "x",
                    hoverlabel: {
                        align: "left",
                        bgcolor: "white",
                        bordercolor: "#E5E7EB",
                        font: {color: "#374151", size: 12, family: "Inter, system-ui, sans-serif"}
                    },
                    annotations: annotations
                }
            };

        } else {
            // --- Slice Mode ---
            var sliceSeries = rawData.series || [];

            if (chartType === "bar") {
                // Bar always uses sliceBreakdown (periods × slices stacked)
                // Use numeric indices to prevent Plotly coercing year labels to numbers
                var bd = rawData.sliceBreakdown || {};
                var periods = bd.periods || [];
                var slices = bd.slices || [];
                // Trim to maxPrior + 1 (current + N priors), keeping most recent
                var maxBars2 = (maxPrior && maxPrior > 0) ? maxPrior + 1 : periods.length;
                if (periods.length > maxBars2) {
                    var trimStart2 = periods.length - maxBars2;
                    periods = periods.slice(trimStart2);
                    slices = slices.map(function(s) {
                        return Object.assign({}, s, {values: s.values.slice(trimStart2)});
                    });
                }
                // Remove slices with no data in displayed periods
                slices = slices.filter(function(s) {
                    return s.values.some(function(v) { return v > 0; });
                });
                var barIndices2 = periods.map(function(_, i) { return i; });

                var barTotals2 = [];
                var barTotalYs2 = [];
                if (slices.length > 0 && periods.length > 0) {
                    for (var pi = 0; pi < periods.length; pi++) {
                        var parts = ["<b>" + periods[pi] + "</b>"];
                        var total = 0;
                        for (var sj = 0; sj < slices.length; sj++) {
                            var val = slices[sj].values[pi] || 0;
                            if (val > 0) {
                                parts.push("<span style='color:" + slices[sj].color + "'>\u25A0</span> " +
                                    slices[sj].name + ": " + fmtVal(val));
                                total += val;
                            }
                        }
                        if (slices.length > 1) {
                            parts.push("<b>Total: " + fmtVal(total) + "</b>");
                        }
                        barTotals2.push(parts.join("<br>"));
                        barTotalYs2.push(total);
                    }
                    // Put summary hover on every bar so any bar in a group triggers the tooltip
                    for (var si = 0; si < slices.length; si++) {
                        var sl = slices[si];
                        traces.push({
                            x: barIndices2, y: sl.values, name: sl.name,
                            type: "bar", marker: {color: sl.color},
                            customdata: barTotals2,
                            hovertemplate: "%{customdata}<extra></extra>"
                        });
                    }
                }
                var isGrouped2 = stackVal === "grouped";
                var yMaxBar2 = 0;
                var barAnnotations2 = [];
                for (var pi2 = 0; pi2 < periods.length; pi2++) {
                    var ct = barTotalYs2[pi2] || 0;
                    if (isGrouped2) {
                        for (var gs2 = 0; gs2 < slices.length; gs2++) {
                            var sv2 = (slices[gs2].values[pi2] || 0);
                            if (sv2 > yMaxBar2) yMaxBar2 = sv2;
                        }
                    } else {
                        if (ct > yMaxBar2) yMaxBar2 = ct;
                        barAnnotations2.push({
                            x: pi2, y: ct,
                            text: "<b>" + fmtVal(ct) + "</b>",
                            showarrow: false, yshift: 8,
                            font: {size: 11, color: "#374151", family: "Inter, system-ui, sans-serif"}
                        });
                    }
                }

                return {
                    data: traces,
                    layout: {
                        barmode: isGrouped2 ? "group" : "stack",
                        xaxis: {
                            showgrid: false, showspikes: false,
                            type: "linear",
                            tickvals: barIndices2, ticktext: periods,
                            tickangle: 0, autorange: true,
                            categoryorder: null, categoryarray: null
                        },
                        yaxis: {
                            gridcolor: "#E5E7EB", title: "",
                            tickprefix: isDollar ? '$' : '',
                            range: [0, Math.ceil(yMaxBar2 * 1.13)],
                            autorange: false
                        },
                        bargap: 0.15,
                        showlegend: slices.length > 1,
                        legend: {orientation: "h", yanchor: "bottom", y: 1.02, xanchor: "left", x: 0,
                                 tracegroupgap: 0},
                        margin: {l: 36, r: 16, t: 8, b: 20},
                        plot_bgcolor: "white", paper_bgcolor: "white",
                        font: {family: "Inter, system-ui, sans-serif", size: 12, color: "#374151"},
                        hovermode: "closest",
                        hoverlabel: {
                            align: "left", bgcolor: "white", bordercolor: "#E5E7EB",
                            font: {color: "#374151", size: 12, family: "Inter, system-ui, sans-serif"}
                        },
                        annotations: barAnnotations2
                    }
                };
            }

            // Line/Area: build traces with summary hover — LOESS smoothed display
            var sliceDates = rawData.dates || [];
            var monthNames2 = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
            var sliceValsByName = {};
            for (var si = 0; si < sliceSeries.length; si++) {
                var ss = sliceSeries[si];
                sliceValsByName[ss.name] = ss.values;  // raw for hover
                var displaySliceVals = loessFrac > 0 ? loessClamped(ss.values, loessFrac) : ss.values;
                var sTrace = {
                    x: sliceDates, y: displaySliceVals, name: ss.name,
                    mode: "lines", connectgaps: true,
                    line: {color: ss.color, width: 2},
                    hoverinfo: "skip"
                };
                if (chartType === "area") {
                    sTrace.fill = "tozeroy";
                    sTrace.fillcolor = hexToRgba(ss.color, 0.15);
                }
                if (visibilityMap.hasOwnProperty(ss.name)) {
                    sTrace.visible = visibilityMap[ss.name];
                }
                traces.push(sTrace);
            }

            // Summary hover trace
            var sSummaryX = [], sSummaryY = [], sSummaryH = [];
            for (var di = 0; di < sliceDates.length; di++) {
                var _p2 = parseIsoDate(sliceDates[di]);
                var dlabel = _p2.valid ? monthNames2[_p2.month] + " " + _p2.day + ", " + _p2.year : sliceDates[di];
                var pts = ["<b>" + dlabel + "</b>"];
                var ptMax2 = 0, total2 = 0;
                for (var sn = 0; sn < sliceSeries.length; sn++) {
                    var entry2 = sliceSeries[sn];
                    var sv = sliceValsByName[entry2.name];
                    var isV = !visibilityMap.hasOwnProperty(entry2.name) || visibilityMap[entry2.name] === true;
                    var val2 = di < sv.length ? sv[di] : null;
                    if (val2 !== null && val2 !== undefined && isV) {
                        pts.push("<span style='color:" + entry2.color + "'>\u25A0</span> " +
                            entry2.name + ": " + fmtVal(val2));
                        total2 += Math.round(val2);
                        if (val2 > ptMax2) ptMax2 = val2;
                    }
                }
                if (sliceSeries.length > 1) pts.push("<b>Total: " + fmtVal(total2) + "</b>");
                sSummaryX.push(sliceDates[di]);
                sSummaryY.push(ptMax2);
                sSummaryH.push(pts.join("<br>"));
            }
            traces.push({
                x: sSummaryX, y: sSummaryY, customdata: sSummaryH,
                name: "", mode: "lines", line: {color: "transparent", width: 0},
                hovertemplate: "%{customdata}<extra></extra>",
                showlegend: false
            });

            // Dynamic y-range
            var yMaxSlice = 0;
            for (var yi2 = 0; yi2 < sSummaryY.length; yi2++) {
                if (sSummaryY[yi2] > yMaxSlice) yMaxSlice = sSummaryY[yi2];
            }

            // Smart x-axis tick spacing based on date range
            var nDays = sliceDates.length;
            var tickFormat, dtick;
            if (nDays <= 60) {
                dtick = 7 * 86400000;  // weekly
                tickFormat = "%b %d";
            } else if (nDays <= 180) {
                dtick = 14 * 86400000;  // biweekly
                tickFormat = "%b %d";
            } else if (nDays <= 730) {
                dtick = "M1";  // monthly
                tickFormat = "%b '%y";
            } else if (nDays <= 1825) {
                dtick = "M3";  // quarterly
                tickFormat = "%b '%y";
            } else {
                dtick = "M12";  // yearly
                tickFormat = "%Y";
            }
            var effXAxis = {
                type: "date", showgrid: false, showspikes: false,
                dtick: dtick, tickformat: tickFormat,
                tickangle: 0, automargin: true,
                // Clear bar-mode properties (Plotly.react merges layouts)
                categoryorder: null, categoryarray: null,
                tickvals: null, ticktext: null
            };

            return {
                data: traces,
                layout: {
                    xaxis: effXAxis,
                    yaxis: {
                        gridcolor: "#E5E7EB", title: "",
                        tickprefix: isDollar ? '$' : '',
                        range: [0, Math.ceil(yMaxSlice * 1.1)],
                        autorange: false
                    },
                    showlegend: true,
                    legend: {orientation: "h", yanchor: "bottom", y: 1.02, xanchor: "left", x: 0,
                             tracegroupgap: 0},
                    margin: {l: 36, r: 16, t: 28, b: 20},
                    plot_bgcolor: "white", paper_bgcolor: "white",
                    font: {family: "Inter, system-ui, sans-serif", size: 12, color: "#374151"},
                    hovermode: "x",
                    hoverlabel: {
                        align: "left", bgcolor: "white", bordercolor: "#E5E7EB",
                        font: {color: "#374151", size: 12, family: "Inter, system-ui, sans-serif"}
                    }
                }
            };
        }
    },

    /**
     * Update prior-period controls based on metadata in the cumulative store.
     *
     * Outputs (in order):
     *   0 — period-type SegmentedControl "data" (disable Calendar when period > 365d)
     *   1 — period-type SegmentedControl "value" (force "rolling" when Calendar disabled)
     *   2 — prior-periods Slider "max"
     *   3 — prior-periods Slider "marks"
     *
     * @param {Object} storeData  — cumulative store (must include periodDays, maxAvailablePriors)
     * @param {string} currentPtValue — current period-type SegmentedControl value
     */
    updatePriorControls: function(storeData, currentPtValue) {
        var nu = window.dash_clientside.no_update;
        if (!storeData) return [nu, nu, nu, nu];

        var periodDays     = storeData.periodDays || 0;
        var maxAvail       = (storeData.maxAvailablePriors != null)
                                 ? storeData.maxAvailablePriors : 5;
        var hasPartial     = storeData.hasPartialPrior || false;

        // --- Calendar / Rolling toggle ---
        var calDisabled = periodDays > 365;
        var ptData = [
            {value: "calendar", label: "Calendar", disabled: calDisabled},
            {value: "rolling",  label: "Rolling"}
        ];
        var ptValue = (calDisabled && currentPtValue === "calendar")
                          ? "rolling" : nu;

        // --- Prior-periods slider ---
        // If no full priors but a partial exists, allow 1 (the partial)
        var sliderMax = (maxAvail > 0) ? maxAvail : (hasPartial ? 1 : 1);
        if (sliderMax > 10) sliderMax = 10;
        var marks = [];
        for (var i = 1; i <= sliderMax; i++) {
            marks.push({value: i, label: String(i)});
        }

        return [ptData, ptValue, sliderMax, marks];
    }
};
