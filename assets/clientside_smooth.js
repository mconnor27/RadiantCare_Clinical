/**
 * Clientside LOESS smoothing for charts and sparklines.
 * Enables real-time slider updates without server round-trips.
 */

window.dash_clientside = window.dash_clientside || {};

// ---------------------------------------------------------------------------
// Sparkline smoothing (KPI cards)
// ---------------------------------------------------------------------------

function buildSparkline(data, smoothPct, key) {
    if (!data || !data[key]) {
        return window.dash_clientside.no_update;
    }

    var spark = data[key];
    var frac = (smoothPct || 0) * 0.5;  // slider 0-1 maps to frac 0-0.5
    var yVals = frac > 0 && spark.values.length >= 4 ? loess(spark.values, frac) : spark.values;
    var color = spark.color || "#7C2A83";
    var hoverFmt = spark.hover_fmt || "%{x|%b %d}: %{y:,.0f}<extra></extra>";

    return {
        data: [{
            x: spark.labels,
            y: yVals,
            mode: "lines",
            line: {color: color, width: 1.5},
            hovertemplate: hoverFmt
        }],
        layout: {
            margin: {l: 0, r: 0, t: 0, b: 0},
            height: 34,
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
            yaxis: {visible: false},
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
        var totals = new Array(displayDates.length).fill(0);
        var futureTotals = hasFuture ? new Array(futureDates.length).fill(0) : [];

        // Past data traces
        for (var i = 0; i < rawData.series.length; i++) {
            var s = rawData.series[i];
            var displayVals = step > 1 ? downsampleAvg(s.values, step) : s.values.slice();
            var yVals = smoothPct > 0 ? rollingAvg(displayVals, windowSize) : displayVals;
            var isVisible = !visibilityMap.hasOwnProperty(s.name) || visibilityMap[s.name] === true;

            // Sum for total trace
            if (isVisible) {
                for (var k = 0; k < yVals.length; k++) {
                    totals[k] += yVals[k];
                }
            }

            var traceObj;
            if (chartType === "bar") {
                // Stacked bar chart with formatted date labels (filtered to valid dates only)
                var filteredY = filterByIndices(yVals, barData.validIndices);
                traceObj = {
                    x: barData.labels,
                    y: filteredY,
                    name: s.name,
                    type: "bar",
                    marker: {color: s.color, line: {width: 0}},
                    hovertemplate: s.name + ": %{y:.0f}<extra></extra>"
                };
            } else if (chartType === "line") {
                // Non-stacked line chart
                traceObj = {
                    x: displayDates,
                    y: yVals,
                    name: s.name,
                    mode: "lines",
                    line: {color: s.color, width: 2},
                    hovertemplate: s.name + ": %{y:.0f}<extra></extra>"
                };
            } else {
                // Stacked area chart (default)
                traceObj = {
                    x: displayDates,
                    y: yVals,
                    name: s.name,
                    mode: "lines",
                    line: {color: s.color, width: 1.5},
                    fillcolor: hexToRgba(s.color, 0.5),
                    stackgroup: "one",
                    hovertemplate: s.name + ": %{y:.0f}<extra></extra>"
                };
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

            for (var i = 0; i < rawData.series.length; i++) {
                var s = rawData.series[i];
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
                    // Bar chart: lighter opacity bars for future
                    var filteredFutureY = filterByIndices(futureVals, futureBarData.validIndices);
                    futureTraceObj = {
                        x: futureBarData.labels,
                        y: filteredFutureY,
                        name: s.name + " (scheduled)",
                        type: "bar",
                        marker: {color: s.color, opacity: 0.4, line: {width: 0}},
                        showlegend: false,
                        hovertemplate: s.name + " (scheduled): %{y:.0f}<extra></extra>"
                    };
                } else {
                    // Line/area: connect to last past point
                    var lastPastDate = displayDates[displayDates.length - 1];
                    var lastPastVal = traces[i].y[traces[i].y.length - 1];

                    futureTraceObj = {
                        x: [lastPastDate].concat(futureDates),
                        y: [lastPastVal].concat(futureVals),
                        name: s.name + " (scheduled)",
                        mode: "lines",
                        line: {color: s.color, width: 1, dash: "dot"},
                        fillcolor: chartType === "line" ? "transparent" : hexToRgba(s.color, 0.2),
                        stackgroup: chartType === "line" ? undefined : "future",
                        showlegend: false,
                        hovertemplate: s.name + " (scheduled): %{y:.0f}<extra></extra>"
                    };
                }

                // Preserve visibility (use base name)
                if (visibilityMap.hasOwnProperty(s.name)) {
                    futureTraceObj.visible = visibilityMap[s.name];
                }

                traces.push(futureTraceObj);
            }
        }

        // Add invisible total trace for hover (sum of smoothed series) - only for stacked charts
        if (chartType !== "line") {
            var totalX = chartType === "bar" ? barData.labels : displayDates;
            var totalY = chartType === "bar" ? filterByIndices(totals, barData.validIndices) : totals;
            traces.unshift({
                x: totalX,
                y: totalY,
                name: "Total",
                mode: "lines",
                line: {color: "transparent", width: 0},
                hovertemplate: "<b>Total: %{y:.0f}</b><extra></extra>",
                showlegend: false
            });
        }

        var smoothed = smoothPct > 0;
        var layout = {
            height: height,
            xaxis: {showgrid: false},
            yaxis: {gridcolor: "#E5E7EB"},
            showlegend: false,
            margin: {l: 28, r: 8, t: 8, b: 32},
            plot_bgcolor: "white",
            paper_bgcolor: "white",
            font: {family: "Inter, system-ui, sans-serif", size: 12, color: "#374151"},
            hovermode: "x unified",
            hoverlabel: {align: "left"}
        };

        // Add barmode for stacked bar (categorical x-axis for no gaps)
        if (chartType === "bar") {
            layout.barmode = "stack";
            layout.bargap = 0.15;  // Small gap to distinguish from area chart
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
    smoothChartWithTypeAndRange: function(rawData, smoothPct, chartType, rangeDays, currentFig) {
        // First, get the base figure from smoothChartWithType
        var fig = window.dash_clientside.census.smoothChartWithType(rawData, smoothPct, chartType, currentFig);

        if (fig === window.dash_clientside.no_update || !rawData || !rawData.dates || rawData.dates.length === 0) {
            return fig;
        }

        // Debug logging
        console.log('[DEBUG] smoothChartWithTypeAndRange called');
        console.log('  rawData.dates.length:', rawData.dates.length);
        console.log('  First date:', rawData.dates[0]);
        console.log('  Last date:', rawData.dates[rawData.dates.length - 1]);
        console.log('  rangeDays:', rangeDays);

        // Calculate x-axis range based on rangeDays
        var days = parseInt(rangeDays) || 0;
        if (days > 0) {
            // Get last date from data (strip time component for consistency)
            var lastDate = rawData.dates[rawData.dates.length - 1].split('T')[0];
            var lastDateObj = new Date(lastDate);

            // Calculate start date (days back from last date)
            var startDateObj = new Date(lastDateObj);
            startDateObj.setDate(startDateObj.getDate() - days);
            var startDate = startDateObj.toISOString().split('T')[0];

            console.log('  Calculated range:', startDate, 'to', lastDate);

            // Set x-axis range in layout
            fig.layout.xaxis = fig.layout.xaxis || {};
            fig.layout.xaxis.range = [startDate, lastDate];

            // Enable drag/pan to allow scrolling through all data (horizontal only)
            fig.layout.dragmode = 'pan';
            fig.layout.yaxis = fig.layout.yaxis || {};
            fig.layout.yaxis.fixedrange = true;  // Lock y-axis to prevent vertical panning

            // Add range slider for easier navigation (optional - commented out for cleaner UI)
            // fig.layout.xaxis.rangeslider = {visible: true};
        } else {
            // "All" selected - show full range
            fig.layout.xaxis = fig.layout.xaxis || {};
            fig.layout.xaxis.autorange = true;
            fig.layout.dragmode = 'pan';
            fig.layout.yaxis = fig.layout.yaxis || {};
            fig.layout.yaxis.fixedrange = true;  // Lock y-axis to prevent vertical panning
        }

        return fig;
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
 * Centered rolling average - ideal for stacked area charts.
 * sum(rolling_avg(series)) = rolling_avg(sum(series))
 */
function rollingAvg(arr, windowSize) {
    if (windowSize <= 1) return arr.slice();
    var n = arr.length;
    var result = new Array(n);
    var halfW = Math.floor(windowSize / 2);

    for (var i = 0; i < n; i++) {
        var left = Math.max(0, i - halfW);
        var right = Math.min(n - 1, i + halfW);
        var sum = 0;
        for (var j = left; j <= right; j++) {
            sum += arr[j];
        }
        result[i] = sum / (right - left + 1);
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
    smoothChartWithTypeAndRange: function(rawData, smoothVal, chartType, rangeDays) {
        if (!rawData || !rawData.pastSeries || rawData.pastSeries.length === 0) {
            return window.dash_clientside.hoursRibbon.smoothChartWithType(rawData, smoothVal, chartType);
        }

        // Store raw data globally for dynamic y-axis scaling on pan
        window._ribbonChartData = rawData;

        // Disable downsampling for time-limited views by setting flag
        var days = parseInt(rangeDays) || 0;
        var dataWithFlag = JSON.parse(JSON.stringify(rawData)); // Deep copy
        dataWithFlag._skipDownsample = (days > 0); // Skip downsampling for specific time windows

        // Render with all data (downsampling controlled by flag)
        var fig = window.dash_clientside.hoursRibbon.smoothChartWithType(dataWithFlag, smoothVal, chartType);

        // Set x-axis range to show selected window (keeps all data for panning)
        if (days > 0) {
            // Find the last date across all past series
            var lastDate = null;
            for (var i = 0; i < rawData.pastSeries.length; i++) {
                var s = rawData.pastSeries[i];
                if (s.dates && s.dates.length > 0) {
                    var seriesLastDate = s.dates[s.dates.length - 1];
                    if (!lastDate || seriesLastDate > lastDate) {
                        lastDate = seriesLastDate;
                    }
                }
            }

            if (lastDate) {
                // Strip time component for consistency
                lastDate = lastDate.split('T')[0];
                var lastDateObj = new Date(lastDate);

                // Calculate start date (days back from last date)
                var startDateObj = new Date(lastDateObj);
                startDateObj.setDate(startDateObj.getDate() - days);
                var startDate = startDateObj.toISOString().split('T')[0];

                // Calculate y-axis range from visible data only
                var minHour = 24, maxHour = 0;
                for (var i = 0; i < rawData.pastSeries.length; i++) {
                    var s = rawData.pastSeries[i];
                    for (var j = 0; j < s.dates.length; j++) {
                        var date = s.dates[j].split('T')[0];
                        if (date >= startDate && date <= lastDate) {
                            if (s.startHours[j] < minHour) minHour = s.startHours[j];
                            if (s.endHours[j] > maxHour) maxHour = s.endHours[j];
                        }
                    }
                }

                // Round to nearest half-hour with padding
                var yMin = Math.floor(minHour * 2) / 2 - 0.5;
                var yMax = Math.ceil(maxHour * 2) / 2 + 0.5;
                yMin = Math.max(0, yMin);
                yMax = Math.min(24, yMax);

                // Generate tick values for y-axis
                var tickInterval = 1;
                var tickStart = Math.ceil(yMin / tickInterval) * tickInterval;
                var tickEnd = Math.floor(yMax / tickInterval) * tickInterval;
                var tickvals = [];
                var ticktext = [];
                for (var h = tickStart; h <= tickEnd; h += tickInterval) {
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

                // Set x-axis range and y-axis range
                fig.layout.xaxis = fig.layout.xaxis || {};
                fig.layout.xaxis.range = [startDate, lastDate];
                fig.layout.xaxis.fixedrange = false;  // Allow horizontal panning

                fig.layout.yaxis = fig.layout.yaxis || {};
                fig.layout.yaxis.range = [yMin, yMax];
                fig.layout.yaxis.tickvals = tickvals;
                fig.layout.yaxis.ticktext = ticktext;
                fig.layout.yaxis.fixedrange = true;  // Lock y-axis (no vertical pan)

                fig.layout.dragmode = 'pan';
            }
        } else {
            // "All" view - autorange both axes
            fig.layout.xaxis = fig.layout.xaxis || {};
            fig.layout.xaxis.autorange = true;
            fig.layout.xaxis.fixedrange = false;

            fig.layout.yaxis = fig.layout.yaxis || {};
            fig.layout.yaxis.fixedrange = true;  // Lock y-axis (no vertical pan)

            fig.layout.dragmode = 'pan';
        }

        return fig;
    }
};

// ---------------------------------------------------------------------------
// Dynamic Y-Axis Scaling for Ribbon Chart on Pan
// ---------------------------------------------------------------------------

// Store reference to raw data for y-axis calculations (set by smoothChartWithTypeAndRange)
window._ribbonChartData = null;

// Clientside callback function to handle y-axis updates on pan
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.ribbonYAxis = {
    updateYAxisOnPan: function(relayoutData, currentFigure) {
        console.log('[Ribbon Y-Axis] updateYAxisOnPan called');
        console.log('  relayoutData:', relayoutData);

        // If no relayout data or no raw data, return current figure unchanged
        if (!relayoutData || !window._ribbonChartData || !currentFigure) {
            console.log('[Ribbon Y-Axis] Skipping - missing data');
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
            // Not an x-axis range event
            console.log('[Ribbon Y-Axis] Not an x-axis range event');
            return window.dash_clientside.no_update;
        }

        console.log('[Ribbon Y-Axis] X-axis range changed to:', startDate, 'to', endDate);

        // Convert to YYYY-MM-DD format
        var startStr = (typeof startDate === 'string') ? startDate.split('T')[0] : new Date(startDate).toISOString().split('T')[0];
        var endStr = (typeof endDate === 'string') ? endDate.split('T')[0] : new Date(endDate).toISOString().split('T')[0];

        var rawData = window._ribbonChartData;

        // Calculate y-axis range from visible data
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

        console.log('[Ribbon Y-Axis] Calculated hours - min:', minHour, 'max:', maxHour);

        if (minHour === 24 || maxHour === 0) {
            console.log('[Ribbon Y-Axis] No data in visible range');
            return window.dash_clientside.no_update;
        }

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

        console.log('[Ribbon Y-Axis] Updating y-axis range to:', yMin, '-', yMax);

        // Create updated figure with new y-axis range
        var newFigure = JSON.parse(JSON.stringify(currentFigure)); // Deep copy
        newFigure.layout.yaxis.range = [yMin, yMax];
        newFigure.layout.yaxis.tickvals = tickvals;
        newFigure.layout.yaxis.ticktext = ticktext;

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
