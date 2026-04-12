/**
 * Machine Downtime page — clientside renderers.
 * Depends on: 00_utils.js (hexToRgba, rollingAvg, loess)
 */

/**
 * Aggregate daily date-strings + parallel value arrays into D/W/M buckets.
 * Returns {dates: [...], values: [[...], [...], ...]}.
 */
function _aggregateDates(rawDates, valueSets, agg) {
    if (!agg || agg === "D") {
        return {dates: rawDates, values: valueSets};
    }

    // Build bucket key for each raw date
    var buckets = {};  // key → {date: first-date-str, sums: []}
    var order = [];
    for (var i = 0; i < rawDates.length; i++) {
        var d = new Date(rawDates[i]);
        var key;
        if (agg === "W") {
            // ISO week: Monday-based — subtract dayOfWeek to get Monday
            var day = d.getUTCDay();
            var mon = new Date(d);
            mon.setUTCDate(mon.getUTCDate() - ((day + 6) % 7));
            key = mon.toISOString().slice(0, 10);
        } else {
            // Monthly
            key = rawDates[i].slice(0, 7) + "-01";
        }

        if (!buckets[key]) {
            buckets[key] = {date: key, sums: valueSets.map(function() { return 0; })};
            order.push(key);
        }
        for (var s = 0; s < valueSets.length; s++) {
            buckets[key].sums[s] += (valueSets[s][i] || 0);
        }
    }

    var dates = [];
    var aggValues = valueSets.map(function() { return []; });
    for (var j = 0; j < order.length; j++) {
        var b = buckets[order[j]];
        dates.push(b.date);
        for (var k = 0; k < valueSets.length; k++) {
            aggValues[k].push(Math.round(b.sums[k] * 100) / 100);
        }
    }

    return {dates: dates, values: aggValues};
}

window.dash_clientside = window.dash_clientside || {};

window.dash_clientside.machinesDowntime = {

    // -----------------------------------------------------------------------
    // Drill-level visibility toggle + breadcrumb
    // -----------------------------------------------------------------------
    toggleDrillLevel: function(drill) {
        if (!drill) drill = {level: 1};
        var level = drill.level || 1;
        var show = {display: "block"};
        var hide = {display: "none"};

        var l1 = level === 1 ? show : hide;
        var l2 = level === 2 ? show : hide;
        var l3 = level === 3 ? show : hide;

        // Breadcrumb — parent levels are clickable links, current level is plain text
        var linkStyle = "cursor:pointer;text-decoration:underline;";
        var sep = ' <span style="color:#9CA3AF;"> \u203A </span> ';
        var crumbs = "";
        var dateLabel = "";
        if (level === 1) {
            crumbs = '<span style="color:#7C2A83;">All Years</span>';
        } else if (level === 2) {
            crumbs = '<span class="bc-link" data-level="1" style="' + linkStyle + '">' +
                     'All Years</span>' + sep +
                     '<span style="color:#7C2A83;">' + drill.year + '</span>';
        } else if (level === 3) {
            var months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
            var mName = months[(drill.month || 1) - 1];
            crumbs = '<span class="bc-link" data-level="1" style="' + linkStyle + '">' +
                     'All Years</span>' + sep +
                     '<span class="bc-link" data-level="2" style="' + linkStyle + '">' +
                     drill.year + '</span>' + sep +
                     '<span style="color:#7C2A83;">' + mName + '</span>';
            dateLabel = mName + " " + drill.day + ", " + drill.year;
        }

        // Use set_props to inject breadcrumb HTML after Dash renders,
        // and set up delegated click handler once
        if (window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props("machines-breadcrumb", {
                dangerously_allow_html: crumbs
            });
        }

        var bcEl = document.getElementById("machines-breadcrumb");
        if (bcEl) {
            bcEl.innerHTML = crumbs;
            if (!bcEl._bcDelegated) {
                bcEl._bcDelegated = true;
                bcEl.addEventListener("click", function(e) {
                    var link = e.target.closest(".bc-link");
                    if (!link) return;
                    e.stopPropagation();
                    var targetLevel = parseInt(link.getAttribute("data-level"), 10);
                    var newDrill;
                    if (targetLevel === 1) {
                        newDrill = {level: 1, year: null, month: null, day: null};
                    } else if (targetLevel === 2) {
                        // Read year from the level-2 link's own text
                        var yearLink = bcEl.querySelector("[data-level='2']");
                        var yearVal = yearLink ? parseInt(yearLink.textContent, 10) : null;
                        newDrill = {level: 2, year: yearVal, month: null, day: null};
                    }
                    if (newDrill && window.dash_clientside && window.dash_clientside.set_props) {
                        window.dash_clientside.set_props("machines-store-drill", {data: newDrill});
                    }
                });
            }
        }

        // Return no_update for breadcrumb children to avoid overwriting innerHTML
        return [l1, l2, l3, window.dash_clientside.no_update, dateLabel];
    },

    // -----------------------------------------------------------------------
    // Level 1: Year overview cards
    // -----------------------------------------------------------------------
    renderYearCards: function(agg) {
        var container = document.getElementById("machines-year-cards-container");
        if (!container) return window.dash_clientside.no_update;

        if (!agg || !agg.yearly || agg.yearly.length === 0) {
            container.innerHTML = '<div style="text-align:center;color:#9CA3AF;padding:40px;">No downtime data</div>';
            return window.dash_clientside.no_update;
        }

        var years = agg.yearly;
        var cardW = 220;
        var cardH = 146;
        var barH = 72;
        var monthLabels = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

        // Find global max monthly hours for consistent bar scaling
        var globalMax = 1;
        for (var i = 0; i < years.length; i++) {
            for (var m = 0; m < 12; m++) {
                if (years[i].monthly[m] > globalMax) globalMax = years[i].monthly[m];
            }
        }

        // Outer wrapper for positioning tooltip; inner div scrolls
        var html = '<div style="position:relative;">' +
            '<div style="display:flex;flex-wrap:nowrap;gap:12px;overflow-x:auto;padding-bottom:2px;">';

        for (var i = 0; i < years.length; i++) {
            var yr = years[i];

            var accentColor = yr.availability >= 97 ? "#4CAF50" :
                              yr.availability >= 95 ? "#FFC107" :
                              yr.availability >= 85 ? "#FF9800" : "#EF4444";

            html += '<div class="machines-year-card-wrap" data-year="' + yr.year + '" data-card-idx="' + i + '" ' +
                    'style="cursor:pointer;flex:0 0 ' + cardW + 'px;width:' + cardW + 'px;min-width:' + cardW + 'px;">';

            var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + cardW + '" height="' + cardH + '" style="display:block;">';

            // Card background
            svg += '<rect x="0" y="0" width="' + cardW + '" height="' + cardH +
                   '" rx="6" fill="white" stroke="#E5E7EB" stroke-width="1" class="machines-year-card"/>';

            // Accent left bar
            svg += '<rect x="0" y="0" width="4" height="' + cardH + '" rx="2" fill="' + accentColor + '"/>';

            // Year label
            svg += '<text x="14" y="24" font-size="20" font-weight="700" fill="#1F2937">' + yr.year + '</text>';

            // Stats
            svg += '<text x="14" y="42" font-size="13" fill="#6B7280">' +
                   yr.hours.toFixed(0) + ' hrs  \u00B7  ' + yr.availability.toFixed(1) + '% avail</text>';

            svg += '<text x="14" y="58" font-size="11" fill="#9CA3AF">' +
                   yr.gapCount + ' events' + (yr.fullDayCount > 0 ? '  \u00B7  ' + yr.fullDayCount + ' full-day' : '') + '</text>';

            // Monthly bar sparkline
            var barTop = 68;
            var barW = (cardW - 28) / 12;
            for (var m = 0; m < 12; m++) {
                var bx = 14 + m * barW;
                var bh = (yr.monthly[m] / globalMax) * barH;
                if (bh < 0.5 && yr.monthly[m] > 0) bh = 0.5;
                var by = barTop + barH - bh;
                svg += '<rect class="yr-bar" x="' + bx + '" y="' + by + '" width="' + Math.max(barW - 1, 1) +
                       '" height="' + bh + '" fill="' + hexToRgba(accentColor, 0.5) + '" rx="1" ' +
                       'data-tip="' + monthLabels[m] + ': ' + yr.monthly[m].toFixed(1) + ' hrs" ' +
                       'style="cursor:pointer;"/>';
            }

            svg += '</svg>';
            html += svg + '</div>';
        }

        // Close scroll container, then add tooltip in outer wrapper
        html += '</div>';
        html += '<div id="yr-tooltip" style="display:none;position:absolute;pointer-events:none;' +
            'background:rgba(30,30,30,0.92);color:#fff;padding:6px 10px;border-radius:6px;' +
            'font-size:11px;line-height:1.4;white-space:pre-line;max-width:220px;z-index:10;' +
            'box-shadow:0 2px 8px rgba(0,0,0,0.25);font-family:Inter,sans-serif;"></div></div>';

        container.innerHTML = html;

        var yrTip = container.querySelector("#yr-tooltip");
        function showYrTip(evt, text) {
            if (!yrTip) return;
            yrTip.textContent = text;
            yrTip.style.display = "block";
            var r = container.getBoundingClientRect();
            var tx = evt.clientX - r.left + 12;
            var ty = evt.clientY - r.top - 8;
            if (tx + 220 > r.width) tx = evt.clientX - r.left - 230;
            if (ty < 0) ty = 4;
            yrTip.style.left = tx + "px";
            yrTip.style.top = ty + "px";
        }
        function hideYrTip() { if (yrTip) yrTip.style.display = "none"; }

        // Card hover and click via wrapper divs
        var cardWraps = container.querySelectorAll(".machines-year-card-wrap");
        cardWraps.forEach(function(wrap) {
            var bgRect = wrap.querySelector(".machines-year-card");

            // Click to drill down
            wrap.addEventListener("click", function() {
                var year = parseInt(wrap.getAttribute("data-year"), 10);
                if (window.dash_clientside && window.dash_clientside.set_props) {
                    window.dash_clientside.set_props("machines-store-year-click", {data: year});
                }
            });

            // Card hover
            wrap.addEventListener("mouseenter", function() {
                if (bgRect) {
                    bgRect.setAttribute("stroke", "#9CA3AF");
                    bgRect.setAttribute("stroke-width", "2");
                    bgRect.style.filter = "drop-shadow(0 4px 8px rgba(0,0,0,0.15))";
                }
            });
            wrap.addEventListener("mouseleave", function() {
                if (bgRect) {
                    bgRect.setAttribute("stroke", "#E5E7EB");
                    bgRect.setAttribute("stroke-width", "1");
                    bgRect.style.filter = "";
                }
            });
        });

        // Bar hover — tooltip
        var bars = container.querySelectorAll(".yr-bar");
        bars.forEach(function(bar) {
            bar.addEventListener("mouseenter", function(e) {
                bar.style.filter = "brightness(1.3)";
                showYrTip(e, bar.getAttribute("data-tip"));
            });
            bar.addEventListener("mousemove", function(e) { showYrTip(e, bar.getAttribute("data-tip")); });
            bar.addEventListener("mouseleave", function() {
                bar.style.filter = "";
                hideYrTip();
            });
        });

        return window.dash_clientside.no_update;
    },

    // -----------------------------------------------------------------------
    // Level 2: Month heatmap — 12 mini calendars in a single horizontal row
    // Each month: columns = M T W T F, rows = weeks (traditional calendar)
    // -----------------------------------------------------------------------
    renderMonthHeatmap: function(agg, drill) {
        var container = document.getElementById("machines-month-heatmap-container");
        if (!container) return window.dash_clientside.no_update;

        if (!agg || !agg.daily || !drill || drill.level !== 2 || !drill.year) {
            container.innerHTML = "";
            return window.dash_clientside.no_update;
        }

        var year = drill.year;
        var daily = agg.daily;
        var monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
        var dayLabels = ["M","T","W","T","F"];

        // Build lookup
        var lookup = {};
        for (var i = 0; i < daily.length; i++) {
            lookup[daily[i].date] = daily[i];
        }

        // Find global max for color scaling
        var maxMin = 1;
        for (var i = 0; i < daily.length; i++) {
            var dd = daily[i];
            if (dd.date.substring(0, 4) === String(year) && dd.minutes > maxMin) {
                maxMin = dd.minutes;
            }
        }

        // Pre-compute month grids: each week is a row [Mon..Fri]
        var maxWeeks = 0;
        var monthGrids = [];
        for (var mo = 0; mo < 12; mo++) {
            var weeks = [];
            var curWeek = new Array(5).fill(null);
            var d = new Date(year, mo, 1);

            while (d.getMonth() === mo) {
                var dow = d.getDay();
                var monDow = dow === 0 ? 6 : dow - 1; // 0=Mon..6=Sun
                if (monDow === 0 && curWeek.some(function(c) { return c !== null; })) {
                    weeks.push(curWeek);
                    curWeek = new Array(5).fill(null);
                }
                if (monDow < 5) {
                    var ds = year + "-" + String(mo + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
                    curWeek[monDow] = {date: ds, day: d.getDate()};
                }
                d.setDate(d.getDate() + 1);
            }
            if (curWeek.some(function(c) { return c !== null; })) weeks.push(curWeek);
            monthGrids.push(weeks);
            if (weeks.length > maxWeeks) maxWeeks = weeks.length;
        }

        // Layout: single row of 12 months
        var containerW = container.clientWidth || 900;
        var monthGap = 6;
        var labelH = 16;     // month name height
        var dayLabelH = 12;  // day-of-week header row height
        var cellGap = 2;

        // Compute cell size: each month has 5 columns (M-F)
        var availPerMonth = (containerW + monthGap) / 12 - monthGap;
        var cell = Math.max(8, Math.floor((availPerMonth + cellGap) / 5 - cellGap));
        var monthW = 5 * (cell + cellGap) - cellGap;
        var monthH = labelH + dayLabelH + maxWeeks * (cell + cellGap) - cellGap;
        var totalW = containerW;
        var totalH = monthH;

        function cellColor(mins) {
            if (mins <= 0) return "#EBEDF0";
            var t = Math.min(mins / maxMin, 1);
            if (t < 0.2) return "#FDBA74";   // light orange
            if (t < 0.45) return "#F97316";   // orange
            if (t < 0.7) return "#EA580C";    // deep orange
            return "#DC2626";                  // red
        }

        var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="100%" ' +
                  'viewBox="0 0 ' + totalW + ' ' + totalH + '" preserveAspectRatio="xMinYMid meet" ' +
                  'style="display:block;cursor:pointer;">';

        for (var mo = 0; mo < 12; mo++) {
            var ox = mo * (monthW + monthGap);
            var oy = 0;

            // Month label (centered above grid)
            svg += '<text x="' + (ox + monthW / 2) + '" y="' + (oy + 11) +
                   '" text-anchor="middle" font-size="11" fill="#374151" font-weight="600">' +
                   monthNames[mo] + '</text>';

            // Day-of-week column headers
            for (var dc = 0; dc < 5; dc++) {
                var hx = ox + dc * (cell + cellGap) + cell / 2;
                svg += '<text x="' + hx + '" y="' + (oy + labelH + 8) +
                       '" text-anchor="middle" font-size="7" fill="#9CA3AF">' + dayLabels[dc] + '</text>';
            }

            // Grid cells: rows = weeks, columns = M T W T F
            var weeks = monthGrids[mo];
            for (var w = 0; w < weeks.length; w++) {
                for (var dc = 0; dc < 5; dc++) {
                    var c = weeks[w][dc];
                    var cx = ox + dc * (cell + cellGap);
                    var cy = oy + labelH + dayLabelH + w * (cell + cellGap);

                    if (!c) continue;

                    var info = lookup[c.date];
                    var mins = info ? info.minutes : 0;
                    var color = cellColor(mins);
                    var tip = monthNames[mo] + " " + c.day;
                    if (info) {
                        tip += "\n" + mins.toFixed(0) + " min downtime\n" +
                               info.gapCount + " gaps, " + info.cancelled + " cancelled\n" +
                               info.machines.join(", ");
                    } else {
                        tip += "\nNo downtime";
                    }

                    svg += '<rect class="hm-cell" x="' + cx + '" y="' + cy + '" width="' + cell + '" height="' + cell +
                           '" rx="3" fill="' + color + '" data-date="' + c.date + '" ' +
                           'data-tip="' + tip.replace(/"/g, '&quot;') + '" ' +
                           'style="cursor:pointer;transition:stroke 0.05s,stroke-width 0.05s;"/>';
                }
            }
        }

        svg += '</svg>';

        // Wrap with relative container for tooltip
        container.innerHTML = '<div style="position:relative;">' + svg +
            '<div id="hm-tooltip" style="display:none;position:absolute;pointer-events:none;' +
            'background:rgba(30,30,30,0.92);color:#fff;padding:6px 10px;border-radius:6px;' +
            'font-size:11px;line-height:1.4;white-space:pre-line;max-width:240px;z-index:10;' +
            'box-shadow:0 2px 8px rgba(0,0,0,0.25);font-family:Inter,sans-serif;"></div></div>';

        var hmTip = container.querySelector("#hm-tooltip");
        function showHmTip(evt, text) {
            if (!hmTip) return;
            hmTip.textContent = text;
            hmTip.style.display = "block";
            var r = container.getBoundingClientRect();
            var tx = evt.clientX - r.left + 12;
            var ty = evt.clientY - r.top - 8;
            if (tx + 240 > r.width) tx = evt.clientX - r.left - 250;
            if (ty < 0) ty = 4;
            hmTip.style.left = tx + "px";
            hmTip.style.top = ty + "px";
        }
        function hideHmTip() { if (hmTip) hmTip.style.display = "none"; }

        // Cell hover — outline highlight + tooltip
        var cells = container.querySelectorAll(".hm-cell");
        cells.forEach(function(el) {
            el.addEventListener("mouseenter", function(e) {
                el.setAttribute("stroke", "#374151");
                el.setAttribute("stroke-width", "1.5");
                showHmTip(e, el.getAttribute("data-tip"));
            });
            el.addEventListener("mousemove", function(e) { showHmTip(e, el.getAttribute("data-tip")); });
            el.addEventListener("mouseleave", function() {
                el.removeAttribute("stroke");
                el.removeAttribute("stroke-width");
                hideHmTip();
            });
        });

        // Wire click handlers for day cells
        cells.forEach(function(el) {
            el.addEventListener("click", function() {
                var date = el.getAttribute("data-date");
                if (window.dash_clientside && window.dash_clientside.set_props) {
                    window.dash_clientside.set_props("machines-store-day-click", {data: date});
                }
            });
        });

        return window.dash_clientside.no_update;
    },

    // -----------------------------------------------------------------------
    // Level 3: Daily timeline strip (SVG)
    // -----------------------------------------------------------------------
    showTimelineLoading: function(drill, machines, confidence, gapThreshold) {
        if (!drill || drill.level !== 3) return window.dash_clientside.no_update;
        var container = document.getElementById("machines-timeline-svg-container");
        if (!container) return window.dash_clientside.no_update;
        // Overlay a spinner on top of existing content (or empty state)
        var existing = container.innerHTML;
        if (!container.querySelector(".tl-loading-overlay")) {
            var overlay = document.createElement("div");
            overlay.className = "tl-loading-overlay";
            overlay.style.cssText = "position:absolute;inset:0;display:flex;align-items:center;justify-content:center;" +
                "background:rgba(250,250,250,0.7);z-index:20;border-radius:8px;";
            overlay.innerHTML = '<div style="width:32px;height:32px;border:3px solid #E5E7EB;border-top-color:#7C2A83;' +
                'border-radius:50%;animation:tl-spin 0.8s linear infinite;"></div>';
            container.style.position = "relative";
            container.appendChild(overlay);
        }
        // Inject keyframes if not already present
        if (!document.getElementById("tl-spin-style")) {
            var style = document.createElement("style");
            style.id = "tl-spin-style";
            style.textContent = "@keyframes tl-spin { to { transform: rotate(360deg); } }";
            document.head.appendChild(style);
        }
        return "machines-timeline-container";
    },

    renderTimelineStrip: function(data) {
        var container = document.getElementById("machines-timeline-svg-container");
        if (!container) return window.dash_clientside.no_update;

        if (!data || !data.machines || data.machines.length === 0) {
            container.innerHTML = '<div style="text-align:center;color:#9CA3AF;padding:40px;">No timeline data for this day</div>';
            return window.dash_clientside.no_update;
        }

        var machines = data.machines;
        var gaps = data.gaps || [];
        var fields = data.fields || [];

        // SVG dimensions — fill container width
        var margin = {left: 120, right: 20, top: 30, bottom: 40};
        var rowHeight = 92;
        var width = Math.max(600, container.clientWidth || 900);
        var height = margin.top + margin.bottom + machines.length * rowHeight;

        // Auto-scale time axis from data, rounded to nearest hour
        var allMinutes = [];
        function parseTimeMin(t) {
            if (!t || t.length < 5) return -1;
            var p = t.split(":");
            var hh = parseInt(p[0], 10);
            var mm = parseInt(p[1], 10);
            if (isNaN(hh) || isNaN(mm)) return -1;
            return hh * 60 + mm;
        }
        for (var ti = 0; ti < fields.length; ti++) {
            var tm1 = parseTimeMin(fields[ti].start);
            var tm2 = parseTimeMin(fields[ti].end);
            if (tm1 > 0) allMinutes.push(tm1);
            if (tm2 > 0) allMinutes.push(tm2);
        }
        for (var tg = 0; tg < gaps.length; tg++) {
            var tg1 = parseTimeMin(gaps[tg].start);
            var tg2 = parseTimeMin(gaps[tg].end);
            if (tg1 > 0) allMinutes.push(tg1);
            if (tg2 > 0) allMinutes.push(tg2);
        }
        var startMin, endMin;
        if (allMinutes.length > 0) {
            var dataMin = Math.min.apply(null, allMinutes);
            var dataMax = Math.max.apply(null, allMinutes);
            // Round down/up to nearest hour
            startMin = Math.floor(dataMin / 60) * 60;
            endMin = Math.ceil(dataMax / 60) * 60;
            // Ensure at least 1 hour padding if range is very tight
            if (endMin - startMin < 120) {
                startMin = Math.max(0, startMin - 60);
                endMin = Math.min(24 * 60, endMin + 60);
            }
        } else {
            startMin = 6 * 60 + 30;
            endMin = 18 * 60 + 30;
        }
        var timeRange = endMin - startMin;
        var chartW = width - margin.left - margin.right;

        function timeToX(timeStr) {
            if (!timeStr) return null;
            var parts = timeStr.split(":");
            var h = parseInt(parts[0], 10);
            var m = parseInt(parts[1], 10);
            var totalMin = h * 60 + m;
            return margin.left + ((totalMin - startMin) / timeRange) * chartW;
        }

        function machineY(machine) {
            var idx = machines.indexOf(machine);
            return margin.top + idx * rowHeight;
        }

        var confColors = {High: "rgba(211,47,47,0.35)", Medium: "rgba(255,152,0,0.35)", Low: "rgba(255,193,7,0.25)"};
        var confColorsHover = {High: "rgba(211,47,47,0.55)", Medium: "rgba(255,152,0,0.55)", Low: "rgba(255,193,7,0.45)"};
        var statusColors = {NORMAL: "#4CAF50", MACHINE: "#D32F2F", OPERATOR: "#FF9800", UNKNOWN: "#9E9E9E"};
        var statusLabels = {NORMAL: "Normal", MACHINE: "Machine Termination", OPERATOR: "Operator Termination", UNKNOWN: "Unknown"};

        var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="' + height + '" ' +
                  'viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="none" ' +
                  'style="font-family: Inter, sans-serif; background: #fafafa; border-radius: 8px; display: block;">';

        // Hour gridlines and labels — dynamic range
        var firstHour = Math.ceil(startMin / 60);
        var lastHour = Math.floor(endMin / 60);
        for (var h = firstHour; h <= lastHour; h++) {
            var x = timeToX(String(h).padStart(2, "0") + ":00:00");
            if (x !== null) {
                svg += '<line x1="' + x + '" y1="' + margin.top + '" x2="' + x + '" y2="' + (height - margin.bottom) + '" ' +
                       'stroke="#E5E7EB" stroke-width="1" stroke-dasharray="2,2"/>';
                var label = h > 12 ? (h - 12) + " PM" : (h === 12 ? "12 PM" : h + " AM");
                svg += '<text x="' + x + '" y="' + (margin.top - 8) + '" text-anchor="middle" ' +
                       'font-size="10" fill="#9CA3AF">' + label + '</text>';
            }
        }

        // Machine row labels and backgrounds
        for (var i = 0; i < machines.length; i++) {
            var y = machineY(machines[i]);
            if (i % 2 === 0) {
                svg += '<rect x="' + margin.left + '" y="' + y + '" width="' + chartW + '" height="' + rowHeight + '" ' +
                       'fill="rgba(0,0,0,0.02)"/>';
            }
            svg += '<text x="' + (margin.left - 8) + '" y="' + (y + rowHeight / 2 + 4) + '" ' +
                   'text-anchor="end" font-size="11" fill="#374151" font-weight="500">' + machines[i] + '</text>';
        }

        // Gap bands — with data attributes for hover
        for (var g = 0; g < gaps.length; g++) {
            var gap = gaps[g];
            var gy = machineY(gap.machine);

            if (gap.fullDay) {
                // Full-day outage — render as full-width red band
                svg += '<rect class="tl-gap" x="' + margin.left + '" y="' + (gy + 2) + '" width="' + chartW + '" height="' + (rowHeight - 4) + '" ' +
                       'fill="rgba(211,47,47,0.25)" rx="3" stroke="#D32F2F" stroke-width="1" stroke-opacity="0.5" ' +
                       'data-tip="Full day down" data-conf="FullDay" style="cursor:pointer;transition:fill 0.15s;"/>';
                svg += '<text x="' + (margin.left + chartW / 2) + '" y="' + (gy + rowHeight / 2 + 5) + '" ' +
                       'text-anchor="middle" font-size="14" fill="#D32F2F" font-weight="600" pointer-events="none">' +
                       'Full Day Down</text>';
                continue;
            }

            var gx1 = timeToX(gap.start);
            var gx2 = timeToX(gap.end);
            if (gx1 !== null && gx2 !== null && gx2 > gx1) {
                var gColor = confColors[gap.confidence] || confColors.Low;
                var tipLines = [gap.minutes + ' min ' + gap.confidence.toLowerCase() + ' confidence gap'];
                if (gap.cancelled > 0) {
                    var cancelText = gap.cancelled + ' cancelled';
                    if (gap.outcomes && Object.keys(gap.outcomes).length > 0) {
                        var parts = [];
                        for (var oc in gap.outcomes) {
                            parts.push(gap.outcomes[oc] + ' ' + oc.toLowerCase());
                        }
                        cancelText += ' (' + parts.join(', ') + ')';
                    }
                    tipLines.push(cancelText);
                }
                if (gap.notes && gap.notes.length > 0) tipLines.push('Notes: ' + gap.notes.join(', '));
                if (gap.errors > 0) tipLines.push(gap.errors + ' errors nearby');
                if (gap.prevPatient) tipLines.push('Prev: ' + gap.prevPatient);
                if (gap.nextPatient) tipLines.push('Next: ' + gap.nextPatient);
                if (gap.reroute) tipLines.push('Rerouted to: ' + gap.reroute);
                svg += '<rect class="tl-gap" x="' + gx1 + '" y="' + (gy + 2) + '" width="' + (gx2 - gx1) + '" height="' + (rowHeight - 4) + '" ' +
                       'fill="' + gColor + '" rx="3" stroke="' + (gap.confidence === "High" ? "#D32F2F" : gap.confidence === "Medium" ? "#FF9800" : "#FFC107") + '" stroke-width="1" stroke-opacity="0.5" ' +
                       'data-tip="' + tipLines.join('&#10;').replace(/"/g, '&quot;') + '" ' +
                       'data-conf="' + gap.confidence + '" style="cursor:pointer;transition:fill 0.15s;"/>';

                // Duration label inside gap if wide enough
                if (gx2 - gx1 > 30) {
                    svg += '<text x="' + ((gx1 + gx2) / 2) + '" y="' + (gy + rowHeight / 2 + 5) + '" ' +
                           'text-anchor="middle" font-size="14" fill="white" font-weight="600" pointer-events="none">' +
                           gap.minutes + 'm</text>';
                }
            }
        }

        // Treatment field ticks — with data attributes for hover
        for (var f = 0; f < fields.length; f++) {
            var field = fields[f];
            var fx = timeToX(field.start);
            var fy = machineY(field.machine);
            if (fx !== null) {
                var fColor = statusColors[field.status] || statusColors.NORMAL;
                var fWidth = field.status === "MACHINE" ? 5 : (field.type === "Image" ? 2 : 3);
                var fOpacity = field.type === "Image" ? 0.5 : 1.0;
                var fTip = (field.type === "Image" ? "[Image] " : "") +
                           field.patient + (field.fieldId ? ' | ' + field.fieldId : '') +
                           (field.status ? ' | ' + (statusLabels[field.status] || field.status) : '');

                // Error arrow — red inverted triangle above MACHINE termination ticks
                if (field.status === "MACHINE") {
                    var arrowY = fy - 4;
                    svg += '<polygon class="tl-error-arrow" points="' +
                           (fx - 6) + ',' + arrowY + ' ' +
                           (fx + 6) + ',' + arrowY + ' ' +
                           fx + ',' + (arrowY + 9) + '" ' +
                           'fill="#D32F2F" opacity="0.9" pointer-events="none"/>';
                }

                // Invisible wider hit-area for hover (8px), then visible thin tick on top
                var hitW = 8;
                svg += '<rect class="tl-field" x="' + (fx - hitW / 2) + '" y="' + (fy + 4) + '" width="' + hitW + '" height="' + (rowHeight - 8) + '" ' +
                       'fill="transparent" ' +
                       'data-tip="' + fTip.replace(/"/g, '&quot;') + '" ' +
                       'data-vis-id="field-vis-' + f + '" ' +
                       'style="cursor:pointer;"/>';
                svg += '<rect id="field-vis-' + f + '" x="' + (fx - fWidth / 2) + '" y="' + (fy + 4) + '" width="' + fWidth + '" height="' + (rowHeight - 8) + '" ' +
                       'fill="' + fColor + '" opacity="' + fOpacity + '" pointer-events="none" ' +
                       'data-base-opacity="' + fOpacity + '" data-base-width="' + fWidth + '" data-cx="' + fx + '"/>';
            }
        }

        // Legend — measure text with a hidden SVG element for accurate spacing
        var legY = height - 15;
        var legFS = "11";

        // Render all legend items, measure each text, then space evenly
        var allLeg = [
            {color: "#4CAF50", label: "Normal", stroke: false},
            {color: "#D32F2F", label: "Machine Termination", stroke: false},
            {color: "#FF9800", label: "Operator Termination", stroke: false},
            {type: "gap", size: 30},
            {color: "rgba(211,47,47,0.35)", label: "High Confidence", stroke: true},
            {color: "rgba(255,152,0,0.35)", label: "Medium Confidence", stroke: true},
            {color: "rgba(255,193,7,0.25)", label: "Low Confidence", stroke: true},
        ];
        // Use canvas to measure text widths accurately
        var legCanvas = document.createElement("canvas").getContext("2d");
        legCanvas.font = legFS + "px Inter, system-ui, sans-serif";
        var legX = margin.left;
        var legPad = 24; // gap after text before next swatch
        for (var li = 0; li < allLeg.length; li++) {
            var item = allLeg[li];
            if (item.type === "gap") { legX += item.size; continue; }
            var sw = item.stroke ? ' stroke="#ccc" stroke-width="0.5"' : '';
            svg += '<rect x="' + legX + '" y="' + (legY - 9) + '" width="12" height="12" fill="' + item.color + '" rx="2"' + sw + '/>';
            svg += '<text x="' + (legX + 17) + '" y="' + (legY + 1) + '" font-size="' + legFS + '" fill="#6B7280">' + item.label + '</text>';
            var tw = legCanvas.measureText(item.label).width;
            legX += 17 + tw + legPad;
        }

        svg += '</svg>';

        // Wrap with a relative container for tooltip positioning
        container.innerHTML = '<div style="position:relative;">' + svg +
            '<div id="tl-tooltip" style="display:none;position:absolute;pointer-events:none;' +
            'background:rgba(30,30,30,0.92);color:#fff;padding:6px 10px;border-radius:6px;' +
            'font-size:11px;line-height:1.4;white-space:pre-line;max-width:260px;z-index:10;' +
            'box-shadow:0 2px 8px rgba(0,0,0,0.25);font-family:Inter,sans-serif;"></div></div>';

        // Attach hover listeners for gaps and fields
        var tooltip = container.querySelector("#tl-tooltip");
        var confHover = {High: "rgba(211,47,47,0.55)", Medium: "rgba(255,152,0,0.55)", Low: "rgba(255,193,7,0.45)", FullDay: "rgba(211,47,47,0.45)"};
        var confBase = {High: "rgba(211,47,47,0.35)", Medium: "rgba(255,152,0,0.35)", Low: "rgba(255,193,7,0.25)", FullDay: "rgba(211,47,47,0.25)"};

        function showTip(evt, text) {
            if (!tooltip) return;
            tooltip.textContent = text;
            tooltip.style.display = "block";
            var rect = container.getBoundingClientRect();
            var x = evt.clientX - rect.left + 12;
            var y = evt.clientY - rect.top - 8;
            // Keep tooltip within bounds
            if (x + 260 > rect.width) x = evt.clientX - rect.left - 270;
            if (y < 0) y = 4;
            tooltip.style.left = x + "px";
            tooltip.style.top = y + "px";
        }
        function hideTip() {
            if (tooltip) tooltip.style.display = "none";
        }

        // Gap hover
        var gapEls = container.querySelectorAll(".tl-gap");
        for (var gi2 = 0; gi2 < gapEls.length; gi2++) {
            (function(el) {
                el.addEventListener("mouseenter", function(e) {
                    var conf = el.getAttribute("data-conf");
                    el.setAttribute("fill", confHover[conf] || confHover.Low);
                    el.setAttribute("stroke-width", "2");
                    showTip(e, el.getAttribute("data-tip"));
                });
                el.addEventListener("mousemove", function(e) { showTip(e, el.getAttribute("data-tip")); });
                el.addEventListener("mouseleave", function() {
                    var conf = el.getAttribute("data-conf");
                    el.setAttribute("fill", confBase[conf] || confBase.Low);
                    el.setAttribute("stroke-width", "1");
                    hideTip();
                });
            })(gapEls[gi2]);
        }

        // Field hover — hit-area triggers highlight on the visible tick
        var fieldEls = container.querySelectorAll(".tl-field");
        for (var fi2 = 0; fi2 < fieldEls.length; fi2++) {
            (function(hitEl) {
                var visId = hitEl.getAttribute("data-vis-id");
                var visEl = container.querySelector("#" + visId);
                if (!visEl) return;
                hitEl.addEventListener("mouseenter", function(e) {
                    visEl.setAttribute("opacity", "1");
                    var cx = parseFloat(visEl.getAttribute("data-cx"));
                    visEl.setAttribute("x", String(cx - 2));
                    visEl.setAttribute("width", "4");
                    showTip(e, hitEl.getAttribute("data-tip"));
                });
                hitEl.addEventListener("mousemove", function(e) { showTip(e, hitEl.getAttribute("data-tip")); });
                hitEl.addEventListener("mouseleave", function() {
                    visEl.setAttribute("opacity", visEl.getAttribute("data-base-opacity"));
                    var cx = parseFloat(visEl.getAttribute("data-cx"));
                    var bw = parseFloat(visEl.getAttribute("data-base-width"));
                    visEl.setAttribute("x", String(cx - bw / 2));
                    visEl.setAttribute("width", String(bw));
                    hideTip();
                });
            })(fieldEls[fi2]);
        }

        return window.dash_clientside.no_update;
    },

    // -----------------------------------------------------------------------
    // Downtime trend chart — daily data with D/W/M aggregation
    // -----------------------------------------------------------------------
    renderTrend: function(data, smoothPct, chartType, agg, currentFig) {
        if (!data || !data.dates || data.dates.length === 0) {
            return {
                data: [],
                layout: {
                    xaxis: {visible: false}, yaxis: {visible: false},
                    annotations: [{text: "No trend data", showarrow: false,
                        font: {size: 14, color: "#9CA3AF"}, xref: "paper", yref: "paper", x: 0.5, y: 0.5}],
                    autosize: true, margin: {l: 20, r: 20, t: 20, b: 20},
                    plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)"
                }
            };
        }

        var rawDates = data.dates;
        var series = data.series;
        agg = agg || "W";

        // Aggregate dates and values by period
        var aggResult = _aggregateDates(rawDates, series.map(function(s) { return s.values; }), agg);
        var dates = aggResult.dates;
        var aggValues = aggResult.values;

        var windowSize = Math.max(1, Math.floor((smoothPct || 0) / 3) + 1);
        var traces = [];

        // Preserve legend visibility
        var visMap = {};
        if (currentFig && currentFig.data) {
            for (var v = 0; v < currentFig.data.length; v++) {
                if (currentFig.data[v].name) {
                    visMap[currentFig.data[v].name] = currentFig.data[v].visible;
                }
            }
        }

        var isBar = !chartType || chartType === "bar";
        var isArea = chartType === "area";
        var dateFmt = agg === "M" ? "%b %Y" : "%b %d, %Y";

        for (var s = 0; s < series.length; s++) {
            var ser = series[s];
            var vals = windowSize > 1 && typeof rollingAvg === "function" ?
                       rollingAvg(aggValues[s], windowSize) : aggValues[s];

            var trace = {
                x: dates, y: vals,
                name: ser.name,
                hovertemplate: ser.name + "<br>%{x|" + dateFmt + "}: %{y:.1f} hrs<extra></extra>",
            };

            if (isBar) {
                trace.type = "bar";
                trace.marker = {color: ser.color};
            } else if (isArea) {
                trace.type = "scatter";
                trace.mode = "lines";
                trace.fill = "tonexty";
                trace.line = {color: ser.color, width: 1.5};
                trace.fillcolor = hexToRgba(ser.color, 0.3);
                trace.stackgroup = "one";
            } else {
                trace.type = "scatter";
                trace.mode = "lines+markers";
                trace.line = {color: ser.color, width: 2};
                trace.marker = {size: 4};
            }

            if (visMap[ser.name] !== undefined) trace.visible = visMap[ser.name];
            traces.push(trace);
        }

        return {
            data: traces,
            layout: {
                autosize: true,
                margin: {l: 50, r: 20, t: 10, b: 40},
                barmode: "stack",
                xaxis: {gridcolor: "#F3F4F6", zeroline: false},
                yaxis: {title: "Downtime Hours", gridcolor: "#F3F4F6", zeroline: false, rangemode: "tozero"},
                plot_bgcolor: "rgba(0,0,0,0)",
                paper_bgcolor: "rgba(0,0,0,0)",
                legend: {orientation: "h", y: 1.12, x: 0.5, xanchor: "center"},
                font: {family: "Inter, system-ui, sans-serif", size: 12, color: "#374151"},
                hoverlabel: {font: {family: "Inter, system-ui, sans-serif"}},
                hovermode: "x unified",
            }
        };
    },

    // -----------------------------------------------------------------------
    // Patient impact chart — daily data with D/W/M aggregation
    // -----------------------------------------------------------------------
    renderPatientImpact: function(data, smoothPct, chartType, agg, mode, _currentFig) {
        if (!data || !data.dates || data.dates.length === 0) {
            return {
                data: [],
                layout: {
                    xaxis: {visible: false}, yaxis: {visible: false},
                    annotations: [{text: "No patient impact data", showarrow: false,
                        font: {size: 14, color: "#9CA3AF"}, xref: "paper", yref: "paper", x: 0.5, y: 0.5}],
                    autosize: true, margin: {l: 20, r: 20, t: 20, b: 20},
                    plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)"
                }
            };
        }

        agg = agg || "W";
        mode = mode || "appt";
        var isCourse = mode === "course";

        var sourceSets = isCourse
            ? [data.courses || []]
            : [data.cancelled, data.rerouted];
        var aggResult = _aggregateDates(data.dates, sourceSets, agg);
        var dates = aggResult.dates;

        var windowSize = Math.max(1, Math.floor((smoothPct || 0) / 3) + 1);
        var isBar = !chartType || chartType === "bar";
        var isArea = chartType === "area";
        var traces = [];

        if (isCourse) {
            // Single series: courses interrupted
            var courses = (windowSize > 1 && typeof rollingAvg === "function") ?
                          rollingAvg(aggResult.values[0], windowSize) : aggResult.values[0];
            var trace = {
                x: dates, y: courses, name: "Courses Interrupted",
                hovertemplate: "Courses: %{y:.0f}<extra></extra>",
            };
            if (isBar) {
                trace.type = "bar";
                trace.marker = {color: "#7C2A83"};
            } else if (isArea) {
                trace.type = "scatter"; trace.mode = "lines";
                trace.fill = "tozeroy"; trace.line = {color: "#7C2A83", width: 1.5};
                trace.fillcolor = hexToRgba("#7C2A83", 0.15);
            } else {
                trace.type = "scatter"; trace.mode = "lines+markers";
                trace.line = {color: "#7C2A83", width: 2}; trace.marker = {size: 4};
            }
            traces.push(trace);
        } else {
            // Two series: cancelled + rerouted
            var cancelled = (windowSize > 1 && typeof rollingAvg === "function") ?
                            rollingAvg(aggResult.values[0], windowSize) : aggResult.values[0];
            var rerouted = (windowSize > 1 && typeof rollingAvg === "function") ?
                           rollingAvg(aggResult.values[1], windowSize) : aggResult.values[1];

            if (isBar) {
                traces.push({x: dates, y: cancelled, name: "Cancelled", type: "bar", marker: {color: "#D32F2F"},
                    hovertemplate: "Cancelled: %{y:.0f}<extra></extra>"});
                traces.push({x: dates, y: rerouted, name: "Rerouted", type: "bar", marker: {color: "#FF9800"},
                    hovertemplate: "Rerouted: %{y:.0f}<extra></extra>"});
            } else if (isArea) {
                traces.push({x: dates, y: cancelled, name: "Cancelled", type: "scatter", mode: "lines",
                    fill: "tonexty", line: {color: "#D32F2F", width: 1.5}, fillcolor: hexToRgba("#D32F2F", 0.3),
                    stackgroup: "one", hovertemplate: "Cancelled: %{y:.0f}<extra></extra>"});
                traces.push({x: dates, y: rerouted, name: "Rerouted", type: "scatter", mode: "lines",
                    fill: "tonexty", line: {color: "#FF9800", width: 1.5}, fillcolor: hexToRgba("#FF9800", 0.3),
                    stackgroup: "one", hovertemplate: "Rerouted: %{y:.0f}<extra></extra>"});
            } else {
                traces.push({x: dates, y: cancelled, name: "Cancelled", type: "scatter", mode: "lines+markers",
                    line: {color: "#D32F2F", width: 2}, marker: {size: 4}, hovertemplate: "Cancelled: %{y:.0f}<extra></extra>"});
                traces.push({x: dates, y: rerouted, name: "Rerouted", type: "scatter", mode: "lines+markers",
                    line: {color: "#FF9800", width: 2}, marker: {size: 4}, hovertemplate: "Rerouted: %{y:.0f}<extra></extra>"});
            }
        }

        var yTitle = isCourse ? "Courses" : "Appointments";

        return {
            data: traces,
            layout: {
                autosize: true,
                margin: {l: 50, r: 20, t: 10, b: 40},
                barmode: "stack",
                xaxis: {gridcolor: "#F3F4F6", zeroline: false},
                yaxis: {title: yTitle, gridcolor: "#F3F4F6", zeroline: false, rangemode: "tozero"},
                plot_bgcolor: "rgba(0,0,0,0)",
                paper_bgcolor: "rgba(0,0,0,0)",
                legend: {orientation: "h", y: 1.12, x: 0.5, xanchor: "center"},
                font: {family: "Inter, system-ui, sans-serif", size: 12, color: "#374151"},
                hoverlabel: {font: {family: "Inter, system-ui, sans-serif"}},
                hovermode: "x unified",
            }
        };
    },

    // -----------------------------------------------------------------------
    // KPI sparklines
    // -----------------------------------------------------------------------
    // -----------------------------------------------------------------------
    // Continuous Strip — treatment activity across many days
    // Each vertical slice = one workday, Y = time of day (7AM→6PM)
    // Blue = treatment active, Red/Orange = downtime gaps, Amber = lunch
    // -----------------------------------------------------------------------
    renderStrip: function(data) {
        var container = document.getElementById("machines-strip-svg-container");
        if (!container) return window.dash_clientside.no_update;

        if (!data || !data.machines || data.machines.length === 0) {
            container.innerHTML = '<div style="text-align:center;color:#9CA3AF;padding:40px;">No strip data available</div>';
            return window.dash_clientside.no_update;
        }

        var machines = data.machines;
        var machineData = data.data;
        // data.colors no longer used — consistent colors for all machines

        // Build a CONTINUOUS index per machine (no calendar gaps).
        // Each machine gets its own packed day array — days are
        // already sorted and weekday-only from the server.
        // For the shared x-axis we use the union of dates packed
        // tightly: index 0, 1, 2, ... with no weekend holes.
        var allDatesSet = {};
        for (var mi = 0; mi < machines.length; mi++) {
            var days = machineData[machines[mi]] || [];
            for (var di = 0; di < days.length; di++) {
                allDatesSet[days[di][0]] = true;
            }
        }
        var sortedDates = Object.keys(allDatesSet).sort();
        var numDays = sortedDates.length;
        if (numDays === 0) {
            container.innerHTML = '<div style="text-align:center;color:#9CA3AF;padding:40px;">No data in range</div>';
            return window.dash_clientside.no_update;
        }

        // Continuous index — each date maps to its packed position
        var dateIdx = {};
        for (var i = 0; i < sortedDates.length; i++) {
            dateIdx[sortedDates[i]] = i;
        }

        // Dimensions
        var margin = {left: 120, right: 12, top: 8, bottom: 46};
        var rowHeight = 120;
        var rowGap = 4;
        var containerW = container.clientWidth || 900;
        var width = Math.max(600, containerW);
        var height = margin.top + margin.bottom + machines.length * (rowHeight + rowGap) - rowGap;
        var chartW = width - margin.left - margin.right;
        var dayWidth = chartW / numDays;

        var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="' + height + '" ' +
                  'viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="xMidYMid meet" ' +
                  'style="display:block;">';

        // --- Per-machine rows ---
        for (var mi = 0; mi < machines.length; mi++) {
            var machine = machines[mi];
            var rTop = margin.top + mi * (rowHeight + rowGap);
            var mDays = machineData[machine] || [];

            // Per-machine dynamic time range
            var mTimeMin = Infinity, mTimeMax = -Infinity;
            for (var di2 = 0; di2 < mDays.length; di2++) {
                var dd = mDays[di2];
                if (dd[1] != null && dd[1] < mTimeMin) mTimeMin = dd[1];
                if (dd[2] != null && dd[2] > mTimeMax) mTimeMax = dd[2];
                var dGaps2 = dd[3] || [];
                for (var gi2 = 0; gi2 < dGaps2.length; gi2++) {
                    if (dGaps2[gi2][0] != null && dGaps2[gi2][0] < mTimeMin) mTimeMin = dGaps2[gi2][0];
                    if (dGaps2[gi2][1] != null && dGaps2[gi2][1] > mTimeMax) mTimeMax = dGaps2[gi2][1];
                }
            }
            if (mTimeMin === Infinity) { mTimeMin = 420; mTimeMax = 1080; }
            var tMin = Math.floor(mTimeMin / 60) * 60 - 30;
            var tMax = Math.ceil(mTimeMax / 60) * 60 + 30;
            if (tMax - tMin < 120) { tMin -= 60; tMax += 60; }
            tMin = Math.max(0, tMin);
            tMax = Math.min(1440, tMax);
            var tRange = tMax - tMin;
            function tY(minutes, rowTop) {
                return rowTop + ((minutes - tMin) / tRange) * rowHeight;
            }

            // Light background
            svg += '<rect x="' + margin.left + '" y="' + rTop + '" width="' + chartW +
                   '" height="' + rowHeight + '" fill="#F3F4F6" rx="3"/>';

            // Machine label — positioned left of time labels
            svg += '<text x="' + (margin.left - 24) + '" y="' + (rTop + rowHeight / 2 + 4) +
                   '" text-anchor="end" font-size="11" fill="#374151" font-weight="600">' +
                   machine + '</text>';

            // Time labels (left axis — every 2 hours, dynamic per machine)
            var firstTickHour = Math.ceil(tMin / 60);
            var lastTickHour = Math.floor(tMax / 60);
            // Start on an even hour for clean 2-hour spacing
            if (firstTickHour % 2 !== 0) firstTickHour++;
            for (var h = firstTickHour; h <= lastTickHour; h += 2) {
                var tickMin = h * 60;
                if (tickMin <= tMin || tickMin >= tMax) continue;
                var tickLabel = h === 0 ? "12a" : h < 12 ? h + "a" : h === 12 ? "12p" : (h - 12) + "p";
                var tickY = tY(tickMin, rTop);
                svg += '<text x="' + (margin.left - 3) + '" y="' + (tickY + 4) +
                       '" text-anchor="end" font-size="10" fill="#9CA3AF">' + tickLabel + '</text>';
                svg += '<line x1="' + margin.left + '" y1="' + tickY +
                       '" x2="' + (margin.left + chartW) + '" y2="' + tickY +
                       '" stroke="#E5E7EB" stroke-width="0.5"/>';
            }

            // Helpers: earliest/latest activity on a day (treatment + gaps)
            function dayEarliest(d) {
                var best = d[1]; // firstTreatment
                var dGaps = d[3] || [];
                for (var gg = 0; gg < dGaps.length; gg++) {
                    if (dGaps[gg][0] != null && (best === null || dGaps[gg][0] < best)) best = dGaps[gg][0];
                }
                return best;
            }
            function dayLatest(d) {
                var best = d[2]; // lastTreatment
                var dGaps = d[3] || [];
                for (var gg = 0; gg < dGaps.length; gg++) {
                    if (dGaps[gg][1] != null && (best === null || dGaps[gg][1] > best)) best = dGaps[gg][1];
                }
                return best;
            }

            // Pre-scan: find interpolated ft/lt for full-day outage days
            var interpFt = {}, interpLt = {};
            for (var di = 0; di < mDays.length; di++) {
                if (!mDays[di][4]) continue;  // only full-day outages
                var prevFt = null, prevLt = null;
                for (var b = di - 1; b >= 0; b--) {
                    if (!mDays[b][4]) {
                        var pe = dayEarliest(mDays[b]), pl = dayLatest(mDays[b]);
                        if (pe !== null) { prevFt = pe; prevLt = pl; break; }
                    }
                }
                var nextFt = null, nextLt = null;
                for (var f = di + 1; f < mDays.length; f++) {
                    if (!mDays[f][4]) {
                        var ne = dayEarliest(mDays[f]), nl = dayLatest(mDays[f]);
                        if (ne !== null) { nextFt = ne; nextLt = nl; break; }
                    }
                }
                if (prevFt !== null && nextFt !== null) {
                    interpFt[di] = Math.round((prevFt + nextFt) / 2);
                    interpLt[di] = Math.round((prevLt + nextLt) / 2);
                } else if (prevFt !== null) {
                    interpFt[di] = prevFt; interpLt[di] = prevLt;
                } else if (nextFt !== null) {
                    interpFt[di] = nextFt; interpLt[di] = nextLt;
                } else {
                    interpFt[di] = 480; interpLt[di] = 1020;
                }
            }

            // Draw each day column at its packed index position
            for (var di = 0; di < mDays.length; di++) {
                var day = mDays[di];
                var dateStr = day[0];
                var idx = dateIdx[dateStr];
                if (idx === undefined) continue;
                var x = margin.left + idx * dayWidth;
                var ft = day[1];  // firstTreatment (minutes)
                var lt = day[2];  // lastTreatment
                var gaps = day[3];
                var isFullDay = day[4];  // full-day outage flag
                var dw = Math.max(dayWidth, 0.5);

                if (isFullDay) {
                    var ift = interpFt[di] || 480;
                    var ilt = interpLt[di] || 1020;
                    var fy1 = tY(ift, rTop);
                    var fy2 = tY(ilt, rTop);
                    svg += '<rect class="strip-band" x="' + x + '" y="' + fy1 + '" width="' + dw +
                           '" height="' + (fy2 - fy1) + '" fill="rgba(220,38,38,0.7)" ' +
                           'data-tip="' + dateStr + ' | ' + machine + '\nFULL DAY DOWN" ' +
                           'data-date="' + dateStr + '" style="cursor:pointer;"/>';
                    continue;
                }

                // Treatment band — consistent color for all machines
                if (ft !== null && lt !== null && lt > ft) {
                    var y1 = tY(ft, rTop);
                    var y2 = tY(lt, rTop);
                    var ftH = Math.floor(ft / 60), ftM = ft % 60;
                    var ltH = Math.floor(lt / 60), ltM = lt % 60;
                    var bandTip = dateStr + ' | ' + machine +
                        '\nFirst: ' + ftH + ':' + String(ftM).padStart(2, '0') +
                        '\nLast: ' + ltH + ':' + String(ltM).padStart(2, '0');
                    svg += '<rect class="strip-band" x="' + x + '" y="' + y1 + '" width="' + dw +
                           '" height="' + (y2 - y1) + '" fill="rgba(76,175,80,0.45)" ' +
                           'data-tip="' + bandTip.replace(/"/g, '&quot;') + '" ' +
                           'data-date="' + dateStr + '" style="cursor:pointer;"/>';
                }

                // Gap overlays
                for (var gi = 0; gi < gaps.length; gi++) {
                    var gs = gaps[gi][0], ge = gaps[gi][1], gc = gaps[gi][2];
                    var isEod = gaps[gi][3];
                    var isBod = gaps[gi][4];

                    // For EndOfDay gaps, interpolate end from neighbors' latest activity
                    if (isEod) {
                        var cnt = 0, sum = 0;
                        for (var b = di - 1; b >= Math.max(0, di - 5); b--) {
                            var nbrLt = dayLatest(mDays[b]);
                            if (!mDays[b][4] && nbrLt !== null) { sum += nbrLt; cnt++; break; }
                        }
                        for (var ff = di + 1; ff <= Math.min(mDays.length - 1, di + 5); ff++) {
                            var nbrLt2 = dayLatest(mDays[ff]);
                            if (!mDays[ff][4] && nbrLt2 !== null) { sum += nbrLt2; cnt++; break; }
                        }
                        if (cnt > 0) ge = Math.round(sum / cnt);
                    }

                    // For StartOfDay gaps, interpolate start from neighbors' earliest activity
                    if (isBod) {
                        var cntB = 0, sumB = 0;
                        for (var bb = di - 1; bb >= Math.max(0, di - 5); bb--) {
                            var nbrFt = dayEarliest(mDays[bb]);
                            if (!mDays[bb][4] && nbrFt !== null) { sumB += nbrFt; cntB++; break; }
                        }
                        for (var fb = di + 1; fb <= Math.min(mDays.length - 1, di + 5); fb++) {
                            var nbrFt2 = dayEarliest(mDays[fb]);
                            if (!mDays[fb][4] && nbrFt2 !== null) { sumB += nbrFt2; cntB++; break; }
                        }
                        if (cntB > 0) gs = Math.round(sumB / cntB);
                    }

                    var gy1 = tY(gs, rTop);
                    var gy2 = tY(ge, rTop);
                    var gFill = "rgba(220,38,38,0.75)";
                    var gapLabel = isEod ? ' (End of Day)' : isBod ? ' (Start of Day)' : '';
                    var gapTip = dateStr + ' | ' + machine +
                        '\n' + Math.floor(gs / 60) + ':' + String(gs % 60).padStart(2, "0") +
                        '\u2013' + Math.floor(ge / 60) + ':' + String(ge % 60).padStart(2, "0") + gapLabel;
                    svg += '<rect class="strip-hover" x="' + x + '" y="' + gy1 + '" width="' + dw +
                           '" height="' + Math.max(0.5, gy2 - gy1) + '" fill="' + gFill + '" ' +
                           'data-tip="' + gapTip.replace(/"/g, '&quot;') + '" ' +
                           'data-date="' + dateStr + '" style="cursor:pointer;"/>';
                }
            }
        }

        // --- Month labels on x-axis (using packed indices) ---
        var monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
        var lastLabel = -1;
        var lastLabelX = -Infinity;
        var lastLabelYear = -1;
        var minLabelGap = 50; // minimum px between labels
        var axisY = height - margin.bottom + 12;
        for (var di = 0; di < sortedDates.length; di++) {
            var parts = sortedDates[di].split("-");
            var ym = parts[0] + "-" + parts[1];  // "YYYY-MM"
            if (ym !== String(lastLabel)) {
                lastLabel = ym;
                var lx = margin.left + di * dayWidth;
                // Skip partial first month — not enough room for the label
                if (di === 0 && parseInt(parts[2], 10) > 5) continue;
                // Skip if too close to previous label
                if (lx - lastLabelX < minLabelGap) continue;
                var yr = parseInt(parts[0], 10);
                var mo = parseInt(parts[1], 10) - 1;
                // Show 'YY on first labeled month of each year
                var label = yr !== lastLabelYear
                    ? monthNames[mo] + " \u2019" + String(yr).slice(-2)
                    : monthNames[mo];
                lastLabelYear = yr;
                svg += '<text x="' + lx + '" y="' + axisY + '" font-size="9" fill="#6B7280">' +
                       label + '</text>';
                svg += '<line x1="' + lx + '" y1="' + margin.top + '" x2="' + lx +
                       '" y2="' + (height - margin.bottom) + '" stroke="#D1D5DB" stroke-width="0.5" stroke-opacity="0.5"/>';
                lastLabelX = lx;
            }
        }

        // --- Strip legend (bottom-left, below axis labels) ---
        var sLegItems = [
            {c: "rgba(76,175,80,0.45)", l: "Active"},
            {c: "rgba(220,38,38,0.7)", l: "Full Day Down"},
            {c: "rgba(220,38,38,0.85)", l: "High Confidence"},
            {c: "rgba(234,88,12,0.7)", l: "Medium Confidence"},
            {c: "rgba(245,158,11,0.5)", l: "Low Confidence"},
        ];
        var sLegCanvas = document.createElement("canvas").getContext("2d");
        sLegCanvas.font = "11px Inter, system-ui, sans-serif";
        var sLegX = margin.left;
        var sLegY = height - 4;
        for (var sli = 0; sli < sLegItems.length; sli++) {
            svg += '<rect x="' + sLegX + '" y="' + (sLegY - 9) + '" width="10" height="10" fill="' +
                   sLegItems[sli].c + '" rx="2"/>';
            svg += '<text x="' + (sLegX + 15) + '" y="' + sLegY + '" font-size="11" fill="#6B7280">' +
                   sLegItems[sli].l + '</text>';
            sLegX += 15 + sLegCanvas.measureText(sLegItems[sli].l).width + 22;
        }

        svg += '</svg>';

        // Wrap with relative container for tooltip
        container.innerHTML = '<div style="position:relative;">' + svg +
            '<div id="strip-tooltip" style="display:none;position:absolute;pointer-events:none;' +
            'background:rgba(30,30,30,0.92);color:#fff;padding:6px 10px;border-radius:6px;' +
            'font-size:11px;line-height:1.4;white-space:pre-line;max-width:260px;z-index:10;' +
            'box-shadow:0 2px 8px rgba(0,0,0,0.25);font-family:Inter,sans-serif;"></div></div>';

        // Hover + tooltip for all interactive rects
        var stripTip = container.querySelector("#strip-tooltip");
        function showStripTip(evt, text) {
            if (!stripTip) return;
            stripTip.textContent = text;
            stripTip.style.display = "block";
            var rect = container.getBoundingClientRect();
            var sx = evt.clientX - rect.left + 12;
            var sy = evt.clientY - rect.top - 8;
            if (sx + 260 > rect.width) sx = evt.clientX - rect.left - 270;
            if (sy < 0) sy = 4;
            stripTip.style.left = sx + "px";
            stripTip.style.top = sy + "px";
        }
        function hideStripTip() { if (stripTip) stripTip.style.display = "none"; }

        var hoverEls = container.querySelectorAll(".strip-band, .strip-hover");
        for (var hi = 0; hi < hoverEls.length; hi++) {
            (function(el) {
                var origOpacity = el.getAttribute("opacity") || "1";
                el.addEventListener("mouseenter", function(e) {
                    el.setAttribute("opacity", "0.9");
                    el.style.filter = "brightness(1.2)";
                    showStripTip(e, el.getAttribute("data-tip"));
                });
                el.addEventListener("mousemove", function(e) { showStripTip(e, el.getAttribute("data-tip")); });
                el.addEventListener("mouseleave", function() {
                    el.setAttribute("opacity", origOpacity);
                    el.style.filter = "";
                    hideStripTip();
                });
                // Click to drill into level 3 for that day
                el.addEventListener("click", function() {
                    var date = el.getAttribute("data-date");
                    if (date && window.dash_clientside && window.dash_clientside.set_props) {
                        window.dash_clientside.set_props("machines-store-day-click", {data: date});
                    }
                });
            })(hoverEls[hi]);
        }

        return window.dash_clientside.no_update;
    },

};
