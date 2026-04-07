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
        if (!rawData || !rawData.series) {
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
                    marker: {color: s.color, line: {width: 0}},
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
            } else {
                // Area chart (stacked by default, overlay when stacked:false)
                traceObj = {
                    x: traceDates,
                    y: traceY,
                    customdata: traceRaw,
                    name: s.name,
                    mode: traceDates.length <= 3 ? "lines+markers" : "lines",
                    line: {color: s.color, width: stacked ? 1.5 : 2},
                    fillcolor: hexToRgba(s.color, stacked ? 0.5 : 0.15),
                    connectgaps: true,
                    hoverinfo: "skip"
                };
                if (traceDates.length <= 3) traceObj.marker = {size: 8};
                if (stacked) {
                    traceObj.stackgroup = "one";
                } else {
                    traceObj.fill = "tozeroy";
                }
            }

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
                        connectgaps: true,
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

        // Build summary hover text per date point (unified tooltip for all modes)
        var monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
        var summaryX = chartType === "bar" ? barData.labels.slice() : displayDates.slice();
        var summaryHover = [];
        var summaryY = chartType === "bar"
            ? filterByIndices(totals, barData.validIndices)
            : totals.slice();

        // Detect if values are fractional (e.g. median days, percentages) vs integer counts
        var isPercent = rawData.yTitle && rawData.yTitle.indexOf('%') >= 0;
        var isFractional = isPercent || (rawData.yTitle && (
            rawData.yTitle.toLowerCase().indexOf('median') >= 0 ||
            rawData.yTitle.toLowerCase().indexOf('rate') >= 0 ||
            rawData.yTitle.toLowerCase().indexOf('days') >= 0
        ));
        var isDays = rawData.yTitle && rawData.yTitle.toLowerCase().indexOf('days') >= 0;
        var valueSuffix = isPercent ? "%" : isDays ? " days" : "";

        function formatVal(v) {
            if (v === null || v === undefined || isNaN(v)) return "0";
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

        // Invisible summary hover trace — same pattern for all chart types.
        // Uses hovermode "x" so the tooltip is a clean left-aligned card
        // with bold date header, matching line/area style.
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

        var smoothed = smoothPct > 0;

        var layout = {
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
            hovermode: "x",
            hoverlabel: {
                align: "left",
                bgcolor: "white",
                bordercolor: "#E5E7EB",
                font: {color: "#374151", size: 12, family: "Inter, system-ui, sans-serif"}
            }
        };

        // Suffix for y-axis on percentage charts
        if (!stacked && rawData.yTitle && rawData.yTitle.indexOf('%') >= 0) {
            layout.yaxis.ticksuffix = '%';
        }

        // Add barmode for bar charts
        if (chartType === "bar") {
            layout.barmode = stacked ? "stack" : "group";
            // Tighten gaps as bar count increases to keep bars visible
            var nBars = barData.labels.length + (futureDates ? formatDatesForBars(futureDates).labels.length : 0);
            if (stacked) {
                if (nBars > 80) {
                    layout.bargap = 0;
                } else if (nBars > 40) {
                    layout.bargap = 0.08;
                } else {
                    layout.bargap = 0.15;
                }
                layout.bargroupgap = 0;
            } else {
                // Grouped: minimize gaps so bars fill available space.
                // Also hide (visible:false) empty-data traces so Plotly
                // doesn't allocate bar width to invisible series.
                layout.bargap = 0;
                layout.bargroupgap = 0;
            }
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
        if (yMaxSCWT > 0) {
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
                        text: "<b>" + Math.round(t).toLocaleString() + "</b>",
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
                    if (plotEl) Plotly.react(plotEl, fig.data, fig.layout);
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

// ---------------------------------------------------------------------------
// Cumulative overlay chart — prior periods or slice-by mode
// ---------------------------------------------------------------------------

window.dash_clientside.cumulative = {
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
    renderCumulative: function(rawData, smoothPct, chartType, currentFig) {
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

        // Smoothing window
        var windowSize = Math.max(1, Math.floor(smoothPct) + 1);

        if (rawData.mode === "prior") {
            // --- Prior Periods Mode ---
            var dayIndices = rawData.dayIndices || [];
            var tickPositions = rawData.tickPositions || [];
            var tickLabels = rawData.tickLabels || [];
            var current = rawData.current || {};
            var prior = rawData.prior || [];

            if (chartType === "bar") {
                // --- Bar: stacked bars per period, broken down by slice ---
                // Use numeric indices as x-values to prevent Plotly from coercing
                // year-only labels like "2021" to numbers on the axis.
                var bd = rawData.sliceBreakdown || {};
                var periods = bd.periods || [];
                var slices = bd.slices || [];
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
                                    slices[sj].name + ": " + val.toLocaleString());
                                total += val;
                            }
                        }
                        parts.push("<b>Total: " + total.toLocaleString() + "</b>");
                        barTotals.push(parts.join("<br>"));
                        barTotalYs.push(total);
                    }
                    // Bar traces — use numeric indices, no individual hover
                    for (var si = 0; si < slices.length; si++) {
                        var sl = slices[si];
                        traces.push({
                            x: barIndices, y: sl.values, name: sl.name,
                            type: "bar", marker: {color: sl.color},
                            hoverinfo: "skip"
                        });
                    }
                    // Invisible summary hover trace at the top of each stack
                    traces.push({
                        x: barIndices, y: barTotalYs, customdata: barTotals,
                        type: "scatter", mode: "markers",
                        marker: {size: 0.1, opacity: 0},
                        hovertemplate: "%{customdata}<extra></extra>",
                        showlegend: false
                    });
                }

                // Dynamic y-range + annotations for totals on top
                var yMaxBar = 0;
                var barAnnotations = [];
                for (var pi = 0; pi < periods.length; pi++) {
                    var colTotal = barTotalYs[pi] || 0;
                    if (colTotal > yMaxBar) yMaxBar = colTotal;
                    barAnnotations.push({
                        x: pi, y: colTotal,
                        text: "<b>" + colTotal.toLocaleString() + "</b>",
                        showarrow: false, yshift: 8,
                        font: {size: 11, color: "#374151", family: "Inter, system-ui, sans-serif"}
                    });
                }

                return {
                    data: traces,
                    layout: {
                        barmode: "stack",
                        xaxis: {
                            showgrid: false, showspikes: false,
                            type: "linear",
                            tickvals: barIndices, ticktext: periods,
                            tickangle: 0, autorange: true,
                            categoryorder: null, categoryarray: null
                        },
                        yaxis: {
                            gridcolor: "#E5E7EB", title: "",
                            range: [0, Math.ceil(yMaxBar * 1.13)],
                            autorange: false
                        },
                        bargap: 0.15,
                        showlegend: slices.length > 0,
                        legend: {
                            orientation: "h", yanchor: "bottom", y: 1.02,
                            xanchor: "left", x: 0
                        },
                        margin: {l: 50, r: 16, t: 28, b: 20},
                        plot_bgcolor: "white",
                        paper_bgcolor: "white",
                        font: {family: "Inter, system-ui, sans-serif", size: 12, color: "#374151"},
                        hovermode: "x",
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

            // Prior period traces (thin gray lines)
            for (var i = 0; i < prior.length; i++) {
                var p = prior[i];
                var pVals = smoothPct > 0 ? rollingAvg(p.values, windowSize) : p.values;
                lineValsByName[p.label] = pVals;
                var traceObj = {
                    x: dayIndices, y: pVals, name: p.label,
                    mode: "lines",
                    connectgaps: true,
                    line: {color: "#D1D5DB", width: 1.5},
                    hoverinfo: "skip",
                    opacity: 0.7
                };
                if (chartType === "area") {
                    traceObj.fill = "tozeroy";
                    traceObj.fillcolor = "rgba(209, 213, 219, 0.08)";
                }
                if (visibilityMap.hasOwnProperty(p.label)) {
                    traceObj.visible = visibilityMap[p.label];
                }
                traces.push(traceObj);
            }

            // Current period trace (bold, on top)
            var currentVals = current.values || [];
            var trimmedX = [];
            var trimmedY = [];
            for (var k = 0; k < currentVals.length; k++) {
                if (currentVals[k] !== null && currentVals[k] !== undefined) {
                    trimmedX.push(k);
                    trimmedY.push(currentVals[k]);
                }
            }
            var smoothedY = smoothPct > 0 ? rollingAvg(trimmedY, windowSize) : trimmedY;
            lineValsByName[current.label || "Current"] = smoothedY;

            var currentTrace = {
                x: trimmedX, y: smoothedY,
                name: current.label || "Current",
                mode: "lines",
                connectgaps: true,
                line: {color: current.color || "#7C2A83", width: 3},
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

            // Summary hover trace — current period first, then prior (oldest last)
            var allTraceEntries = [{name: current.label || "Current", color: current.color || "#7C2A83"}];
            for (var pi = 0; pi < prior.length; pi++) {
                allTraceEntries.push({name: prior[pi].label, color: "#D1D5DB"});
            }

            var summaryXL = [];
            var summaryYL = [];
            var summaryHL = [];
            var monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
            var startDateMs = rawData.startDate ? new Date(rawData.startDate).getTime() : null;
            for (var di = 0; di < dayIndices.length; di++) {
                var dateLabel = "";
                if (startDateMs) {
                    var dd = new Date(startDateMs + di * 86400000);
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
                            entry.name + ": " + Math.round(v).toLocaleString());
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

            // Endpoint annotation
            var annotations = [];
            if (smoothedY.length > 0) {
                var endVal = smoothedY[smoothedY.length - 1];
                var endX = trimmedX[trimmedX.length - 1];
                if (endVal !== null && endVal !== undefined) {
                    var fmtVal = endVal.toLocaleString();
                    annotations.push({
                        x: endX,
                        y: endVal,
                        text: "<b>" + fmtVal + "</b>",
                        showarrow: false,
                        xanchor: "left",
                        yanchor: "bottom",
                        xshift: 6,
                        yshift: 2,
                        font: {color: current.color || "#7C2A83", size: 13, family: "Inter, system-ui, sans-serif"},
                        bgcolor: "rgba(255,255,255,0.85)",
                        borderpad: 3
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
                        range: [0, Math.ceil(yMaxLine * 1.1)],
                        autorange: false
                    },
                    showlegend: true,
                    legend: {
                        orientation: "h",
                        yanchor: "bottom",
                        y: 1.02,
                        xanchor: "left",
                        x: 0
                    },
                    margin: {l: 50, r: 16, t: 28, b: 20},
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
                                    slices[sj].name + ": " + val.toLocaleString());
                                total += val;
                            }
                        }
                        parts.push("<b>Total: " + total.toLocaleString() + "</b>");
                        barTotals2.push(parts.join("<br>"));
                        barTotalYs2.push(total);
                    }
                    for (var si = 0; si < slices.length; si++) {
                        var sl = slices[si];
                        traces.push({
                            x: barIndices2, y: sl.values, name: sl.name,
                            type: "bar", marker: {color: sl.color},
                            hoverinfo: "skip"
                        });
                    }
                    traces.push({
                        x: barIndices2, y: barTotalYs2, customdata: barTotals2,
                        type: "scatter", mode: "markers",
                        marker: {size: 0.1, opacity: 0},
                        hovertemplate: "%{customdata}<extra></extra>",
                        showlegend: false
                    });
                }
                var yMaxBar2 = 0;
                var barAnnotations2 = [];
                for (var pi2 = 0; pi2 < periods.length; pi2++) {
                    var ct = barTotalYs2[pi2] || 0;
                    if (ct > yMaxBar2) yMaxBar2 = ct;
                    barAnnotations2.push({
                        x: pi2, y: ct,
                        text: "<b>" + ct.toLocaleString() + "</b>",
                        showarrow: false, yshift: 8,
                        font: {size: 11, color: "#374151", family: "Inter, system-ui, sans-serif"}
                    });
                }

                return {
                    data: traces,
                    layout: {
                        barmode: "stack",
                        xaxis: {
                            showgrid: false, showspikes: false,
                            type: "linear",
                            tickvals: barIndices2, ticktext: periods,
                            tickangle: 0, autorange: true,
                            categoryorder: null, categoryarray: null
                        },
                        yaxis: {
                            gridcolor: "#E5E7EB", title: "",
                            range: [0, Math.ceil(yMaxBar2 * 1.13)],
                            autorange: false
                        },
                        bargap: 0.15,
                        showlegend: slices.length > 0,
                        legend: {orientation: "h", yanchor: "bottom", y: 1.02, xanchor: "left", x: 0},
                        margin: {l: 50, r: 16, t: 8, b: 20},
                        plot_bgcolor: "white", paper_bgcolor: "white",
                        font: {family: "Inter, system-ui, sans-serif", size: 12, color: "#374151"},
                        hovermode: "x",
                        hoverlabel: {
                            align: "left", bgcolor: "white", bordercolor: "#E5E7EB",
                            font: {color: "#374151", size: 12, family: "Inter, system-ui, sans-serif"}
                        },
                        annotations: barAnnotations2
                    }
                };
            }

            // Line/Area: build traces with summary hover (not delegated, to get unified tooltip)
            var sliceDates = rawData.dates || [];
            var windowSize2 = Math.max(1, Math.floor(smoothPct) + 1);
            var monthNames2 = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
            var sliceValsByName = {};

            for (var si = 0; si < sliceSeries.length; si++) {
                var ss = sliceSeries[si];
                var sVals = (smoothPct > 0) ? rollingAvg(ss.values, windowSize2) : ss.values;
                sliceValsByName[ss.name] = sVals;
                var sTrace = {
                    x: sliceDates, y: sVals, name: ss.name,
                    mode: "lines", connectgaps: true, line: {color: ss.color, width: 2},
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
                var d2 = new Date(sliceDates[di]);
                var dlabel = !isNaN(d2) ? monthNames2[d2.getMonth()] + " " + d2.getDate() + ", " + d2.getFullYear() : sliceDates[di];
                var pts = ["<b>" + dlabel + "</b>"];
                var ptMax2 = 0, total2 = 0;
                for (var sn = 0; sn < sliceSeries.length; sn++) {
                    var entry2 = sliceSeries[sn];
                    var sv = sliceValsByName[entry2.name];
                    var isV = !visibilityMap.hasOwnProperty(entry2.name) || visibilityMap[entry2.name] === true;
                    var val2 = di < sv.length ? sv[di] : null;
                    if (val2 !== null && val2 !== undefined && isV) {
                        pts.push("<span style='color:" + entry2.color + "'>\u25A0</span> " +
                            entry2.name + ": " + Math.round(val2).toLocaleString());
                        total2 += Math.round(val2);
                        if (val2 > ptMax2) ptMax2 = val2;
                    }
                }
                if (sliceSeries.length > 1) pts.push("<b>Total: " + total2.toLocaleString() + "</b>");
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

            var effXAxis = {
                showgrid: false, showspikes: false, nticks: 12, automargin: true,
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
                        range: [0, Math.ceil(yMaxSlice * 1.1)],
                        autorange: false
                    },
                    showlegend: true,
                    legend: {orientation: "h", yanchor: "bottom", y: 1.02, xanchor: "left", x: 0},
                    margin: {l: 50, r: 16, t: 28, b: 20},
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
    }
};
