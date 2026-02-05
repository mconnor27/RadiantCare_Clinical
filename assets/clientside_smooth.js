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
     * @param {Object} currentFig - Current figure (to preserve trace visibility)
     * @returns {Object} Plotly figure
     */
    smoothChart: function(rawData, smoothPct, currentFig) {
        if (!rawData || !rawData.series) {
            return window.dash_clientside.no_update;
        }

        var dates = rawData.dates;
        var futureDates = rawData.futureDates || [];
        var height = rawData.height || 380;
        var yTitle = rawData.yTitle || "Unique Patients";
        var hasFuture = futureDates.length > 0;

        // Downsample to ~500 points max for display (chart is only ~500px wide)
        var maxPoints = 500;
        var step = dates.length > maxPoints ? Math.ceil(dates.length / maxPoints) : 1;
        var displayDates = step > 1 ? downsample(dates, step) : dates;

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

            var traceObj = {
                x: displayDates,
                y: yVals,
                name: s.name,
                mode: "lines",
                line: {color: s.color, width: 1.5},
                fillcolor: hexToRgba(s.color, 0.5),
                stackgroup: "one",
                hovertemplate: s.name + ": %{y:.0f}<extra></extra>"
            };

            // Preserve visibility if it was explicitly set
            if (visibilityMap.hasOwnProperty(s.name)) {
                traceObj.visible = visibilityMap[s.name];
            }

            traces.push(traceObj);
        }

        // Future projection traces (lighter fill, dotted line, no smoothing)
        if (hasFuture) {
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

                // Connect to last past point
                var lastPastDate = displayDates[displayDates.length - 1];
                var lastPastVal = traces[i].y[traces[i].y.length - 1];

                var futureTraceObj = {
                    x: [lastPastDate].concat(futureDates),
                    y: [lastPastVal].concat(futureVals),
                    name: s.name + " (scheduled)",
                    mode: "lines",
                    line: {color: s.color, width: 1, dash: "dot"},
                    fillcolor: hexToRgba(s.color, 0.2),
                    stackgroup: "future",
                    showlegend: false,
                    hovertemplate: s.name + " (scheduled): %{y:.0f}<extra></extra>"
                };

                // Preserve visibility (use base name)
                if (visibilityMap.hasOwnProperty(s.name)) {
                    futureTraceObj.visible = visibilityMap[s.name];
                }

                traces.push(futureTraceObj);
            }
        }

        // Add invisible total trace for hover (sum of smoothed series)
        traces.unshift({
            x: displayDates,
            y: totals,
            name: "Total",
            mode: "lines",
            line: {color: "transparent", width: 0},
            hovertemplate: "<b>Total: %{y:.0f}</b><extra></extra>",
            showlegend: false
        });

        var smoothed = smoothPct > 0;
        return {
            data: traces,
            layout: {
                height: height,
                xaxis: {title: "Date", showgrid: false},
                yaxis: {title: yTitle + (smoothed ? " (smoothed)" : ""), gridcolor: "#E5E7EB"},
                legend: {orientation: "h", yanchor: "bottom", y: 1.02, xanchor: "left", x: 0},
                margin: {l: 48, r: 16, t: 16, b: 48},
                plot_bgcolor: "white",
                paper_bgcolor: "white",
                font: {family: "Inter, system-ui, sans-serif", size: 12, color: "#374151"},
                hovermode: "x unified",
                hoverlabel: {align: "left"}
            }
        };
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
 * Downsample an array by taking every nth element (for dates/labels).
 */
function downsample(arr, step) {
    var result = [];
    for (var i = 0; i < arr.length; i += step) {
        result.push(arr[i]);
    }
    return result;
}

/**
 * Downsample numeric values by averaging buckets of size `step`.
 * This preserves the visual shape better than just sampling.
 */
function downsampleAvg(arr, step) {
    var result = [];
    for (var i = 0; i < arr.length; i += step) {
        var end = Math.min(i + step, arr.length);
        var sum = 0;
        for (var j = i; j < end; j++) {
            sum += arr[j];
        }
        result.push(sum / (end - i));
    }
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
     * Build operating hours ribbon chart with clientside smoothing.
     * @param {Object} rawData - {pastSeries, futureSeries, yAxis, today}
     * @param {number} smoothVal - Rolling average window size (0 = no smoothing)
     */
    smoothChart: function(rawData, smoothVal) {
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

        // Downsample to ~500 points max for performance (chart is only ~500px wide)
        var maxPoints = 500;

        // Process past series (solid fill with edge lines)
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

        // Process future series (lighter fill, connect to past)
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

            // Prepend past end point to connect the series
            var pastEnd = pastEndPoints[s.name];
            if (pastEnd && dates.length > 0) {
                dates.unshift(pastEnd.date);
                startHours.unshift(pastEnd.start);
                endHours.unshift(pastEnd.end);
            }

            // Build hover text
            var hoverText = [];
            for (var j = 0; j < dates.length; j++) {
                var d = new Date(dates[j]);
                var dateStr = d.toLocaleDateString("en-US", {month: "short", day: "numeric"});
                var label = (j === 0 && pastEnd) ? s.name : s.name + " (scheduled)";
                hoverText.push("<b>" + label + "</b><br>" + dateStr + ": " +
                    hourToTimeStr(startHours[j]) + " - " + hourToTimeStr(endHours[j]));
            }

            var color = s.color;
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

        return {
            data: traces,
            layout: {
                height: 380,
                font: {family: "Inter, system-ui, sans-serif", size: 11},
                plot_bgcolor: "#FFFFFF",
                paper_bgcolor: "#FFFFFF",
                margin: {l: 40, r: 16, t: 16, b: 30},
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
            }
        };
    }
};
