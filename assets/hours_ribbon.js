/**
 * Operating hours ribbon/band visualization.
 * Used by operations and home pages.
 * Depends on: 00_utils.js (hexToRgba, rollingAvg, downsample, downsampleAvg,
 *             formatDatesForBars, filterByIndices, hourToTimeStr)
 */

window.dash_clientside = window.dash_clientside || {};

// ---------------------------------------------------------------------------
// Operating Hours Ribbon Chart (band visualization)
// ---------------------------------------------------------------------------

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
            // Return empty figure with stable layout to prevent container collapse
            return {
                data: [],
                layout: {
                    uirevision: "hours-timeseries",
                    plot_bgcolor: "rgba(0,0,0,0)",
                    paper_bgcolor: "rgba(0,0,0,0)",
                    margin: {l: 36, r: 8, t: 8, b: 32, pad: 0},
                    xaxis: {visible: false},
                    yaxis: {visible: false},
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

        // Build a set of holiday date strings for gap insertion
        var holidaySet = {};
        if (rawData.holidays) {
            for (var hi = 0; hi < rawData.holidays.length; hi++) {
                holidaySet[rawData.holidays[hi].split("T")[0]] = true;
            }
        }

        // Insert null gaps for weekends and holidays so Plotly breaks
        // lines and fills naturally (no rangebreaks needed).
        function insertGaps(dates, startH, endH) {
            if (!dates || dates.length < 2) return {dates: dates, startHours: startH, endHours: endH};
            var dataMap = {};
            for (var gi = 0; gi < dates.length; gi++) {
                dataMap[dates[gi].split("T")[0]] = {s: startH[gi], e: endH[gi]};
            }
            var first = new Date(dates[0].split("T")[0] + "T12:00:00");
            var last = new Date(dates[dates.length - 1].split("T")[0] + "T12:00:00");
            var outD = [], outS = [], outE = [];
            for (var d = new Date(first); d <= last; d.setDate(d.getDate() + 1)) {
                var iso = d.toISOString().split("T")[0];
                var dow = d.getUTCDay(); // 0=Sun, 6=Sat — use UTC to match ISO date
                if (dow === 0 || dow === 6 || holidaySet[iso]) {
                    // Insert null gap for non-business days
                    outD.push(iso + "T00:00:00");
                    outS.push(null);
                    outE.push(null);
                } else if (dataMap[iso]) {
                    outD.push(iso + "T00:00:00");
                    outS.push(dataMap[iso].s);
                    outE.push(dataMap[iso].e);
                } else {
                    // Weekday with no data — also a gap
                    outD.push(iso + "T00:00:00");
                    outS.push(null);
                    outE.push(null);
                }
            }
            return {dates: outD, startHours: outS, endHours: outE};
        }

        // Process past series
        for (var i = 0; i < rawData.pastSeries.length; i++) {
            var s = rawData.pastSeries[i];
            var dates, startHours, endHours;
            if (chartType === "bar") {
                // Bars get null gaps for weekends/holidays so they don't span non-working days
                var gapped = insertGaps(s.dates, s.startHours.slice(), s.endHours.slice());
                dates = gapped.dates;
                startHours = gapped.startHours;
                endHours = gapped.endHours;
            } else {
                // Ribbon/line: continuous across weekends (tonexty can't handle null gaps)
                dates = s.dates;
                startHours = s.startHours.slice();
                endHours = s.endHours.slice();
            }

            // Downsample if needed
            var step = dates.length > maxPoints ? Math.ceil(dates.length / maxPoints) : 1;
            if (step > 1) {
                dates = downsample(dates, step);
                startHours = downsampleAvg(startHours, step);
                endHours = downsampleAvg(endHours, step);
            }

            // Keep raw values for hover text (always show actuals)
            var rawStart = startHours.slice();
            var rawEnd = endHours.slice();

            // Apply smoothing after downsampling (skip for bar charts)
            if (smoothVal > 0 && chartType !== "bar") {
                startHours = rollingAvg(startHours, windowSize);
                endHours = rollingAvg(endHours, windowSize);
            }

            // Store end point for connecting to future (use smoothed values)
            if (dates.length > 0) {
                pastEndPoints[s.name] = {
                    date: dates[dates.length - 1],
                    start: startHours[startHours.length - 1],
                    end: endHours[endHours.length - 1]
                };
            }

            // Build hover text from raw (unsmoothed) values
            var hoverText = [];
            for (var j = 0; j < dates.length; j++) {
                var _hp = parseIsoDate(dates[j]);
                var _hMonths = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
                var dateStr = _hp.valid ? _hMonths[_hp.month] + " " + _hp.day : dates[j];
                hoverText.push("<b>" + s.name + "</b><br>" + dateStr + ": " +
                    hourToTimeStr(rawStart[j]) + " - " + hourToTimeStr(rawEnd[j]));
            }

            var color = s.color;
            var fillColor = hexToRgba(color, pastFillOpacity);

            if (chartType === "bar") {
                // Floating bar chart: bars span from startHours to endHours
                // Use date x-values directly (not categorical) to avoid date parsing issues
                var durations = [];
                var baseHours = [];
                for (var j = 0; j < startHours.length; j++) {
                    durations.push(endHours[j] - startHours[j]);
                    baseHours.push(startHours[j]);
                }
                traces.push({
                    x: dates,
                    y: durations,
                    base: baseHours,
                    name: s.name,
                    type: "bar",
                    marker: {color: hexToRgba(color, 0.7), line: {color: "rgba(255,255,255,0.6)", width: 0.5}},
                    hovertemplate: "%{text}<extra></extra>",
                    text: hoverText,
                    textposition: "none"
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
                    hovertemplate: "%{text}<extra></extra>",
                    connectgaps: true
                });
                traces.push({
                    x: dates,
                    y: endHours,
                    name: s.name + " End",
                    mode: "lines",
                    line: {color: color, width: 2, dash: "dash"},
                    showlegend: false,
                    hoverinfo: "skip",
                    connectgaps: true
                });
            } else {
                // Ribbon (band) chart - default
                // Upper bound (end hours) - invisible anchor for tonexty fill
                traces.push({
                    x: dates,
                    y: endHours,
                    mode: "lines",
                    line: {width: 0},
                    showlegend: false,
                    hoverinfo: "skip",
                    connectgaps: true
                });

                // Lower bound (start hours) with fill to previous trace
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
                    hovertemplate: "%{text}<extra></extra>",
                    connectgaps: true
                });

                // Edge line - top (end hours)
                traces.push({
                    x: dates,
                    y: endHours,
                    mode: "lines",
                    line: {color: color, width: 1.5},
                    showlegend: false,
                    hoverinfo: "skip",
                    connectgaps: true
                });

                // Edge line - bottom (start hours)
                traces.push({
                    x: dates,
                    y: startHours,
                    mode: "lines",
                    line: {color: color, width: 1.5},
                    showlegend: false,
                    hoverinfo: "skip",
                    connectgaps: true
                });
            }
        }

        // Process future series (lighter fill for ribbon, lighter opacity bars, dotted lines)
        if (chartType === "ribbon" || chartType === "bar" || chartType === "line") {
            for (var i = 0; i < rawData.futureSeries.length; i++) {
                var s = rawData.futureSeries[i];
                var dates, startHours, endHours;
                if (chartType === "bar") {
                    var futGapped = insertGaps(s.dates, s.startHours.slice(), s.endHours.slice());
                    dates = futGapped.dates;
                    startHours = futGapped.startHours;
                    endHours = futGapped.endHours;
                } else {
                    dates = s.dates;
                    startHours = s.startHours.slice();
                    endHours = s.endHours.slice();
                }

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
                    var _fp = parseIsoDate(dates[j]);
                    var _fMonths = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
                    var dateStr = _fp.valid ? _fMonths[_fp.month] + " " + _fp.day : dates[j];
                    hoverText.push("<b>" + s.name + " (scheduled)</b><br>" + dateStr + ": " +
                        hourToTimeStr(startHours[j]) + " - " + hourToTimeStr(endHours[j]));
                }

                var color = s.color;

                if (chartType === "bar") {
                    // Floating bar chart for future data (pre-computed rgba to avoid flash)
                    var durations = [];
                    var baseHours = [];
                    for (var j = 0; j < startHours.length; j++) {
                        durations.push(endHours[j] - startHours[j]);
                        baseHours.push(startHours[j]);
                    }
                    traces.push({
                        x: dates,
                        y: durations,
                        base: baseHours,
                        name: s.name + " (scheduled)",
                        type: "bar",
                        marker: {color: hexToRgba(color, 0.35), line: {color: "rgba(255,255,255,0.6)", width: 0.5}},
                        hovertemplate: "%{text}<extra></extra>",
                        text: hoverText,
                        textposition: "none",
                        showlegend: false
                    });
                } else if (chartType === "line") {
                    // Line chart for future data (dotted, connects to past end)
                    var pastEnd = pastEndPoints[s.name];
                    var hasConn = false;
                    if (pastEnd && dates.length > 0) {
                        dates.unshift(pastEnd.date);
                        startHours.unshift(pastEnd.start);
                        endHours.unshift(pastEnd.end);
                        hasConn = true;
                    }

                    // Future start line (dotted)
                    traces.push({
                        x: dates,
                        y: startHours,
                        name: s.name + " (scheduled)",
                        mode: "lines",
                        line: {color: color, width: 1.5, dash: "dot"},
                        showlegend: false,
                        hoverinfo: "skip",
                        connectgaps: true
                    });

                    // Future end line (dotted)
                    traces.push({
                        x: dates,
                        y: endHours,
                        mode: "lines",
                        line: {color: color, width: 1.5, dash: "dot"},
                        showlegend: false,
                        hoverinfo: "skip",
                        connectgaps: true
                    });

                    // Hover-only trace for future points (excludes connection point)
                    var hoverDates = hasConn ? dates.slice(1) : dates;
                    var hoverY = hasConn ? startHours.slice(1) : startHours;
                    if (hoverDates.length > 0) {
                        traces.push({
                            x: hoverDates,
                            y: hoverY,
                            mode: "lines",
                            line: {width: 0},
                            showlegend: false,
                            text: hoverText,
                            hovertemplate: "%{text}<extra></extra>"
                        });
                    }
                } else {
                    // Ribbon chart - prepend past end point to connect visually
                    var pastEnd = pastEndPoints[s.name];
                    var hasConn = false;
                    if (pastEnd && dates.length > 0) {
                        dates.unshift(pastEnd.date);
                        startHours.unshift(pastEnd.start);
                        endHours.unshift(pastEnd.end);
                        hasConn = true;
                    }

                    var fillColor = hexToRgba(color, futureFillOpacity);

                    // Upper bound (fill anchor)
                    traces.push({
                        x: dates,
                        y: endHours,
                        mode: "lines",
                        line: {width: 0},
                        showlegend: false,
                        hoverinfo: "skip",
                        connectgaps: true
                    });

                    // Lower bound with fill
                    traces.push({
                        x: dates,
                        y: startHours,
                        mode: "lines",
                        line: {width: 0},
                        fill: "tonexty",
                        fillcolor: fillColor,
                        name: s.name + " (scheduled)",
                        showlegend: false,
                        hoverinfo: "skip",
                        connectgaps: true
                    });

                    // Hover-only trace for future points (excludes connection point)
                    var hoverDates = hasConn ? dates.slice(1) : dates;
                    var hoverY = hasConn ? startHours.slice(1) : startHours;
                    if (hoverDates.length > 0) {
                        traces.push({
                            x: hoverDates,
                            y: hoverY,
                            mode: "lines",
                            line: {width: 0},
                            showlegend: false,
                            text: hoverText,
                            hovertemplate: "%{text}<extra></extra>"
                        });
                    }

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

        // Place divider at the last past data point (not calendar today,
        // which may fall on a weekend with no data)
        var adjustedToday = "";
        for (var pi = 0; pi < rawData.pastSeries.length; pi++) {
            var pd = rawData.pastSeries[pi].dates;
            if (pd && pd.length > 0) {
                var d = pd[pd.length - 1].split('T')[0];
                if (d > adjustedToday) adjustedToday = d;
            }
        }
        if (!adjustedToday) adjustedToday = today.split('T')[0];

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
            uirevision: "hours-timeseries",
            font: {family: "Inter, system-ui, sans-serif", size: 11},
            plot_bgcolor: "rgba(0,0,0,0)",
            paper_bgcolor: "rgba(0,0,0,0)",
            margin: {l: 36, r: 8, t: 8, b: 32, pad: 0},
            showlegend: false,
            hovermode: "x unified",
            transition: {duration: 0},
            yaxis: {
                range: [yAxis.min, yAxis.max],
                tickvals: yAxis.tickvals,
                ticktext: yAxis.ticktext,
                gridcolor: "#E5E7EB",
                automargin: true
            },
            shapes: shapes
        };

        layout.xaxis = {
            type: "date",
            side: "bottom",
            showgrid: false,
            automargin: true,
            ticklabelposition: "outside bottom",
            tickmode: "auto"
        };

        if (chartType === "bar") {
            // Rangebreaks collapse weekend/holiday gaps on the date axis.
            // Safe for bars (no tonexty fill issues).
            var rangebreaks = [{bounds: ["sat", "mon"]}];
            if (rawData.holidays && rawData.holidays.length > 0) {
                for (var hi = 0; hi < rawData.holidays.length; hi++) {
                    var hd = rawData.holidays[hi].split("T")[0];
                    var nextDay = new Date(hd + "T12:00:00");
                    nextDay.setDate(nextDay.getDate() + 1);
                    var ndStr = nextDay.toISOString().split("T")[0];
                    rangebreaks.push({values: [hd + " 00:00:00", ndStr + " 00:00:00"]});
                }
            }
            layout.xaxis.rangebreaks = rangebreaks;
            layout.barmode = "overlay";
            layout.bargap = 0.15;
            layout.bargroupgap = 0;
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
                var _rlp = parseIsoDate(lastDate);
                var startDateObj = _rlp.valid ? new Date(_rlp.year, _rlp.month, _rlp.day - days) : new Date();
                var startDate = localDateToIso(startDateObj);

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

    smoothChartWithTypeAndRange: function(rawData, smoothVal, chartType, rangeDays, weekOffset) {
        // Force a clean Plotly instance when switching between calendar/week
        // and timeseries modes to prevent cross-mode layout carryover.
        var chartEl = document.getElementById('home-chart-hours')
                   || document.getElementById('ops-chart-hours');
        var modeKey = (rangeDays === "thisweek") ? "week" : (chartType === "bar" ? "bar" : "timeseries");
        var modeStateKey = "_hoursLastMode_" + (chartEl ? chartEl.id : "default");
        var prevMode = window[modeStateKey];
        if (chartEl && prevMode && prevMode !== modeKey) {
            var plotEl = chartEl.querySelector('.js-plotly-plot');
            if (plotEl && typeof Plotly !== "undefined" && Plotly.purge) {
                Plotly.purge(plotEl);
            }
        }
        window[modeStateKey] = modeKey;

        // Calendar mode: no debounce needed
        if (rangeDays === "thisweek") {
            window._ribbonChartData = rawData;
            var calFig = window.dash_clientside.hoursRibbon.renderCalendarWeek(rawData, weekOffset || 0);
            setTimeout(window.dash_clientside.hoursRibbon._setupCalendarHover, 150);
            return calFig;
        }

        if (!rawData || !rawData.pastSeries || rawData.pastSeries.length === 0) {
            return window.dash_clientside.hoursRibbon.smoothChartWithType(rawData, smoothVal, chartType);
        }
        // Always return the next figure through Dash so the component state
        // stays consistent when switching between week and non-week modes.
        return window.dash_clientside.hoursRibbon._buildWithRange(rawData, smoothVal, chartType, rangeDays);
    },

    /**
     * Render a weekly calendar view of operating hours.
     * Shows Mon-Fri columns with time-of-day on Y-axis and colored bands
     * per department representing operating windows (first start to last end).
     *
     * @param {Object} rawData - {pastSeries, futureSeries, yAxis, today}
     * @returns {Object} Plotly figure
     */
    renderCalendarWeek: function(rawData, weekOffset) {
        if (!rawData || (!rawData.pastSeries && !rawData.futureSeries)) {
            return {
                data: [],
                layout: {
                    annotations: [{
                        text: "No operating hours data available",
                        xref: "paper", yref: "paper",
                        x: 0.5, y: 0.5, showarrow: false,
                        font: {size: 14, color: "#6B7280"}
                    }]
                }
            };
        }

        // Calculate target week Mon-Fri (offset in weeks from current)
        var now = new Date();
        var dayOfWeek = now.getDay(); // 0=Sun, 1=Mon, ..., 6=Sat
        var mondayOffset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek;
        var monday = new Date(now);
        monday.setDate(now.getDate() + mondayOffset + (weekOffset || 0) * 7);
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

        // Theme-aware grid + separator colors (shapes use fixed values,
        // so pick at build time based on current <html data-theme>).
        var _isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        var _hourGridColor = _isDark ? "rgba(140,145,160,0.08)" : "#E5E7EB";
        var _daySepColor   = _isDark ? "rgba(140,145,160,0.14)" : "#E5E7EB";

        // Horizontal gridlines at each hour
        for (var h = Math.ceil(yMin); h <= Math.floor(yMax); h++) {
            shapes.push({
                type: "line",
                x0: -0.5, x1: 4.5, y0: h, y1: h,
                line: {color: _hourGridColor, width: 0.5},
                xref: "x", yref: "y", layer: "below"
            });
        }

        // Vertical day separators
        for (var d = 0; d < 4; d++) {
            shapes.push({
                type: "line",
                x0: d + 0.5, x1: d + 0.5, y0: yMin, y1: yMax,
                line: {color: _daySepColor, width: 1},
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

        // Store shape info for hover highlight handler (per-element)
        window._calendarHoverData = window._calendarHoverData || {};
        var shapeInfo = bandShapeMap.map(function(si) {
            var orig = shapes[si].fillcolor;
            var hover = orig.replace(/[\d.]+\)$/, function(m) {
                return Math.min(0.85, parseFloat(m) + 0.25) + ")";
            });
            return {idx: si, orig: orig, hover: hover};
        });
        // Store under a key that _setupCalendarHover will pick up
        window._calendarHoverData._pending = {
            shapeInfo: shapeInfo,
            bandMap: hoverBandIdx,
        };

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
            uirevision: "hours-calendar",
            font: {family: "Inter, system-ui, sans-serif", size: 11},
            plot_bgcolor: "rgba(0,0,0,0)",
            paper_bgcolor: "rgba(0,0,0,0)",
            margin: {l: 44, r: 8, t: 32, b: 8, pad: 0, autoexpand: false},
            showlegend: false,
            hovermode: "closest",
            hoverdistance: -1,
            dragmode: false,
            transition: {duration: 0},
            xaxis: {
                type: "linear",
                tickmode: "array",
                tickvals: [0, 1, 2, 3, 4],
                ticktext: dayLabels,
                range: [-0.5, 4.5],
                showgrid: false,
                fixedrange: true,
                side: "top",
                ticklabelposition: "outside top",
                automargin: false,
                dtick: null,
                nticks: null,
                categoryorder: null,
                categoryarray: null,
                zeroline: false
            },
            yaxis: {
                range: [yMax, yMin],
                tickmode: "array",
                tickvals: tickvals,
                ticktext: ticktext,
                showgrid: false,
                fixedrange: true,
                automargin: false,
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
     * Supports multiple chart instances by storing hover data per element.
     */
    _setupCalendarHover: function(targetId) {
        var pending = window._calendarHoverData && window._calendarHoverData._pending;
        if (!pending) return;

        // Find the target element — try provided ID, then known IDs
        var ids = targetId ? [targetId] : ["home-chart-hours", "ops-chart-hours"];
        var wrapper = null;
        for (var i = 0; i < ids.length; i++) {
            wrapper = document.getElementById(ids[i]);
            if (wrapper) break;
        }
        if (!wrapper) {
            requestAnimationFrame(function() {
                window.dash_clientside.hoursRibbon._setupCalendarHover(targetId);
            });
            return;
        }

        // The Plotly div is the child with class "js-plotly-plot", or the wrapper itself
        var el = wrapper.querySelector(".js-plotly-plot") || wrapper;

        if (typeof el.on !== "function") {
            if (typeof wrapper.on === "function") {
                el = wrapper;
            } else {
                requestAnimationFrame(function() {
                    window.dash_clientside.hoursRibbon._setupCalendarHover(targetId);
                });
                return;
            }
        }

        // Tear down previous listeners
        if (el._calCleanup) el._calCleanup();

        // Consume pending data and store on the element
        var info = pending.shapeInfo;
        var bandMap = pending.bandMap;
        delete window._calendarHoverData._pending;

        if (!info || !info.length) return;

        var lastHovered = -1;

        function onHover(data) {
            if (!data.points || !data.points.length) return;
            var ptIdx = data.points[0].pointIndex;
            var bandIdx = (bandMap && bandMap[ptIdx] !== undefined)
                ? bandMap[ptIdx] : ptIdx;
            if (bandIdx === lastHovered) return;

            // Restore previous
            if (lastHovered >= 0 && lastHovered < info.length) {
                var prev = info[lastHovered];
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
                lastHovered = bandIdx;
            }
        }

        function onUnhover() {
            if (lastHovered >= 0 && lastHovered < info.length) {
                var prev = info[lastHovered];
                var u = {};
                u["shapes[" + prev.idx + "].fillcolor"] = prev.orig;
                Plotly.relayout(el, u);
                lastHovered = -1;
            }
        }

        el.on("plotly_hover", onHover);
        el.on("plotly_unhover", onUnhover);

        el._calCleanup = function() {
            el.removeListener("plotly_hover", onHover);
            el.removeListener("plotly_unhover", onUnhover);
            lastHovered = -1;
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
    var startStr = (typeof startDate === 'string') ? startDate.split('T')[0] : localDateToIso(new Date(startDate));
    var endStr = (typeof endDate === 'string') ? endDate.split('T')[0] : localDateToIso(new Date(endDate));

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
// Dynamic Y-Axis Scaling for Hours Ribbon Charts on Pan
// ---------------------------------------------------------------------------

window.dash_clientside.hoursYAxis = {
    /**
     * Recalculate y-axis range when user pans the hours ribbon chart.
     * Hours data uses startHours/endHours arrays (decimal hours, e.g. 8.5 = 8:30am).
     */
    updateOnPan: function(relayoutData, currentFigure, rawData, rangeMode) {
        if (!relayoutData || !currentFigure || !rawData ||
            (!rawData.pastSeries && !rawData.futureSeries)) {
            return window.dash_clientside.no_update;
        }

        // Never rescale the calendar/week view from stale relayout data that
        // may persist from a prior non-week mode.
        if (rangeMode === "thisweek" ||
            currentFigure.layout?.dragmode === false ||
            (currentFigure.layout?.xaxis?.range &&
             typeof currentFigure.layout.xaxis.range[0] === "number")) {
            return window.dash_clientside.no_update;
        }

        // Extract x-axis range from relayout data
        var startDate, endDate;
        if (relayoutData['xaxis.range[0]'] !== undefined &&
            relayoutData['xaxis.range[1]'] !== undefined) {
            startDate = relayoutData['xaxis.range[0]'];
            endDate = relayoutData['xaxis.range[1]'];
        } else if (relayoutData['xaxis.range'] &&
                   relayoutData['xaxis.range'].length === 2) {
            startDate = relayoutData['xaxis.range'][0];
            endDate = relayoutData['xaxis.range'][1];
        } else {
            return window.dash_clientside.no_update;
        }

        var startStr = String(startDate).split('T')[0].split(' ')[0];
        var endStr = String(endDate).split('T')[0].split(' ')[0];

        // Skip if dates look like category indices
        if (/^\d+(\.\d+)?$/.test(startStr)) {
            return window.dash_clientside.no_update;
        }

        // Find min/max hours in visible range
        var minHour = 24, maxHour = 0;
        var allSeries = (rawData.pastSeries || []).concat(rawData.futureSeries || []);
        for (var i = 0; i < allSeries.length; i++) {
            var s = allSeries[i];
            if (!s.dates) continue;
            for (var j = 0; j < s.dates.length; j++) {
                var d = s.dates[j].split('T')[0];
                if (d < startStr || d > endStr) continue;
                if (s.startHours[j] < minHour) minHour = s.startHours[j];
                if (s.endHours[j] > maxHour) maxHour = s.endHours[j];
            }
        }

        if (minHour >= maxHour) return window.dash_clientside.no_update;

        var yMin = Math.max(0, Math.floor(minHour * 2) / 2 - 0.5);
        var yMax = Math.min(24, Math.ceil(maxHour * 2) / 2 + 0.5);

        // Build tick labels
        var tickvals = [], ticktext = [];
        for (var h = Math.ceil(yMin); h <= Math.floor(yMax); h++) {
            tickvals.push(h);
            ticktext.push(h === 0 ? "12am" : h < 12 ? h + "am" : h === 12 ? "12pm" : (h - 12) + "pm");
        }

        // Skip if unchanged (prevent relayout loop)
        if (currentFigure.layout && currentFigure.layout.yaxis &&
            currentFigure.layout.yaxis.range &&
            currentFigure.layout.yaxis.range[0] === yMin &&
            currentFigure.layout.yaxis.range[1] === yMax) {
            return window.dash_clientside.no_update;
        }

        var newFigure = JSON.parse(JSON.stringify(currentFigure));
        newFigure.layout.yaxis = newFigure.layout.yaxis || {};
        newFigure.layout.yaxis.range = [yMin, yMax];
        newFigure.layout.yaxis.tickvals = tickvals;
        newFigure.layout.yaxis.ticktext = ticktext;
        newFigure.layout.yaxis.autorange = false;

        return newFigure;
    }
};
