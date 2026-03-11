/**
 * Flow-Gantt (time-proportional Sankey) for Workflow page.
 * Depends on: 00_utils.js (hexToRgba)
 */

window.dash_clientside = window.dash_clientside || {};

window.dash_clientside.flowGantt = {

    renderFlowGantt: function(rawData, showLoopbacks) {
        if (!rawData || !rawData.stages || rawData.stages.length < 2) {
            return {
                data: [],
                layout: {
                    xaxis: {visible: false}, yaxis: {visible: false},
                    annotations: [{text: "No workflow data", x: 0.5, y: 0.5,
                        xref: "paper", yref: "paper", showarrow: false,
                        font: {size: 14, color: "#9CA3AF"}}],
                    plot_bgcolor: "#FFFFFF", paper_bgcolor: "#FFFFFF",
                    margin: {l: 0, r: 0, t: 0, b: 0}
                }
            };
        }

        var stages = rawData.stages;
        var counts = rawData.stageCounts;
        var flows = rawData.flowValues;
        var drops = rawData.dropoffs;
        var pending = rawData.pendingCounts || drops;
        var cancelled = rawData.cancelledCounts || [];
        var mDays = rawData.medianDays;
        var xPos = rawData.xPositions;
        var colors = rawData.colors;
        var loopbacks = rawData.loopbacks || [];
        var total = rawData.totalPatients;
        var nStages = stages.length;
        var height = rawData.height || 600;
        var fontFamily = "system-ui, -apple-system, sans-serif";

        // ─── Geometry ─────────────────────────────────────────────────
        var plotL = 0.05, plotR = 0.95, plotW = plotR - plotL;
        var yCenter = 0.45;
        var maxBarH = 0.62;      // height of tallest bar
        var barW = 0.020;        // narrow fixed bar width
        var pendingColor = "#F59E0B";    // amber
        var cancelledColor = "#EF4444";  // red

        function xMap(t) { return plotL + t * plotW; }

        // Cubic bezier evaluation
        function cubic(t, p0, p1, p2, p3) {
            var u = 1 - t;
            return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3;
        }

        // Build a filled polygon tracing a bezier band between two vertical
        // segments: src (x0, y0top→y0bot) and tgt (x1, y1top→y1bot).
        function bezierBand(x0, y0t, y0b, x1, y1t, y1b, nPts) {
            var n = nPts || 32;
            var dx = x1 - x0;
            var cp1 = x0 + dx * 0.38;
            var cp2 = x0 + dx * 0.62;
            var xs = [], yt = [], yb = [];
            for (var p = 0; p <= n; p++) {
                var t = p / n;
                xs.push(cubic(t, x0, cp1, cp2, x1));
                yt.push(cubic(t, y0t, y0t, y1t, y1t));
                yb.push(cubic(t, y0b, y0b, y1b, y1b));
            }
            return { x: xs.concat(xs.slice().reverse()), y: yt.concat(yb.slice().reverse()) };
        }

        // ─── Bar geometry ─────────────────────────────────────────────
        var maxCount = Math.max.apply(null, counts);
        var bars = [];
        for (var i = 0; i < nStages; i++) {
            var cx = xMap(xPos[i]);
            var ratio = maxCount > 0 ? counts[i] / maxCount : 0.5;
            var h = Math.max(ratio * maxBarH, 0.035);
            bars.push({
                cx: cx,
                l: cx - barW / 2,
                r: cx + barW / 2,
                top: yCenter + h / 2,
                bot: yCenter - h / 2,
                h: h,
            });
        }

        // ─── Edge trackers ────────────────────────────────────────────
        var rightEdge = [], leftEdge = [];
        for (var i = 0; i < nStages; i++) {
            rightEdge.push(bars[i].top);
            leftEdge.push(bars[i].top);
        }

        var traces = [];
        var shapes = [];
        var annotations = [];

        // ─── 1. FLOW BANDS + hover per band ──────────────────────────
        for (var i = 0; i < nStages - 1; i++) {
            if (flows[i] <= 0) continue;

            var srcH = bars[i].h * Math.min(flows[i] / Math.max(counts[i], 1), 1);
            var tgtH = bars[i + 1].h * Math.min(flows[i] / Math.max(counts[i + 1], 1), 1);

            var s0 = rightEdge[i];
            var s1 = Math.max(s0 - srcH, bars[i].bot);
            var t0 = leftEdge[i + 1];
            var t1 = Math.max(t0 - tgtH, bars[i + 1].bot);

            rightEdge[i] = s1;
            leftEdge[i + 1] = t1;

            var poly = bezierBand(bars[i].r, s0, s1, bars[i + 1].l, t0, t1, 36);
            traces.push({
                type: "scatter", x: poly.x, y: poly.y,
                fill: "toself",
                fillcolor: hexToRgba(colors[i], 0.20),
                line: { color: hexToRgba(colors[i], 0.35), width: 0.5 },
                mode: "lines", hoverinfo: "skip", showlegend: false,
            });

            // Hover grid across flow band (3 columns × 3 rows)
            var fDx = bars[i + 1].l - bars[i].r;
            var fCp1 = bars[i].r + fDx * 0.38;
            var fCp2 = bars[i].r + fDx * 0.62;
            var fhX = [], fhY = [];
            for (var hc = 1; hc <= 3; hc++) {
                var ht = hc / 4;
                var hxc = cubic(ht, bars[i].r, fCp1, fCp2, bars[i + 1].l);
                var yT = cubic(ht, s0, s0, t0, t0);
                var yB = cubic(ht, s1, s1, t1, t1);
                // 3 vertical positions: top-third, center, bottom-third
                fhX.push(hxc, hxc, hxc);
                fhY.push(yT - (yT - yB) * 0.2, (yT + yB) / 2, yB + (yT - yB) * 0.2);
            }
            var flowPct = total > 0 ? (flows[i] / total * 100).toFixed(1) : "0";
            var flowTip = "<b>" + stages[i] + " \u2192 " + stages[i + 1] + "</b><br>"
                + flows[i].toLocaleString() + " patients (" + flowPct + "%)<br>"
                + "Median wait: " + mDays[i] + " days";
            var flowTips = [];
            for (var ft = 0; ft < fhX.length; ft++) flowTips.push(flowTip);
            traces.push({
                type: "scatter", x: fhX, y: fhY,
                mode: "markers",
                marker: { size: 28, color: "rgba(0,0,0,0)" },
                hovertext: flowTips,
                hoverinfo: "text",
                hoverlabel: {
                    bgcolor: "#FFFFFF", bordercolor: colors[i],
                    font: { size: 12, color: "#1A1A2E", family: fontFamily },
                },
                showlegend: false,
            });
        }

        // ─── 2. EXIT FLOWS — pending (amber) & cancelled (red) ──────
        for (var i = 0; i < nStages - 1; i++) {
            var nPend = (pending && pending[i]) || 0;
            var nCanc = (cancelled && cancelled[i]) || 0;
            if (nPend + nCanc <= 0) continue;

            var exitLen = barW * 1.5;
            var exitDropY = 0.07;

            // ── Pending exit ──
            if (nPend > 0) {
                var pH = bars[i].h * Math.min(nPend / Math.max(counts[i], 1), 1);
                var pTop = rightEdge[i];
                var pBot = Math.max(pTop - pH, bars[i].bot);
                rightEdge[i] = pBot;

                var taper = pH * 0.12;
                var px1 = bars[i].r + exitLen;
                var py = pBot - exitDropY;

                var pPoly = bezierBand(bars[i].r, pTop, pBot, px1, py + taper, py, 20);
                traces.push({
                    type: "scatter", x: pPoly.x, y: pPoly.y,
                    fill: "toself",
                    fillcolor: hexToRgba(pendingColor, 0.18),
                    line: { color: hexToRgba(pendingColor, 0.30), width: 0.5 },
                    mode: "lines", hoverinfo: "skip", showlegend: false,
                });
                // Hover on pending exit
                traces.push({
                    type: "scatter",
                    x: [(bars[i].r + px1) / 2],
                    y: [(pTop + py) / 2],
                    mode: "markers",
                    marker: { size: 18, color: "rgba(0,0,0,0)" },
                    hovertext: ["<b>" + stages[i] + " \u2192 Pending</b><br>" + nPend.toLocaleString() + " patients still in pipeline"],
                    hoverinfo: "text",
                    hoverlabel: { bgcolor: "#FFFBEB", bordercolor: pendingColor, font: { size: 11, color: "#92400E", family: fontFamily } },
                    showlegend: false,
                });

                annotations.push({
                    x: px1 + 0.006, y: py + taper / 2,
                    xref: "x", yref: "y",
                    text: "<span style='color:" + pendingColor + ";font-size:9px'>" + nPend.toLocaleString() + " pending</span>",
                    showarrow: false, font: { size: 9, color: pendingColor },
                    xanchor: "left",
                });
            }

            // ── Cancelled exit ──
            if (nCanc > 0) {
                var cH = bars[i].h * Math.min(nCanc / Math.max(counts[i], 1), 1);
                var cTop = rightEdge[i];
                var cBot = Math.max(cTop - cH, bars[i].bot);
                rightEdge[i] = cBot;

                var cTaper = cH * 0.12;
                var cx1 = bars[i].r + exitLen;
                var cy = cBot - exitDropY - 0.02;  // offset below pending

                var cPoly = bezierBand(bars[i].r, cTop, cBot, cx1, cy + cTaper, cy, 20);
                traces.push({
                    type: "scatter", x: cPoly.x, y: cPoly.y,
                    fill: "toself",
                    fillcolor: hexToRgba(cancelledColor, 0.15),
                    line: { color: hexToRgba(cancelledColor, 0.28), width: 0.5 },
                    mode: "lines", hoverinfo: "skip", showlegend: false,
                });
                // Hover on cancelled exit
                traces.push({
                    type: "scatter",
                    x: [(bars[i].r + cx1) / 2],
                    y: [(cTop + cy) / 2],
                    mode: "markers",
                    marker: { size: 18, color: "rgba(0,0,0,0)" },
                    hovertext: ["<b>" + stages[i] + " \u2192 Cancelled / Unscheduled</b><br>" + nCanc.toLocaleString() + " patients"],
                    hoverinfo: "text",
                    hoverlabel: { bgcolor: "#FEF2F2", bordercolor: cancelledColor, font: { size: 11, color: "#991B1B", family: fontFamily } },
                    showlegend: false,
                });

                annotations.push({
                    x: cx1 + 0.006, y: cy + cTaper / 2,
                    xref: "x", yref: "y",
                    text: "<span style='color:" + cancelledColor + ";font-size:9px'>" + nCanc.toLocaleString() + " canc/unsched</span>",
                    showarrow: false, font: { size: 9, color: cancelledColor },
                    xanchor: "left",
                });
            }
        }

        // ─── 3. BAR RECTANGLES ───────────────────────────────────────
        for (var i = 0; i < nStages; i++) {
            shapes.push({
                type: "rect",
                x0: bars[i].l, y0: bars[i].bot,
                x1: bars[i].r, y1: bars[i].top,
                xref: "x", yref: "y",
                fillcolor: colors[i],
                line: { color: colors[i], width: 0 },
                layer: "above",
                opacity: 0.88,
            });
        }

        // ─── 4. LABELS & ANNOTATIONS ─────────────────────────────────
        for (var i = 0; i < nStages; i++) {
            // Stage name above bar
            annotations.push({
                x: bars[i].cx, y: bars[i].top + 0.035,
                xref: "x", yref: "y",
                text: "<b>" + stages[i] + "</b>",
                showarrow: false,
                font: { size: 12, color: colors[i], family: fontFamily },
            });

            // Count + percentage below bar
            var pct = total > 0 ? Math.round(counts[i] / total * 100) : 0;
            annotations.push({
                x: bars[i].cx, y: bars[i].bot - 0.035,
                xref: "x", yref: "y",
                text: "<b>" + counts[i].toLocaleString() + "</b>"
                    + " <span style='color:#9CA3AF;font-size:10px'>(" + pct + "%)</span>",
                showarrow: false,
                font: { size: 12, color: "#374151", family: fontFamily },
            });

            // Median inter-stage days — fixed row above all bars
            if (i < nStages - 1) {
                var midX = (bars[i].r + bars[i + 1].l) / 2;
                // Use tallest bar top + offset so all labels sit on the same line
                var daysRowY = bars[0].top + 0.065;
                annotations.push({
                    x: midX, y: daysRowY,
                    xref: "x", yref: "y",
                    text: "<b>" + mDays[i] + "</b> " + (mDays[i] === 1 ? "day" : "days"),
                    showarrow: false,
                    font: { size: 13, color: "#4B5563", family: fontFamily },
                });
            }
        }

        // ─── 5. LOOPBACK ARCS ────────────────────────────────────────
        // Uses actual source→target pairs computed from stage sequence data.
        // Each pair shows which stage a patient was at before repeating.
        if (showLoopbacks && rawData.loopbackPairs && rawData.loopbackPairs.length > 0) {
            var pairs = rawData.loopbackPairs.slice().sort(function(a, b) {
                // Longer arcs higher, shorter arcs lower
                return Math.abs(b.fromIdx - b.toIdx) - Math.abs(a.fromIdx - a.toIdx);
            });

            for (var p = 0; p < pairs.length; p++) {
                var pair = pairs[p];
                if (pair.count <= 0) continue;

                var fi = pair.fromIdx, ti = pair.toIdx;
                var fromX = bars[fi].cx;
                var toX = bars[ti].cx;
                var peakY = bars[0].top + 0.05 + p * 0.025;
                var arcColor = colors[ti];

                // Bezier arc above the chart
                shapes.push({
                    type: "path",
                    xref: "x", yref: "y",
                    path: "M " + fromX + " " + bars[fi].top
                        + " C " + fromX + " " + peakY
                        + ", " + toX + " " + peakY
                        + ", " + toX + " " + bars[ti].top,
                    line: { color: hexToRgba(arcColor, 0.50), width: 1.5, dash: "dot" },
                    fillcolor: "rgba(0,0,0,0)",
                    layer: "above",
                });

                // Arrow at target
                var arrowSize = 0.012;
                shapes.push({
                    type: "path",
                    xref: "x", yref: "y",
                    path: "M " + toX + " " + bars[ti].top
                        + " L " + (toX - arrowSize) + " " + (bars[ti].top + arrowSize * 1.5)
                        + " L " + (toX + arrowSize) + " " + (bars[ti].top + arrowSize * 1.5)
                        + " Z",
                    fillcolor: hexToRgba(arcColor, 0.50),
                    line: { width: 0 },
                    layer: "above",
                });

                // Label: "↩ N  Source → Target"
                annotations.push({
                    x: (fromX + toX) / 2, y: peakY + 0.015,
                    xref: "x", yref: "y",
                    text: "<span style='font-size:9px'>\u21A9 " + pair.count.toLocaleString()
                        + "  " + stages[fi] + "\u2192" + stages[ti] + "</span>",
                    showarrow: false,
                    font: { size: 9, color: arcColor },
                });
            }
        }

        // ─── 6. BAR HOVER TRACES ─────────────────────────────────────
        // Vertical column of invisible markers per bar so hover triggers
        // anywhere along the bar height.
        var hx = [], hy = [], ht = [];
        for (var i = 0; i < nStages; i++) {
            var pct2 = total > 0 ? (counts[i] / total * 100).toFixed(1) : "0";
            var tip = "<b>" + stages[i] + "</b><br>"
                + counts[i].toLocaleString() + " patients (" + pct2 + "%)";
            if (i < nStages - 1) {
                tip += "<br>\u2192 " + flows[i].toLocaleString() + " progressed (" + mDays[i] + "d median)";
                var pi = (pending && pending[i]) || 0;
                var ci = (cancelled && cancelled[i]) || 0;
                if (pi > 0) tip += "<br>\u23F3 " + pi.toLocaleString() + " pending";
                if (ci > 0) tip += "<br>\u2715 " + ci.toLocaleString() + " cancelled/unsched";
            }
            if (loopbacks[i] > 0) tip += "<br>\u21A9 " + loopbacks[i].toLocaleString() + " repeats";
            // 5 markers stacked vertically across bar height
            for (var v = 0; v < 5; v++) {
                var vy = bars[i].bot + (bars[i].h * (v + 0.5) / 5);
                hx.push(bars[i].cx);
                hy.push(vy);
                ht.push(tip);
            }
        }
        traces.push({
            type: "scatter", x: hx, y: hy,
            mode: "markers",
            marker: { size: 20, color: "rgba(0,0,0,0)" },
            hovertext: ht, hoverinfo: "text",
            hoverlabel: {
                bgcolor: "#FFFFFF", bordercolor: "#E0E0E0",
                font: { size: 12, color: "#1A1A2E", family: fontFamily },
            },
            showlegend: false,
        });

        // ─── Return figure ────────────────────────────────────────────
        return {
            data: traces,
            layout: {
                height: height,
                xaxis: {
                    range: [-0.02, 1.02], visible: false, fixedrange: true,
                    showgrid: false, zeroline: false,
                },
                yaxis: {
                    range: [0.02, 0.87], visible: false, fixedrange: true,
                    showgrid: false, zeroline: false,
                },
                shapes: shapes,
                annotations: annotations,
                plot_bgcolor: "#FFFFFF",
                paper_bgcolor: "#FFFFFF",
                margin: { l: 6, r: 6, t: 6, b: 6 },
                showlegend: false,
                hovermode: "closest",
                hoverdistance: 20,
                font: { family: fontFamily },
            }
        };
    }
};
