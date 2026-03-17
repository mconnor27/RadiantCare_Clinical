/**
 * Shared utility functions for clientside chart rendering.
 * Loaded first (00_ prefix) so all other chart modules can use these.
 */

window.dash_clientside = window.dash_clientside || {};

// ---------------------------------------------------------------------------
// Color utilities
// ---------------------------------------------------------------------------

function hexToRgba(hex, alpha) {
    var h = hex.replace("#", "");
    var r = parseInt(h.substring(0, 2), 16);
    var g = parseInt(h.substring(2, 4), 16);
    var b = parseInt(h.substring(4, 6), 16);
    return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
}

// ---------------------------------------------------------------------------
// Smoothing algorithms
// ---------------------------------------------------------------------------

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

/**
 * Centered rolling average using prefix sums — O(n).
 * Null-aware: preserves null values (e.g. pre-go-live periods) and only
 * averages over non-null neighbors so smoothing doesn't bleed before go-live.
 */
function rollingAvg(arr, windowSize) {
    if (windowSize <= 1) return arr.slice();
    var n = arr.length;
    var result = new Array(n);
    var halfW = Math.floor(windowSize / 2);

    // Check if array has nulls (e.g. pre-go-live periods)
    var hasNulls = false;
    for (var i = 0; i < n; i++) {
        if (arr[i] === null || arr[i] === undefined) { hasNulls = true; break; }
    }

    if (hasNulls) {
        // Null-aware path: preserve nulls, only average non-null neighbors
        for (var i = 0; i < n; i++) {
            if (arr[i] === null || arr[i] === undefined) {
                result[i] = null;
                continue;
            }
            var left = Math.max(0, i - halfW);
            var right = Math.min(n - 1, i + halfW);
            var sum = 0, count = 0;
            for (var j = left; j <= right; j++) {
                if (arr[j] !== null && arr[j] !== undefined) {
                    sum += arr[j];
                    count++;
                }
            }
            result[i] = count > 0 ? sum / count : null;
        }
        return result;
    }

    // Fast prefix-sum path for arrays without nulls
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
// Downsampling
// ---------------------------------------------------------------------------

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
    return result;
}

// ---------------------------------------------------------------------------
// Date / array utilities
// ---------------------------------------------------------------------------

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
 * Detect aggregation level from an array of ISO date strings.
 * Returns "Y" (yearly), "M" (monthly), "W" (weekly), or "D" (daily).
 */
function detectAggLevel(dates) {
    if (!dates || dates.length < 2) {
        // Single point: check if it's Jan 1 (yearly) or day 1 (monthly)
        if (dates && dates.length === 1) {
            var p = parseIsoDate(dates[0]);
            if (p.valid && p.month === 0 && p.day === 1) return "Y";
            if (p.valid && p.day === 1) return "M";
        }
        return "M";
    }
    var first = parseIsoDate(dates[0]);
    var second = parseIsoDate(dates[1]);
    if (!first.valid || !second.valid) return "W";
    // All dates on day 1 and months differ by ≥1 → monthly or yearly
    if (first.day === 1 && second.day === 1) {
        var monthDiff = (second.year - first.year) * 12 + (second.month - first.month);
        if (monthDiff >= 12) return "Y";
        if (monthDiff >= 1) return "M";
    }
    // Gap between first two dates
    var d1 = new Date(first.year, first.month, first.day);
    var d2 = new Date(second.year, second.month, second.day);
    var gap = Math.round((d2 - d1) / 86400000);
    if (gap >= 5) return "W";
    return "D";
}

/**
 * Format dates for bar chart x-axis and return {labels, validIndices}.
 * Only includes dates that parse correctly.
 * Adapts label format based on aggregation level and bar count:
 *   Yearly  → "2025"
 *   Monthly → "Mar '26" (few bars) or "M '26" / "3/26" (many bars)
 *   Weekly/Daily → "Mar 16 '26" (≤12) or "3/16" (>12, single year) or "3/16 '26" (>12, multi year)
 * Labels must be unique to prevent Plotly from merging bars.
 */
function formatDatesForBars(dates) {
    if (!dates || dates.length === 0) return {labels: [], validIndices: []};

    var labels = [];
    var validIndices = [];
    var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    var aggLevel = detectAggLevel(dates);
    var n = dates.length;

    // Detect whether dates span multiple years (need year suffix for uniqueness)
    var firstParsed = parseIsoDate(dates[0]);
    var lastParsed = parseIsoDate(dates[dates.length - 1]);
    var multiYear = firstParsed.valid && lastParsed.valid && firstParsed.year !== lastParsed.year;

    for (var i = 0; i < n; i++) {
        var parsed = parseIsoDate(dates[i]);
        if (!parsed.valid) continue;

        validIndices.push(i);
        var shortYear = "'" + String(parsed.year).slice(-2);

        if (aggLevel === "Y") {
            labels.push(String(parsed.year));
        } else if (aggLevel === "M") {
            // Monthly: "Mar '26" for ≤18, shorter for more
            if (n <= 18) {
                labels.push(months[parsed.month] + " " + shortYear);
            } else {
                // Compact: "3/'26"
                labels.push((parsed.month + 1) + "/" + shortYear);
            }
        } else {
            // Weekly/Daily
            if (n <= 12) {
                labels.push(months[parsed.month] + " " + parsed.day + " " + shortYear);
            } else if (multiYear) {
                // Compact with year for disambiguation: "3/16 '26"
                labels.push((parsed.month + 1) + "/" + parsed.day + " " + shortYear);
            } else {
                // Compact without year: "3/16"
                labels.push((parsed.month + 1) + "/" + parsed.day);
            }
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

// ---------------------------------------------------------------------------
// Time formatting
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

// ---------------------------------------------------------------------------
// PNG Export Utility
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Chart Settings Toggle
// ---------------------------------------------------------------------------

window.dash_clientside.chartSettings = {
    /**
     * Toggle a settings panel's visibility.
     * Used by register_chart_callbacks() to replace per-chart Python callbacks.
     */
    toggle: function(n_clicks, current_style) {
        if (!n_clicks) return window.dash_clientside.no_update;
        var hidden = !current_style || current_style.display === "none";
        return {display: hidden ? "block" : "none"};
    }
};

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

        var el = document.getElementById(graphId);
        if (!el) {
            console.warn("Chart not found:", graphId);
            return window.dash_clientside.no_update;
        }

        // dcc.Graph wraps the plot in a div — find the actual Plotly element
        var graphEl = el.querySelector(".js-plotly-plot") || el;

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
