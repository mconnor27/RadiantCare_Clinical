/* v2 */
/**
 * Flow-Gantt SVG renderer for Workflow page.
 * Renders a time-proportional Sankey-style pipeline directly as SVG
 * for native shape-level hover and tooltip support.
 * Depends on: 00_utils.js (hexToRgba)
 */

window.dash_clientside = window.dash_clientside || {};

// Helper: update band highlight state after click selection
function _updateBandSelection(svg, selectedIdx) {
    var bands = svg.querySelectorAll(".flow-gantt-band");
    for (var b = 0; b < bands.length; b++) {
        var band = bands[b];
        var idx = parseInt(band.getAttribute("data-flow-index"), 10);
        if (selectedIdx === null || selectedIdx === undefined) {
            // Deselect all — restore originals
            band.setAttribute("data-base-fill", band.getAttribute("data-orig-fill"));
            band.setAttribute("data-base-stroke", band.getAttribute("data-orig-stroke"));
            band.setAttribute("data-base-stroke-width", band.getAttribute("data-orig-stroke-width"));
            band.style.fill = band.getAttribute("data-orig-fill");
            band.style.stroke = band.getAttribute("data-orig-stroke");
            band.style.strokeWidth = band.getAttribute("data-orig-stroke-width");
            band.style.opacity = "";
            band.classList.remove("is-selected", "is-dimmed");
        } else if (idx === selectedIdx) {
            // Selected band — use hover style as persistent base
            band.setAttribute("data-base-fill", band.getAttribute("data-hover-fill"));
            band.setAttribute("data-base-stroke", band.getAttribute("data-hover-stroke"));
            band.setAttribute("data-base-stroke-width", band.getAttribute("data-hover-stroke-width"));
            band.style.fill = band.getAttribute("data-hover-fill");
            band.style.stroke = band.getAttribute("data-hover-stroke");
            band.style.strokeWidth = band.getAttribute("data-hover-stroke-width");
            band.style.opacity = "";
            band.classList.add("is-selected");
            band.classList.remove("is-dimmed");
        } else {
            // Dimmed band — restore originals with low opacity
            band.setAttribute("data-base-fill", band.getAttribute("data-orig-fill"));
            band.setAttribute("data-base-stroke", band.getAttribute("data-orig-stroke"));
            band.setAttribute("data-base-stroke-width", band.getAttribute("data-orig-stroke-width"));
            band.style.fill = band.getAttribute("data-orig-fill");
            band.style.stroke = band.getAttribute("data-orig-stroke");
            band.style.strokeWidth = band.getAttribute("data-orig-stroke-width");
            band.style.opacity = "0.3";
            band.classList.add("is-dimmed");
            band.classList.remove("is-selected");
        }
    }
}

window.dash_clientside.flowGantt = {

    renderFlowGantt: function(rawData, showLoopbacks, rawDataB, showLoopbacksB, compareMode) {
        var container = document.getElementById("wf-flow-gantt");
        if (!container) return window.dash_clientside.no_update;

        // ─── Compare mode: split container into A/B halves ───────────
        if (compareMode && rawDataB) {
            container.innerHTML = "";
            // Compute explicit pixel heights so sub-containers resolve immediately
            var parentH = container.clientHeight || 800;
            var subH = Math.floor(parentH * 0.48);
            var divH = parentH - 2 * subH;

            var wrapA = document.createElement("div");
            wrapA.id = "wf-flow-gantt-a";
            wrapA.style.cssText = "width:100%;height:" + subH + "px;position:relative;overflow:hidden;";
            var labelA = document.createElement("div");
            labelA.className = "flow-gantt-dataset-label";
            labelA.textContent = "A";
            labelA.style.cssText = "position:absolute;left:4px;top:4px;z-index:5;font-size:16px;font-weight:700;color:#2196F3;";
            wrapA.appendChild(labelA);

            var divider = document.createElement("div");
            divider.style.cssText = "width:100%;height:0;border-top:1px dashed #D1D5DB;margin:" + Math.floor(divH / 2) + "px 0;";

            var wrapB = document.createElement("div");
            wrapB.id = "wf-flow-gantt-b";
            wrapB.style.cssText = "width:100%;height:" + subH + "px;position:relative;overflow:hidden;";
            var labelB = document.createElement("div");
            labelB.className = "flow-gantt-dataset-label";
            labelB.textContent = "B";
            labelB.style.cssText = "position:absolute;left:4px;top:4px;z-index:5;font-size:16px;font-weight:700;color:#FF9800;";
            wrapB.appendChild(labelB);

            container.appendChild(wrapA);
            container.appendChild(divider);
            container.appendChild(wrapB);

            // Scale xPositions so pipeline widths are proportional to total
            // duration. Each pipeline's Python-generated xPositions are [0..1]
            // (well-spaced with min-gap). We scale the shorter pipeline down by
            // the ratio of its total duration to the longer one's.
            var xPosA = rawData.xPositions;
            var xPosB = rawDataB.xPositions || xPosA;
            var mDaysA = rawData.medianDays;
            var mDaysB = rawDataB.medianDays;
            if (mDaysA && mDaysB) {
                var totalA = 0, totalB = 0;
                for (var si = 0; si < mDaysA.length; si++) totalA += (mDaysA[si] || 0);
                for (var si = 0; si < mDaysB.length; si++) totalB += (mDaysB[si] || 0);
                var globalMax = Math.max(totalA, totalB, 1);
                var scaleA = totalA / globalMax;
                var scaleB = totalB / globalMax;
                // Scale the shorter pipeline's positions; longer one stays at [0..1]
                // Then enforce minimum gap between consecutive stages
                var MIN_GAP = 0.06;
                function scaleAndEnforceGap(origPos, scale) {
                    if (scale >= 1) return origPos;
                    var pos = origPos.map(function(v) { return v * scale; });
                    // Enforce minimum gap — push positions right if too close
                    for (var j = 1; j < pos.length; j++) {
                        if (pos[j] - pos[j - 1] < MIN_GAP) {
                            pos[j] = pos[j - 1] + MIN_GAP;
                        }
                    }
                    return pos;
                }
                xPosA = scaleAndEnforceGap(xPosA, scaleA);
                xPosB = scaleAndEnforceGap(xPosB, scaleB);
            }

            // Override xPositions in both datasets
            var dataACopy = Object.assign({}, rawData, {xPositions: xPosA});
            var dataBCopy = Object.assign({}, rawDataB, {xPositions: xPosB});

            // Render each pipeline into its own sub-container.
            // Temporarily swap IDs so getElementById("wf-flow-gantt")
            // finds the child, not the parent container.
            container.id = "_wf-flow-gantt-parent";
            wrapA.id = "wf-flow-gantt";
            this._renderSinglePipeline(dataACopy, showLoopbacks, "A");
            wrapA.id = "wf-flow-gantt-a";
            wrapB.id = "wf-flow-gantt";
            this._renderSinglePipeline(dataBCopy, showLoopbacksB, "B");
            wrapB.id = "wf-flow-gantt-b";
            container.id = "wf-flow-gantt";

            // Store data for resize
            container.__fgData = rawData;
            container.__fgDataB = rawDataB;
            container.__fgLoopbacks = showLoopbacks;
            container.__fgLoopbacksB = showLoopbacksB;
            container.__fgCompare = true;
            container.__fgW = container.clientWidth;
            container.__fgH = container.clientHeight;

            if (window.ResizeObserver && !container.__fgRO) {
                var debounce;
                container.__fgRO = new ResizeObserver(function() {
                    var nw = container.clientWidth;
                    var nh = container.clientHeight;
                    if (nw && nh && (nw !== container.__fgW || nh !== container.__fgH)) {
                        clearTimeout(debounce);
                        debounce = setTimeout(function() {
                            window.dash_clientside.flowGantt.renderFlowGantt(
                                container.__fgData, container.__fgLoopbacks,
                                container.__fgDataB, container.__fgLoopbacksB,
                                container.__fgCompare
                            );
                        }, 150);
                    }
                });
                container.__fgRO.observe(container);
            }

            return window.dash_clientside.no_update;
        }

        // ─── Single pipeline mode ────────────────────────────────────
        // Clear compare-mode state so ResizeObserver doesn't re-render in compare layout
        container.__fgData = rawData;
        container.__fgDataB = null;
        container.__fgLoopbacks = showLoopbacks;
        container.__fgLoopbacksB = false;
        container.__fgCompare = false;
        return this._renderSinglePipeline(rawData, showLoopbacks, null);
    },

    _renderSinglePipeline: function(rawData, showLoopbacks, pipelineLabel) {
        var container = document.getElementById("wf-flow-gantt");
        if (!container) return window.dash_clientside.no_update;

        // ─── Clear previous render ──────────────────────────────────────
        container.innerHTML = "";
        // Re-add label if in compare mode
        if (pipelineLabel) {
            var lbl = document.createElement("div");
            lbl.className = "flow-gantt-dataset-label";
            lbl.textContent = pipelineLabel;
            var lblColor = pipelineLabel === "A" ? "#2196F3" : "#FF9800";
            lbl.style.cssText = "position:absolute;left:4px;top:4px;z-index:5;font-size:16px;font-weight:700;color:" + lblColor + ";";
            container.appendChild(lbl);
        }

        // ─── SVG helpers ────────────────────────────────────────────────
        var NS = "http://www.w3.org/2000/svg";

        // Size viewBox to match the container's actual aspect ratio so the
        // chart fills the full card width instead of letterboxing.
        var cw = container.clientWidth  || 1200;
        var ch = container.clientHeight || 600;
        var VB_W = cw;
        var VB_H = ch;

        function svgEl(tag, attrs) {
            var el = document.createElementNS(NS, tag);
            if (attrs) {
                for (var k in attrs) {
                    if (attrs.hasOwnProperty(k)) el.setAttribute(k, attrs[k]);
                }
            }
            return el;
        }

        // Map normalised coords to SVG pixel space.
        // x: 0-1 fills full width.
        // y: trim the visible range so the pipeline uses more of the card.
        // Loopbacks need a little extra headroom for the return arcs.
        var yHi = showLoopbacks ? 0.92 : 0.88;
        var yLo = showLoopbacks ? 0.08 : 0.10;
        var yPad = 4;                       // px padding top & bottom
        var drawH = VB_H - 2 * yPad;

        var xPadR = 8;  // px right padding so last label isn't clipped
        function sx(v) { return v * (VB_W - xPadR); }
        function sy(v) { return yPad + (yHi - v) / (yHi - yLo) * drawH; }

        // Convert {x: [...], y: [...]} polygon to SVG path d attribute
        function polyToPath(poly) {
            var d = "M" + sx(poly.x[0]).toFixed(1) + "," + sy(poly.y[0]).toFixed(1);
            for (var i = 1; i < poly.x.length; i++) {
                d += "L" + sx(poly.x[i]).toFixed(1) + "," + sy(poly.y[i]).toFixed(1);
            }
            return d + "Z";
        }

        // ─── Tooltip setup (reuse across renders) ──────────────────────
        var tooltipId = "__flow_gantt_tooltip";
        var tooltip = document.getElementById(tooltipId);
        if (!tooltip) {
            tooltip = document.createElement("div");
            tooltip.id = tooltipId;
            tooltip.className = "flow-gantt-tooltip";
            document.body.appendChild(tooltip);
        }
        tooltip.style.display = "none";

        function attachHover(el, tipHtml, accentColor) {
            el.style.cursor = "pointer";
            el.addEventListener("mouseenter", function() {
                this.classList.add("is-hovered");
                var hf = this.getAttribute("data-hover-fill");
                var hs = this.getAttribute("data-hover-stroke");
                var hw = this.getAttribute("data-hover-stroke-width");
                if (hf) this.style.fill = hf;
                if (hs) this.style.stroke = hs;
                if (hw) this.style.strokeWidth = hw;
                tooltip.innerHTML = tipHtml;
                tooltip.style.borderLeftColor = accentColor || "#7C2A83";
                tooltip.style.display = "block";
            });
            el.addEventListener("mousemove", function(e) {
                var x = e.clientX + 14, y = e.clientY + 14;
                var tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
                if (x + tw > window.innerWidth - 10) x = e.clientX - tw - 14;
                if (y + th > window.innerHeight - 10) y = e.clientY - th - 14;
                if (y < 10) y = 10;
                tooltip.style.left = x + "px";
                tooltip.style.top = y + "px";
            });
            el.addEventListener("mouseleave", function() {
                this.classList.remove("is-hovered");
                var bf = this.getAttribute("data-base-fill");
                var bs = this.getAttribute("data-base-stroke");
                var bw = this.getAttribute("data-base-stroke-width");
                if (bf) this.style.fill = bf;
                if (bs) this.style.stroke = bs;
                if (bw) this.style.strokeWidth = bw;
                tooltip.style.display = "none";
            });
        }

        // ─── Empty state ────────────────────────────────────────────────
        if (!rawData || !rawData.stages || rawData.stages.length < 2) {
            var svg = svgEl("svg", {
                viewBox: "0 0 " + VB_W + " " + VB_H,
                width: "100%", height: "100%",
                preserveAspectRatio: "xMinYMin meet",
            });
            var emptyText = svgEl("text", {
                x: VB_W / 2, y: VB_H / 2,
                "text-anchor": "middle",
                "dominant-baseline": "middle",
                "font-size": "14",
                fill: "#9CA3AF",
                "font-family": "system-ui, -apple-system, sans-serif",
            });
            emptyText.textContent = "No workflow data";
            svg.appendChild(emptyText);
            container.appendChild(svg);
            return window.dash_clientside.no_update;
        }

        // ─── Data extraction ────────────────────────────────────────────
        var stages     = rawData.stages;
        var counts     = rawData.stageCounts;
        var flows      = rawData.flowValues;
        var drops      = rawData.dropoffs;
        var pending    = rawData.pendingCounts || drops;
        var cancelled  = rawData.cancelledCounts || [];
        var aggFunc    = rawData.aggFunc || "median";
        var mDays      = aggFunc === "mean" ? (rawData.meanDays || rawData.medianDays) : rawData.medianDays;
        var aggLabel   = aggFunc === "mean" ? "Mean" : "Median";
        var aDays      = rawData.allottedDays || [];
        var otPcts     = rawData.onTimePcts || [];
        var xPos       = rawData.xPositions;
        var colors     = rawData.colors;
        var loopbacks  = rawData.loopbacks || [];
        var total      = rawData.totalPatients;
        var nStages    = stages.length;
        var fontFamily = "system-ui, -apple-system, sans-serif";

        // ─── Geometry constants ─────────────────────────────────────────
        var plotL = 0.02, plotR = 0.98, plotW = plotR - plotL;
        var yCenter = 0.52;
        var maxBarH = 0.54;
        var barW = 0.028;
        var pendingColor   = "#64748B";
        var cancelledColor = "#EF4444";

        function xMap(t) { return plotL + t * plotW; }

        // Cubic bezier evaluation
        function cubic(t, p0, p1, p2, p3) {
            var u = 1 - t;
            return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3;
        }

        // Build filled polygon between two vertical segments via bezier
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

        // Bezier band that bows downward to avoid overlapping the main flow
        function exitBezierBand(x0, y0t, y0b, x1, y1t, y1b, sag, nPts) {
            var n = nPts || 36;
            var dx = x1 - x0;
            var cp1 = x0 + dx * 0.35;
            var cp2 = x0 + dx * 0.65;
            var sagT = Math.min(y0t, y1t) - sag;
            var sagB = Math.min(y0b, y1b) - sag;
            var xs = [], yt = [], yb = [];
            for (var p = 0; p <= n; p++) {
                var t = p / n;
                xs.push(cubic(t, x0, cp1, cp2, x1));
                yt.push(cubic(t, y0t, sagT, sagT, y1t));
                yb.push(cubic(t, y0b, sagB, sagB, y1b));
            }
            return { x: xs.concat(xs.slice().reverse()), y: yt.concat(yb.slice().reverse()) };
        }

        // Darken a hex color by a factor (0 = black, 1 = unchanged)
        function darkenColor(hex, factor) {
            var h = hex.replace("#", "");
            var r = Math.round(parseInt(h.substring(0, 2), 16) * factor);
            var g = Math.round(parseInt(h.substring(2, 4), 16) * factor);
            var b = Math.round(parseInt(h.substring(4, 6), 16) * factor);
            return "#" + ("0" + r.toString(16)).slice(-2) + ("0" + g.toString(16)).slice(-2) + ("0" + b.toString(16)).slice(-2);
        }

        // Pick white or dark text based on background luminance
        function textColorForBg(hex) {
            if (!hex || hex.charAt(0) !== "#") return "#374151";
            var h = hex.replace("#", "");
            if (h.length !== 6) return "#374151";
            var r = parseInt(h.substring(0, 2), 16);
            var g = parseInt(h.substring(2, 4), 16);
            var b = parseInt(h.substring(4, 6), 16);
            return (0.299 * r + 0.587 * g + 0.114 * b) > 160 ? "#374151" : "#FFFFFF";
        }

        function mixHexWithWhite(hex, amount) {
            if (!hex || typeof hex !== "string" || hex.charAt(0) !== "#") return hex;
            var h = hex.replace("#", "");
            if (h.length !== 6) return hex;
            var r = parseInt(h.substring(0, 2), 16);
            var g = parseInt(h.substring(2, 4), 16);
            var b = parseInt(h.substring(4, 6), 16);
            var a = Math.max(0, Math.min(amount || 0, 1));
            var nr = Math.round(r + (255 - r) * a);
            var ng = Math.round(g + (255 - g) * a);
            var nb = Math.round(b + (255 - b) * a);
            return "#" + [nr, ng, nb].map(function(v) {
                var s = v.toString(16);
                return s.length === 1 ? "0" + s : s;
            }).join("");
        }

        // ─── Bar geometry ───────────────────────────────────────────────
        var maxCount = Math.max.apply(null, counts);
        var bars = [];
        var maxTop = yCenter + maxBarH / 2;
        var topBias = 0.4;  // 0 = centered, 1 = fully top-aligned
        for (var i = 0; i < nStages; i++) {
            var cx = xMap(xPos[i]);
            var ratio = maxCount > 0 ? counts[i] / maxCount : 0.5;
            var h = Math.max(ratio * maxBarH, 0.035);
            var centeredTop = yCenter + h / 2;
            var shift = topBias * (maxTop - centeredTop);
            bars.push({
                cx: cx,
                l: cx - barW / 2,
                r: cx + barW / 2,
                top: centeredTop + shift,
                bot: (yCenter - h / 2) + shift,
                h: h,
            });
        }

        // Edge trackers (for stacking flows/exits along bar edges)
        // Flow bands: top-down from bar top
        // Exit bands: bottom-up from bar bottom (separate tracker)
        var rightEdge = [], leftEdge = [], exitEdge = [];
        for (var i = 0; i < nStages; i++) {
            rightEdge.push(bars[i].top);
            leftEdge.push(bars[i].top);
            exitEdge.push(bars[i].bot);
        }

        // ─── Create SVG ────────────────────────────────────────────────
        var svg = svgEl("svg", {
            viewBox: "0 0 " + VB_W + " " + VB_H,
            width: "100%", height: "100%",
            preserveAspectRatio: "xMinYMin meet",
            style: "font-family: " + fontFamily,
        });

        // Layer groups (render order = z-order)
        var gBands      = svgEl("g", {"class": "layer-bands"});
        var gExits      = svgEl("g", {"class": "layer-exits"});
        var gConnectors = svgEl("g", {"class": "layer-connectors"});
        var gBars       = svgEl("g", {"class": "layer-bars"});
        var gLoopbacks  = svgEl("g", {"class": "layer-loopbacks"});
        var gLabels     = svgEl("g", {"class": "layer-labels"});

        // ─── 1. FLOW BANDS ─────────────────────────────────────────────
        var bandGeo = [];  // store band geometry for days labels
        for (var i = 0; i < nStages - 1; i++) {
            if (flows[i] <= 0) { bandGeo.push(null); continue; }

            var srcH = bars[i].h * Math.min(flows[i] / Math.max(counts[i], 1), 1);
            var tgtH = bars[i + 1].h * Math.min(flows[i] / Math.max(counts[i + 1], 1), 1);

            var s0 = rightEdge[i];
            var s1 = Math.max(s0 - srcH, bars[i].bot);
            var t0 = leftEdge[i + 1];
            var t1 = Math.max(t0 - tgtH, bars[i + 1].bot);

            bandGeo.push({ s0: s0, s1: s1, t0: t0, t1: t1 });

            rightEdge[i] = s1;
            leftEdge[i + 1] = t1;

            var poly = bezierBand(bars[i].r, s0, s1, bars[i + 1].l, t0, t1, 36);
            var baseFill   = hexToRgba(colors[i], 0.20);
            var baseStroke = hexToRgba(colors[i], 0.35);
            var hoverFill  = hexToRgba(colors[i], 0.30);
            var hoverStroke = hexToRgba(colors[i], 0.55);

            var path = svgEl("path", {
                d: polyToPath(poly),
                fill: baseFill,
                stroke: baseStroke,
                "stroke-width": "0.5",
                "class": "flow-gantt-band",
                "data-flow-index": i,
                "data-base-fill": baseFill,
                "data-base-stroke": baseStroke,
                "data-base-stroke-width": "0.5",
                "data-hover-fill": hoverFill,
                "data-hover-stroke": hoverStroke,
                "data-hover-stroke-width": "1.5",
                "data-orig-fill": baseFill,
                "data-orig-stroke": baseStroke,
                "data-orig-stroke-width": "0.5",
            });

            var flowPct = total > 0 ? (flows[i] / total * 100).toFixed(1) : "0";
            var flowTip = "<b>" + stages[i] + " \u2192 " + stages[i + 1] + "</b><br>"
                + flows[i].toLocaleString() + " patients (" + flowPct + "%)<br>"
                + aggLabel + " wait: " + mDays[i] + " days";
            if (aDays[i] != null) {
                flowTip += "<br>Allotted: " + aDays[i] + " days";
                if (otPcts[i] != null) {
                    var pctColor = otPcts[i] >= 70 ? "#4CAF50" : otPcts[i] >= 40 ? "#FF9800" : "#E53935";
                    flowTip += " — <span style='color:" + pctColor + "'>"
                        + otPcts[i] + "% on time</span>";
                }
            }
            attachHover(path, flowTip, colors[i]);

            // Click to select/deselect flow band
            (function(el, bandIdx) {
                el.addEventListener("click", function(e) {
                    e.stopPropagation();
                    var cur = container.__fgSelectedFlow;
                    var sel = (cur === bandIdx) ? null : bandIdx;
                    container.__fgSelectedFlow = sel;
                    _updateBandSelection(svg, sel);
                    // Also highlight the corresponding band in the other pipeline
                    ["wf-flow-gantt-a", "wf-flow-gantt-b"].forEach(function(oid) {
                        var other = document.getElementById(oid);
                        if (other && other !== container) {
                            var oSvg = other.querySelector("svg");
                            if (oSvg) _updateBandSelection(oSvg, sel);
                        }
                    });
                    if (window.dash_clientside && window.dash_clientside.set_props) {
                        window.dash_clientside.set_props("wf-store-selected-flow", {data: sel});
                        window.dash_clientside.set_props("wf-b-store-selected-flow", {data: sel});
                    }
                });
            })(path, i);

            gBands.appendChild(path);
        }

        // ─── 2. EXIT FLOWS — funnel to pending & cancelled collectors ─
        var exitSources = { pending: [], cancelled: [] };
        var totalPending = 0, totalCancelled = 0;

        for (var i = 0; i < nStages - 1; i++) {
            var nPend = (pending && pending[i]) || 0;
            var nCanc = (cancelled && cancelled[i]) || 0;

            // Bottom-up from bar bottom: cancelled first (lowest), then pending (closer to flow)
            if (nCanc > 0) {
                var cH = bars[i].h * Math.min(nCanc / Math.max(counts[i], 1), 1);
                var cBot = exitEdge[i];
                var cTop = Math.min(cBot + cH, bars[i].top);
                exitEdge[i] = cTop;
                exitSources.cancelled.push({ idx: i, top: cTop, bot: cBot, count: nCanc });
                totalCancelled += nCanc;
            }

            if (nPend > 0) {
                var pH = bars[i].h * Math.min(nPend / Math.max(counts[i], 1), 1);
                var pBot = exitEdge[i];
                var pTop = Math.min(pBot + pH, bars[i].top);
                exitEdge[i] = pTop;
                exitSources.pending.push({ idx: i, top: pTop, bot: pBot, count: nPend });
                totalPending += nPend;
            }
        }

        // Collector bars — right-aligned below last stage (Treatment)
        var lastBar    = bars[nStages - 1];
        var collX      = lastBar.cx;
        var collBW     = barW;
        var collL      = collX - collBW / 2;
        var collR      = collX + collBW / 2;
        var collGap    = 0.062;
        var collSpc    = 0.05;
        var collCursor = lastBar.bot - collGap;

        // ── Pending collector ──
        if (totalPending > 0) {
            var pCollTop = collCursor;
            var pCollH   = Math.min(0.06, Math.max(0.025, maxBarH * totalPending / maxCount));
            var pCollBot = pCollTop - pCollH;

            var pBarFill  = hexToRgba(pendingColor, 0.85);
            var pBarHover = mixHexWithWhite(pendingColor, 0.18);
            var pBarRect  = svgEl("rect", {
                x: sx(collL).toFixed(1), y: sy(pCollTop).toFixed(1),
                width: (sx(collR) - sx(collL)).toFixed(1),
                height: (sy(pCollBot) - sy(pCollTop)).toFixed(1),
                fill: pBarFill, stroke: pendingColor,
                "stroke-width": "0.8", rx: "2",
                "class": "flow-gantt-stage",
                "data-base-fill": pBarFill, "data-base-stroke": pendingColor,
                "data-base-stroke-width": "0.8",
                "data-hover-fill": pBarHover, "data-hover-stroke": pendingColor,
                "data-hover-stroke-width": "1.6",
            });
            var pPctTotal = total > 0 ? (totalPending / total * 100).toFixed(1) : "0";
            var pBarTip = "<b>Pending / In Pipeline</b><br>"
                + totalPending.toLocaleString() + " patients (" + pPctTotal + "%) awaiting next step";
            for (var s = 0; s < exitSources.pending.length; s++) {
                var pSrcPct = total > 0 ? (exitSources.pending[s].count / total * 100).toFixed(1) : "0";
                pBarTip += "<br><span style='color:" + colors[exitSources.pending[s].idx]
                    + "'>&#9679;</span> " + exitSources.pending[s].count.toLocaleString()
                    + " from " + stages[exitSources.pending[s].idx] + " (" + pSrcPct + "%)";
            }
            attachHover(pBarRect, pBarTip, pendingColor);
            gBars.appendChild(pBarRect);

            var pStack = pCollBot;  // bottom-up on collector
            for (var s = 0; s < exitSources.pending.length; s++) {
                var src    = exitSources.pending[s];
                var sliceH = pCollH * (src.count / totalPending);
                var sliceT = pStack + sliceH;  // top of this slice
                var dist   = collL - bars[src.idx].r;
                var sag    = 0.008 + dist * 0.012;
                var poly   = exitBezierBand(bars[src.idx].r, src.top, src.bot, collL, sliceT, pStack, sag, 36);
                var pbF = hexToRgba(pendingColor, 0.15), pbS = hexToRgba(pendingColor, 0.28);
                var pbHF = hexToRgba(pendingColor, 0.25), pbHS = hexToRgba(pendingColor, 0.45);
                var pPath = svgEl("path", {
                    d: polyToPath(poly), fill: pbF, stroke: pbS,
                    "stroke-width": "0.5",
                    "class": "flow-gantt-exit flow-gantt-exit-pending",
                    "data-base-fill": pbF, "data-base-stroke": pbS, "data-base-stroke-width": "0.5",
                    "data-hover-fill": pbHF, "data-hover-stroke": pbHS, "data-hover-stroke-width": "1.2",
                });
                // Invisible wider hit-area for thin bands
                var minNorm = 14 * (yHi - yLo) / drawH;  // 14px in normalized coords
                var bandThick0 = src.top - src.bot;
                var bandThick1 = sliceT - pStack;
                var pad0 = Math.max(0, (minNorm - bandThick0) / 2);
                var pad1 = Math.max(0, (minNorm - bandThick1) / 2);
                var hitPoly = exitBezierBand(bars[src.idx].r, src.top + pad0, src.bot - pad0, collL, sliceT + pad1, pStack - pad1, sag, 36);
                var hitPath = svgEl("path", {
                    d: polyToPath(hitPoly), fill: "transparent", stroke: "none",
                    "pointer-events": "all", cursor: "pointer",
                });
                pPath.style.pointerEvents = "none";
                var pTip = "<b>" + stages[src.idx] + " &#8594; Pending</b><br>"
                    + src.count.toLocaleString() + " patients still in pipeline"
                    + " (" + (total > 0 ? (src.count / total * 100).toFixed(1) : "0") + "%)";
                (function(vis, hit, tip, bF, bS, hF, hS) {
                    hit.addEventListener("mouseenter", function() {
                        vis.style.fill = hF;
                        vis.style.stroke = hS;
                        vis.style.strokeWidth = "1.2";
                        tooltip.innerHTML = tip;
                        tooltip.style.borderLeftColor = pendingColor;
                        tooltip.style.display = "block";
                    });
                    hit.addEventListener("mousemove", function(e) {
                        var x = e.clientX + 14, y = e.clientY + 14;
                        var tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
                        if (x + tw > window.innerWidth - 10) x = e.clientX - tw - 14;
                        if (y + th > window.innerHeight - 10) y = e.clientY - th - 14;
                        if (y < 10) y = 10;
                        tooltip.style.left = x + "px";
                        tooltip.style.top = y + "px";
                    });
                    hit.addEventListener("mouseleave", function() {
                        vis.style.fill = bF;
                        vis.style.stroke = bS;
                        vis.style.strokeWidth = "0.5";
                        tooltip.style.display = "none";
                    });
                })(pPath, hitPath, pTip, pbF, pbS, pbHF, pbHS);
                gExits.appendChild(pPath);
                gExits.appendChild(hitPath);
                pStack = sliceT;
            }

            // Name above bar
            var pNameLbl = svgEl("text", {
                x: sx(collX).toFixed(1), y: sy(pCollTop + 0.02).toFixed(1),
                "text-anchor": "middle", "dominant-baseline": "auto",
                "font-size": "14", "font-weight": "bold", fill: pendingColor,
                "pointer-events": "none",
            });
            pNameLbl.textContent = "Pending";
            gLabels.appendChild(pNameLbl);

            // Count label inside bar — keep collector labels readable in narrow bars.
            var pBarPx = sy(pCollBot) - sy(pCollTop);
            var pBarWpx = sx(collR) - sx(collL);
            var pTxtCol = textColorForBg(pendingColor);
            var pPctVal = total > 0 ? Math.round(totalPending / total * 100) : 0;
            if (pBarPx >= 18) {
                var pCntLbl = svgEl("text", {
                    x: sx(collX).toFixed(1),
                    y: sy((pCollTop + pCollBot) / 2).toFixed(1),
                    "text-anchor": "middle", "dominant-baseline": "central",
                    fill: pTxtCol, "pointer-events": "none",
                });
                if (pBarPx >= 38) {
                    var pCntLine = svgEl("tspan", {
                        x: sx(collX).toFixed(1), dy: "-0.15em",
                        "font-size": "13", "font-weight": "bold",
                    });
                    pCntLine.textContent = totalPending.toLocaleString();
                    var pPctLine = svgEl("tspan", {
                        x: sx(collX).toFixed(1), dy: "1.2em",
                        "font-size": "11", opacity: "0.9",
                    });
                    pPctLine.textContent = "(" + pPctVal + "%)";
                    pCntLbl.appendChild(pCntLine);
                    pCntLbl.appendChild(pPctLine);
                } else if (pBarWpx >= 64) {
                    pCntLbl.setAttribute("font-size", "11");
                    pCntLbl.setAttribute("font-weight", "bold");
                    pCntLbl.textContent = totalPending.toLocaleString() + " (" + pPctVal + "%)";
                } else {
                    pCntLbl.setAttribute("font-size", pBarPx >= 24 ? "12" : "11");
                    pCntLbl.setAttribute("font-weight", "bold");
                    pCntLbl.textContent = totalPending.toLocaleString();
                }
                gLabels.appendChild(pCntLbl);
            }

            collCursor = pCollBot - collSpc;
        }

        // ── Cancelled collector ──
        if (totalCancelled > 0) {
            var cCollTop = collCursor;
            var cCollH   = Math.min(0.06, Math.max(0.025, maxBarH * totalCancelled / maxCount));
            var cCollBot = cCollTop - cCollH;

            var cBarFill  = hexToRgba(cancelledColor, 0.85);
            var cBarHover = mixHexWithWhite(cancelledColor, 0.18);
            var cBarRect  = svgEl("rect", {
                x: sx(collL).toFixed(1), y: sy(cCollTop).toFixed(1),
                width: (sx(collR) - sx(collL)).toFixed(1),
                height: (sy(cCollBot) - sy(cCollTop)).toFixed(1),
                fill: cBarFill, stroke: cancelledColor,
                "stroke-width": "0.8", rx: "2",
                "class": "flow-gantt-stage",
                "data-base-fill": cBarFill, "data-base-stroke": cancelledColor,
                "data-base-stroke-width": "0.8",
                "data-hover-fill": cBarHover, "data-hover-stroke": cancelledColor,
                "data-hover-stroke-width": "1.6",
            });
            var cPctTotal = total > 0 ? (totalCancelled / total * 100).toFixed(1) : "0";
            var cBarTip = "<b>Cancelled / Unscheduled</b><br>"
                + totalCancelled.toLocaleString() + " patients (" + cPctTotal + "%)";
            for (var s = 0; s < exitSources.cancelled.length; s++) {
                var cSrcPct = total > 0 ? (exitSources.cancelled[s].count / total * 100).toFixed(1) : "0";
                cBarTip += "<br><span style='color:" + colors[exitSources.cancelled[s].idx]
                    + "'>&#9679;</span> " + exitSources.cancelled[s].count.toLocaleString()
                    + " from " + stages[exitSources.cancelled[s].idx] + " (" + cSrcPct + "%)";
            }
            attachHover(cBarRect, cBarTip, cancelledColor);
            gBars.appendChild(cBarRect);

            var cStack = cCollBot;  // bottom-up on collector
            for (var s = 0; s < exitSources.cancelled.length; s++) {
                var src    = exitSources.cancelled[s];
                var sliceH = cCollH * (src.count / totalCancelled);
                var sliceT = cStack + sliceH;  // top of this slice
                var dist   = collL - bars[src.idx].r;
                var sag    = 0.008 + dist * 0.012;
                var poly   = exitBezierBand(bars[src.idx].r, src.top, src.bot, collL, sliceT, cStack, sag, 36);
                var cbF = hexToRgba(cancelledColor, 0.12), cbS = hexToRgba(cancelledColor, 0.25);
                var cbHF = hexToRgba(cancelledColor, 0.22), cbHS = hexToRgba(cancelledColor, 0.42);
                var cPath = svgEl("path", {
                    d: polyToPath(poly), fill: cbF, stroke: cbS,
                    "stroke-width": "0.5",
                    "class": "flow-gantt-exit flow-gantt-exit-cancelled",
                    "data-base-fill": cbF, "data-base-stroke": cbS, "data-base-stroke-width": "0.5",
                    "data-hover-fill": cbHF, "data-hover-stroke": cbHS, "data-hover-stroke-width": "1.2",
                });
                var minNorm = 14 * (yHi - yLo) / drawH;
                var bandThick0 = src.top - src.bot;
                var bandThick1 = sliceT - cStack;
                var pad0 = Math.max(0, (minNorm - bandThick0) / 2);
                var pad1 = Math.max(0, (minNorm - bandThick1) / 2);
                var hitPoly = exitBezierBand(bars[src.idx].r, src.top + pad0, src.bot - pad0, collL, sliceT + pad1, cStack - pad1, sag, 36);
                var hitPath = svgEl("path", {
                    d: polyToPath(hitPoly), fill: "transparent", stroke: "none",
                    "pointer-events": "all", cursor: "pointer",
                });
                cPath.style.pointerEvents = "none";
                var cTip = "<b>" + stages[src.idx] + " &#8594; Cancelled/Unsched</b><br>"
                    + src.count.toLocaleString() + " patients"
                    + " (" + (total > 0 ? (src.count / total * 100).toFixed(1) : "0") + "%)";
                (function(vis, hit, tip, bF, bS, hF, hS) {
                    hit.addEventListener("mouseenter", function() {
                        vis.style.fill = hF;
                        vis.style.stroke = hS;
                        vis.style.strokeWidth = "1.2";
                        tooltip.innerHTML = tip;
                        tooltip.style.borderLeftColor = cancelledColor;
                        tooltip.style.display = "block";
                    });
                    hit.addEventListener("mousemove", function(e) {
                        var x = e.clientX + 14, y = e.clientY + 14;
                        var tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
                        if (x + tw > window.innerWidth - 10) x = e.clientX - tw - 14;
                        if (y + th > window.innerHeight - 10) y = e.clientY - th - 14;
                        if (y < 10) y = 10;
                        tooltip.style.left = x + "px";
                        tooltip.style.top = y + "px";
                    });
                    hit.addEventListener("mouseleave", function() {
                        vis.style.fill = bF;
                        vis.style.stroke = bS;
                        vis.style.strokeWidth = "0.5";
                        tooltip.style.display = "none";
                    });
                })(cPath, hitPath, cTip, cbF, cbS, cbHF, cbHS);
                gExits.appendChild(cPath);
                gExits.appendChild(hitPath);
                cStack = sliceT;
            }

            // Name above bar
            var cNameLbl = svgEl("text", {
                x: sx(collX).toFixed(1), y: sy(cCollTop + 0.02).toFixed(1),
                "text-anchor": "middle", "dominant-baseline": "auto",
                "font-size": "14", "font-weight": "bold", fill: cancelledColor,
                "pointer-events": "none",
            });
            cNameLbl.textContent = "Cancelled";
            gLabels.appendChild(cNameLbl);

            // Count label inside bar — keep collector labels readable in narrow bars.
            var cBarPx = sy(cCollBot) - sy(cCollTop);
            var cBarWpx = sx(collR) - sx(collL);
            var cTxtCol = textColorForBg(cancelledColor);
            var cPctVal = total > 0 ? Math.round(totalCancelled / total * 100) : 0;
            if (cBarPx >= 18) {
                var cCntLbl = svgEl("text", {
                    x: sx(collX).toFixed(1),
                    y: sy((cCollTop + cCollBot) / 2).toFixed(1),
                    "text-anchor": "middle", "dominant-baseline": "central",
                    fill: cTxtCol, "pointer-events": "none",
                });
                if (cBarPx >= 38) {
                    var cCntLine = svgEl("tspan", {
                        x: sx(collX).toFixed(1), dy: "-0.15em",
                        "font-size": "13", "font-weight": "bold",
                    });
                    cCntLine.textContent = totalCancelled.toLocaleString();
                    var cPctLine = svgEl("tspan", {
                        x: sx(collX).toFixed(1), dy: "1.2em",
                        "font-size": "11", opacity: "0.9",
                    });
                    cPctLine.textContent = "(" + cPctVal + "%)";
                    cCntLbl.appendChild(cCntLine);
                    cCntLbl.appendChild(cPctLine);
                } else if (cBarWpx >= 64) {
                    cCntLbl.setAttribute("font-size", "11");
                    cCntLbl.setAttribute("font-weight", "bold");
                    cCntLbl.textContent = totalCancelled.toLocaleString() + " (" + cPctVal + "%)";
                } else {
                    cCntLbl.setAttribute("font-size", cBarPx >= 24 ? "12" : "11");
                    cCntLbl.setAttribute("font-weight", "bold");
                    cCntLbl.textContent = totalCancelled.toLocaleString();
                }
                gLabels.appendChild(cCntLbl);
            }
        }

        // ─── 3. STAGE BARS ─────────────────────────────────────────────
        for (var i = 0; i < nStages; i++) {
            var bFill  = hexToRgba(colors[i], 0.88);
            var bHover = mixHexWithWhite(colors[i], 0.16);
            var bHoverStroke = mixHexWithWhite(colors[i], 0.05);

            var rect = svgEl("rect", {
                x: sx(bars[i].l).toFixed(1),
                y: sy(bars[i].top).toFixed(1),
                width: (sx(bars[i].r) - sx(bars[i].l)).toFixed(1),
                height: (sy(bars[i].bot) - sy(bars[i].top)).toFixed(1),
                fill: bFill,
                stroke: colors[i],
                "stroke-width": "0.8",
                rx: "2",
                "class": "flow-gantt-stage",
                "data-base-fill": bFill,
                "data-base-stroke": colors[i],
                "data-base-stroke-width": "0.8",
                "data-hover-fill": bHover,
                "data-hover-stroke": bHoverStroke,
                "data-hover-stroke-width": "1.6",
            });

            // Build bar tooltip — use small colored bullets for consistent styling
            var pct = total > 0 ? (counts[i] / total * 100).toFixed(1) : "0";
            var barTip = "<b>" + stages[i] + "</b><br>"
                + counts[i].toLocaleString() + " patients (" + pct + "% of total)";
            if (i > 0) {
                var prevPct = counts[i - 1] > 0
                    ? (counts[i] / counts[i - 1] * 100).toFixed(1) : "0";
                barTip += "<br>" + prevPct + "% from " + stages[i - 1];
            }
            if (i < nStages - 1) {
                barTip += "<br><span style='color:" + colors[i] + "'>\u25B6</span> "
                    + flows[i].toLocaleString() + " progressed (" + mDays[i] + "d " + aggLabel.toLowerCase()
                    + (aDays[i] != null ? " / " + aDays[i] + "d allotted" : "")
                    + (otPcts[i] != null ? " · " + otPcts[i] + "% on time" : "") + ")";
                var pi = (pending && pending[i]) || 0;
                var ci = (cancelled && cancelled[i]) || 0;
                if (pi > 0) barTip += "<br><span style='color:" + pendingColor + "'>\u25CF</span> "
                    + pi.toLocaleString() + " pending";
                if (ci > 0) barTip += "<br><span style='color:" + cancelledColor + "'>\u25CF</span> "
                    + ci.toLocaleString() + " cancelled/unsched";
            }
            if (showLoopbacks && loopbacks[i] > 0) barTip += "<br><span style='color:#9CA3AF'>\u21A9</span> "
                + loopbacks[i].toLocaleString() + " repeats";

            attachHover(rect, barTip, colors[i]);
            gBars.appendChild(rect);
        }

        // ─── 4. DAYS LABELS ON FLOW BANDS ────────────────────────────────

        for (var i = 0; i < nStages; i++) {
            // Stage name above bar
            var stageName = svgEl("text", {
                x: sx(bars[i].cx).toFixed(1),
                y: sy(bars[i].top + 0.022).toFixed(1),
                "text-anchor": "middle",
                "dominant-baseline": "auto",
                "font-size": "14",
                "font-weight": "bold",
                fill: colors[i],
                "pointer-events": "none",
            });
            stageName.textContent = stages[i];
            gLabels.appendChild(stageName);

            // Count + percentage centered inside bar — adaptive to height
            var pctVal = total > 0 ? Math.round(counts[i] / total * 100) : 0;
            var barTxtCol = textColorForBg(colors[i]);
            var barPx = sy(bars[i].bot) - sy(bars[i].top);
            if (barPx >= 28) {
                var countLabel = svgEl("text", {
                    x: sx(bars[i].cx).toFixed(1),
                    y: sy((bars[i].top + bars[i].bot) / 2).toFixed(1),
                    "text-anchor": "middle",
                    "dominant-baseline": "central",
                    fill: barTxtCol,
                    "pointer-events": "none",
                });
                if (barPx >= 38) {
                    var countLine = svgEl("tspan", {
                        x: sx(bars[i].cx).toFixed(1),
                        dy: "-0.15em",
                        "font-size": "13",
                        "font-weight": "bold",
                    });
                    countLine.textContent = counts[i].toLocaleString();
                    var pctLine = svgEl("tspan", {
                        x: sx(bars[i].cx).toFixed(1),
                        dy: "1.2em",
                        "font-size": "11",
                        opacity: "0.9",
                    });
                    pctLine.textContent = "(" + pctVal + "%)";
                    countLabel.appendChild(countLine);
                    countLabel.appendChild(pctLine);
                } else {
                    countLabel.setAttribute("font-size", "12");
                    countLabel.setAttribute("font-weight", "bold");
                    countLabel.textContent = counts[i].toLocaleString() + " (" + pctVal + "%)";
                }
                gLabels.appendChild(countLabel);
            }

            // Median days label centered on flow band
            // Format: "Xd / Yd" (actual / allotted) or just "Xd" if no allotted
            if (i < nStages - 1 && bandGeo[i]) {
                var bg = bandGeo[i];
                var midX = (bars[i].r + bars[i + 1].l) / 2;
                var bandMidY = ((bg.s0 + bg.s1) / 2 + (bg.t0 + bg.t1) / 2) / 2;

                var hasAllotted = aDays[i] != null;
                var overdue = hasAllotted && mDays[i] > aDays[i];
                var dtX = sx(midX), dtY = sy(bandMidY);
                var gapPx = sx(bars[i + 1].l) - sx(bars[i].r);
                var fillColor = overdue ? "#E53935" : darkenColor(colors[i], 0.65);

                // Two-line layout when gap is tight and we have allotted
                var twoLine = hasAllotted && gapPx < 70;
                if (twoLine) {
                    var bgW = Math.max((String(mDays[i]).length + 1) * 7.5 + 12, (String(aDays[i]).length + 2) * 7.5 + 12);
                    var bgH = 30;
                    gConnectors.appendChild(svgEl("rect", {
                        x: (dtX - bgW / 2).toFixed(1),
                        y: (dtY - bgH / 2).toFixed(1),
                        width: bgW.toFixed(1),
                        height: bgH.toFixed(1),
                        fill: "rgba(255,255,255,0.88)",
                        rx: "10",
                        "pointer-events": "none",
                    }));
                    var daysLabel = svgEl("text", {
                        x: dtX.toFixed(1),
                        y: dtY.toFixed(1),
                        "text-anchor": "middle",
                        "dominant-baseline": "central",
                        "font-size": "11",
                        "font-weight": "bold",
                        fill: fillColor,
                        "pointer-events": "none",
                    });
                    var line1 = svgEl("tspan", {x: dtX.toFixed(1), dy: "-0.5em"});
                    line1.textContent = mDays[i] + "d";
                    var line2 = svgEl("tspan", {x: dtX.toFixed(1), dy: "1.2em", "font-size": "10", "font-weight": "normal"});
                    line2.textContent = "/ " + aDays[i] + "d";
                    daysLabel.appendChild(line1);
                    daysLabel.appendChild(line2);
                    gConnectors.appendChild(daysLabel);
                } else {
                    var daysText = hasAllotted
                        ? mDays[i] + " / " + aDays[i] + "d"
                        : mDays[i] + "d";
                    var bgW = daysText.length * 7.5 + 12;
                    gConnectors.appendChild(svgEl("rect", {
                        x: (dtX - bgW / 2).toFixed(1),
                        y: (dtY - 10).toFixed(1),
                        width: bgW.toFixed(1),
                        height: "20",
                        fill: "rgba(255,255,255,0.88)",
                        rx: "10",
                        "pointer-events": "none",
                    }));
                    var daysLabel = svgEl("text", {
                        x: dtX.toFixed(1),
                        y: dtY.toFixed(1),
                        "text-anchor": "middle",
                        "dominant-baseline": "central",
                        "font-size": "12",
                        "font-weight": "bold",
                        fill: fillColor,
                        "pointer-events": "none",
                    });
                    daysLabel.textContent = daysText;
                    gConnectors.appendChild(daysLabel);
                }
            }
        }

        // ─── Total pipeline duration ────────────────────────────────────
        var totalDays = 0;
        for (var i = 0; i < mDays.length; i++) totalDays += mDays[i];
        totalDays = Math.round(totalDays * 10) / 10;
        var totalRowY = bars[0].top + (showLoopbacks ? 0.09 : 0.055);
        var totalMidX = (bars[0].cx + bars[nStages - 1].cx) / 2;

        var totalLabel = svgEl("text", {
            x: sx(totalMidX).toFixed(1),
            y: sy(totalRowY).toFixed(1),
            "text-anchor": "middle",
            "dominant-baseline": "auto",
            "font-size": "14",
            "font-weight": "bold",
            fill: "#4B5563",
            "pointer-events": "none",
        });
        totalLabel.textContent = "Total: " + totalDays + " days";
        gLabels.appendChild(totalLabel);

        // ─── 5. LOOPBACK FLOW BANDS ─────────────────────────────────────
        if (showLoopbacks && rawData.loopbackPairs && rawData.loopbackPairs.length > 0) {
            // Sort longest span first so wider arcs nest outside narrower ones
            var pairs = rawData.loopbackPairs.slice().sort(function(a, b) {
                return Math.abs(b.fromIdx - b.toIdx) - Math.abs(a.fromIdx - a.toIdx);
            });

            // Max loopback count for proportional thickness scaling
            var maxLbCount = 1;
            for (var p = 0; p < pairs.length; p++) {
                if (pairs[p].count > maxLbCount) maxLbCount = pairs[p].count;
            }

            // Track cumulative arc offset so bands stack without overlap
            var lbCursor = bars[0].top + 0.012;

            for (var p = 0; p < pairs.length; p++) {
                var pair = pairs[p];
                if (pair.count <= 0) continue;

                var fi = pair.fromIdx, ti = pair.toIdx;
                var fromX = bars[fi].cx;
                var toX = bars[ti].cx;
                var arcColor = colors[ti];

                // Proportional band thickness
                var minBand = 0.005;
                var maxBand = 0.025;
                var bandH = minBand + (pair.count / maxLbCount) * (maxBand - minBand);

                // Gentle arc above bars, stacking outward
                var peakY = lbCursor + bandH;
                lbCursor = peakY + 0.002;

                // Build filled bezier band arcing over the top
                var nPts = 40;
                var lbDx = toX - fromX;
                var cp1x = fromX + lbDx * 0.35;
                var cp2x = fromX + lbDx * 0.65;
                var y0 = bars[fi].top;
                var y1 = bars[ti].top;

                var lbXs = [], lbYtop = [], lbYbot = [];
                for (var q = 0; q <= nPts; q++) {
                    var t = q / nPts;
                    lbXs.push(cubic(t, fromX, cp1x, cp2x, toX));
                    lbYtop.push(cubic(t, y0, peakY, peakY, y1));
                    lbYbot.push(cubic(t, y0, peakY - bandH, peakY - bandH, y1));
                }
                var lbPoly = {
                    x: lbXs.concat(lbXs.slice().reverse()),
                    y: lbYtop.concat(lbYbot.slice().reverse()),
                };

                var lbFill = hexToRgba(arcColor, 0.18);
                var lbStroke = hexToRgba(arcColor, 0.35);
                var lbHoverFill = hexToRgba(arcColor, 0.30);
                var lbHoverStroke = hexToRgba(arcColor, 0.55);

                var lbPath = svgEl("path", {
                    d: polyToPath(lbPoly),
                    fill: lbFill,
                    stroke: lbStroke,
                    "stroke-width": "0.5",
                    "class": "flow-gantt-loopback",
                    "data-base-fill": lbFill,
                    "data-base-stroke": lbStroke,
                    "data-base-stroke-width": "0.5",
                    "data-hover-fill": lbHoverFill,
                    "data-hover-stroke": lbHoverStroke,
                    "data-hover-stroke-width": "1.2",
                });

                // Wider hit-area for thin bands
                var lbMinNorm = 14 * (yHi - yLo) / drawH;
                var lbPad = Math.max(0, (lbMinNorm - bandH) / 2);
                var hitYtop = [], hitYbot = [];
                for (var q = 0; q <= nPts; q++) {
                    var t = q / nPts;
                    hitYtop.push(cubic(t, y0 + lbPad, peakY + lbPad, peakY + lbPad, y1 + lbPad));
                    hitYbot.push(cubic(t, y0 - lbPad, peakY - bandH - lbPad, peakY - bandH - lbPad, y1 - lbPad));
                }
                var lbHitPoly = {
                    x: lbXs.concat(lbXs.slice().reverse()),
                    y: hitYtop.concat(hitYbot.slice().reverse()),
                };
                var lbHitPath = svgEl("path", {
                    d: polyToPath(lbHitPoly),
                    fill: "transparent",
                    stroke: "none",
                    "pointer-events": "all",
                    cursor: "pointer",
                });
                lbPath.style.pointerEvents = "none";

                var lbPct = total > 0 ? (pair.count / total * 100).toFixed(1) : "0";
                var lbTip = "<b>" + stages[fi] + " \u2192 " + stages[ti] + " (loopback)</b><br>"
                    + pair.count.toLocaleString() + " patients (" + lbPct + "%)";

                (function(vis, hit, tip, bF, bS, hF, hS, col) {
                    hit.addEventListener("mouseenter", function() {
                        vis.style.fill = hF;
                        vis.style.stroke = hS;
                        vis.style.strokeWidth = "1.2";
                        tooltip.innerHTML = tip;
                        tooltip.style.borderLeftColor = col;
                        tooltip.style.display = "block";
                    });
                    hit.addEventListener("mousemove", function(e) {
                        var x = e.clientX + 14, y = e.clientY + 14;
                        var tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
                        if (x + tw > window.innerWidth - 10) x = e.clientX - tw - 14;
                        if (y + th > window.innerHeight - 10) y = e.clientY - th - 14;
                        if (y < 10) y = 10;
                        tooltip.style.left = x + "px";
                        tooltip.style.top = y + "px";
                    });
                    hit.addEventListener("mouseleave", function() {
                        vis.style.fill = bF;
                        vis.style.stroke = bS;
                        vis.style.strokeWidth = "0.5";
                        tooltip.style.display = "none";
                    });
                })(lbPath, lbHitPath, lbTip, lbFill, lbStroke, lbHoverFill, lbHoverStroke, arcColor);

                gLoopbacks.appendChild(lbPath);
                gLoopbacks.appendChild(lbHitPath);
            }
        }

        // ─── Assemble SVG ──────────────────────────────────────────────
        svg.appendChild(gBands);
        svg.appendChild(gExits);
        svg.appendChild(gConnectors);
        svg.appendChild(gBars);
        svg.appendChild(gLoopbacks);
        svg.appendChild(gLabels);

        // Click SVG background to deselect
        svg.addEventListener("click", function(e) {
            if (e.target === svg) {
                container.__fgSelectedFlow = null;
                _updateBandSelection(svg, null);
                ["wf-flow-gantt-a", "wf-flow-gantt-b"].forEach(function(oid) {
                    var other = document.getElementById(oid);
                    if (other && other !== container) {
                        var oSvg = other.querySelector("svg");
                        if (oSvg) _updateBandSelection(oSvg, null);
                    }
                });
                if (window.dash_clientside && window.dash_clientside.set_props) {
                    window.dash_clientside.set_props("wf-store-selected-flow", {data: null});
                    window.dash_clientside.set_props("wf-b-store-selected-flow", {data: null});
                }
            }
        });

        container.appendChild(svg);

        // ─── ResizeObserver — re-render when container changes size ───
        // (only attach for the main container, not compare sub-containers)
        if (!pipelineLabel) {
            container.__fgData = rawData;
            container.__fgLoopbacks = showLoopbacks;
            container.__fgW = cw;
            container.__fgH = ch;

            if (window.ResizeObserver && !container.__fgRO) {
                var debounce;
                container.__fgRO = new ResizeObserver(function() {
                    var nw = container.clientWidth;
                    var nh = container.clientHeight;
                    if (nw && nh && (nw !== container.__fgW || nh !== container.__fgH)) {
                        clearTimeout(debounce);
                        debounce = setTimeout(function() {
                            window.dash_clientside.flowGantt.renderFlowGantt(
                                container.__fgData, container.__fgLoopbacks,
                                container.__fgDataB, container.__fgLoopbacksB,
                                container.__fgCompare
                            );
                        }, 150);
                    }
                });
                container.__fgRO.observe(container);
            }
        }

        return window.dash_clientside.no_update;
    },

    // ─── Distribution chart (histogram/density) driven by flow selection ──
    renderFlowDistribution: function(flowDetails, selectedFlow, distType, useKM, flowDetailsB, compareMode, aggA, aggB) {
        var font = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
        useKM = !!useKM;  // coerce to boolean
        // Use live toggle values (instant) over stale store aggFunc
        var statFunc = (aggA === "mean") ? "mean" : "median";
        var statLabel = statFunc === "mean" ? "Mean" : "Median";

        // Determine whether to display in hours (when median AND mean < 1 day)
        function resolveUnit(d) {
            var med = d.median, mn = d.mean;
            if (med != null && mn != null && med < 1 && mn < 1) {
                return {unit: "h", scale: 24, axisTitle: "Hours", suffix: "h"};
            }
            return {unit: "d", scale: 1, axisTitle: "Days", suffix: "d"};
        }

        function emptyFig(msg) {
            return {
                data: [],
                layout: {
                    font: {family: font, size: 12},
                    margin: {l: 48, r: 16, t: 16, b: 48},
                    plot_bgcolor: "#FFFFFF", paper_bgcolor: "#FFFFFF",
                    xaxis: {visible: false}, yaxis: {visible: false},
                    autosize: true,
                    annotations: [{
                        text: msg || "No data", showarrow: false,
                        xref: "paper", yref: "paper", x: 0.5, y: 0.5,
                        font: {size: 14, color: "#9CA3AF"}
                    }]
                }
            };
        }

        // Pick the primary stat value: KM-adjusted when toggle is on and available
        function pickStat(d) {
            var naive = statFunc === "mean" ? d.mean : d.median;
            if (useKM && d.kmMedian != null) return d.kmMedian;
            return naive;
        }
        function pickStatLabel(d) {
            if (useKM && d.kmMedian != null) return "KM " + statLabel;
            return statLabel;
        }

        // ── Compare mode: overlay B dataset traces onto A figure ──
        function addBOverlay(figAndTitle, bDetails) {
            if (!compareMode || !bDetails) return figAndTitle;
            var fig = figAndTitle[0], title = figAndTitle[1];
            var bObj;
            if (selectedFlow === null || selectedFlow === undefined || selectedFlow < 0) {
                bObj = bDetails.total;
            } else {
                bObj = bDetails.transitions ? bDetails.transitions[selectedFlow] : null;
            }
            if (!bObj || !bObj.days || bObj.days.length === 0) return figAndTitle;

            // B may have its own agg function selection (independent of A)
            var bStatFunc = (aggB === "mean") ? "mean" : "median";
            var bStatLabelText = bStatFunc === "mean" ? "Mean" : "Median";
            function pickBStat(d) {
                var naive = bStatFunc === "mean" ? d.mean : d.median;
                if (useKM && d.kmMedian != null) return d.kmMedian;
                return naive;
            }
            function pickBStatLabel(d) {
                if (useKM && d.kmMedian != null) return "KM " + bStatLabelText;
                return bStatLabelText;
            }

            var bU = resolveUnit(bObj);
            var bStatVal = pickBStat(bObj);
            var bStatLbl = pickBStatLabel(bObj);
            var bDisp = bU.scale === 1 ? (Math.round(bStatVal * 10) / 10) : Math.round(bStatVal * bU.scale);
            var color = bObj.color; // same stage color — B distinguished by dash/opacity

            // B stat line (dotted)
            fig.layout.shapes.push({
                type: "line", x0: bDisp, x1: bDisp, y0: 0, y1: 1,
                yref: "paper", line: {color: color, width: 1.5, dash: "dot"}
            });
            // In compare mode, label lines with just the letter at same height.
            // Jitter horizontally if A and B values are close enough to overlap.
            var labelY = 1.06;
            var bLabelX = bDisp;
            var bAnchor = "center";
            if (fig.layout.annotations.length > 0) {
                var a0 = fig.layout.annotations[0];
                if (a0.xref === "x") {
                    var aDisp = a0.x;
                    a0.text = "A";
                    a0.font.weight = 700;
                    // Check overlap: if A and B are within 5% of the x-axis range, jitter
                    var xRange = fig.layout.xaxis && fig.layout.xaxis.range
                        ? (fig.layout.xaxis.range[1] - fig.layout.xaxis.range[0])
                        : Math.max(Math.abs(aDisp), Math.abs(bDisp)) * 2 || 1;
                    var proximity = Math.abs(aDisp - bDisp) / xRange;
                    if (proximity < 0.02) {
                        // Jitter: push A left and B right of the pair
                        var nudge = xRange * 0.012;
                        a0.x = Math.min(aDisp, bDisp) - nudge;
                        a0.xanchor = "right";
                        bLabelX = Math.max(aDisp, bDisp) + nudge;
                        bAnchor = "left";
                    }
                }
            }
            fig.layout.annotations.push({
                x: bLabelX, y: labelY, yref: "paper", xref: "x",
                text: "B", xanchor: bAnchor,
                showarrow: false, font: {size: 11, color: color, family: font, weight: 700},
            });

            // B trace — dashed/lighter version of A
            if (distType === "density" && bObj.density) {
                var bDX = bU.scale === 1 ? bObj.density.x : bObj.density.x.map(function(v) { return v * bU.scale; });
                var bDY = bU.scale === 1 ? bObj.density.y : bObj.density.y.map(function(v) { return v / bU.scale; });
                fig.data.push({
                    type: "scatter", mode: "lines",
                    x: bDX, y: bDY, fill: "tozeroy",
                    line: {color: color, width: 2, dash: "dash"},
                    fillcolor: "rgba(255,255,255,0.6)", name: "Dataset B",
                    hovertemplate: bU.axisTitle + ": %{x:.1f}<br>Density: %{y:.4f}<extra>B</extra>",
                });
            } else {
                var bHist = bU.scale === 1 ? bObj.days.map(function(v) { return Math.round(v); }) : bObj.days.map(function(v) { return Math.round(v * bU.scale); });
                fig.data.push({
                    type: "histogram", x: bHist,
                    marker: {color: "rgba(255,255,255,0.6)",
                             line: {color: color, width: 1.5},
                             pattern: {shape: "/", fgcolor: (typeof hexToRgba === "function") ? hexToRgba(color, 0.4) : color, solidity: 0.25}},
                    xbins: {size: 1}, name: "Dataset B",
                    hovertemplate: bU.axisTitle + ": %{x}<br>Count: %{y}<extra>B</extra>",
                });
                fig.layout.barmode = "overlay";
            }

            // Legend + naming
            fig.data[0].name = "Dataset A";
            fig.layout.showlegend = true;
            fig.layout.legend = {orientation: "h", y: 1.02, x: 0, xanchor: "left", yanchor: "bottom"};

            // Label existing bottom annotation as A:, add B stats row
            for (var i = 0; i < fig.layout.annotations.length; i++) {
                var ann = fig.layout.annotations[i];
                if (ann.xref === "paper" && ann.yref === "paper" && ann.y < 0) {
                    ann.text = "A: " + ann.text; break;
                }
            }
            var bAltL = bStatFunc === "mean" ? "Median" : "Mean";
            var bAltV = bStatFunc === "mean" ? bObj.median : bObj.mean;
            var bAltDisp = bU.scale === 1 ? (Math.round(bAltV * 10) / 10) : Math.round(bAltV * bU.scale);
            var bP25 = bU.scale === 1 ? (Math.round(bObj.p25 * 10) / 10) : Math.round(bObj.p25 * bU.scale);
            var bP75 = bU.scale === 1 ? (Math.round(bObj.p75 * 10) / 10) : Math.round(bObj.p75 * bU.scale);
            fig.layout.annotations.push({
                x: 0.5, y: -0.22, xref: "paper", yref: "paper",
                text: "B: n=" + bObj.n + (bObj.nCensored ? " (+" + bObj.nCensored + " in progress)" : "") + "  " + bAltL + ": " + bAltDisp + bU.suffix + "  (IQR: " + bP25 + "\u2013" + bP75 + bU.suffix + ")",
                showarrow: false, font: {size: 11, color: "#4B5563", family: font},
            });
            fig.layout.margin.b = 72;
            title = title + " (Compare)";
            return [fig, title];
        }

        if (!flowDetails || !flowDetails.transitions) {
            return [emptyFig("No flow data"), "Stage Duration (days)"];
        }

        var transitions = flowDetails.transitions;

        // No selection → show total pipeline (Exam → Treatment) distribution
        if (selectedFlow === null || selectedFlow === undefined || selectedFlow < 0) {
            var tot = flowDetails.total;
            if (!tot || !tot.days || tot.days.length === 0) {
                return [emptyFig("No total pipeline data"), "Total Pipeline Duration"];
            }
            var tTitle = "Total Pipeline Duration";
            var tStatVal = pickStat(tot);
            var tStatLbl = pickStatLabel(tot);
            var tAltLabel = statFunc === "mean" ? "Median" : "Mean";
            var tAltVal = statFunc === "mean" ? tot.median : tot.mean;
            var tu = resolveUnit(tot);
            var r1 = function(v) { return Math.round(v * 10) / 10; };  // 1 decimal
            var tStatDisp = tu.scale === 1 ? r1(tStatVal) : Math.round(tStatVal * tu.scale);
            var tAltDisp = tu.scale === 1 ? r1(tAltVal) : Math.round(tAltVal * tu.scale);
            var tP25 = tu.scale === 1 ? r1(tot.p25) : Math.round(tot.p25 * tu.scale);
            var tP75 = tu.scale === 1 ? r1(tot.p75) : Math.round(tot.p75 * tu.scale);
            var tShapes = [{
                type: "line", x0: tStatDisp, x1: tStatDisp, y0: 0, y1: 1,
                yref: "paper", line: {color: tot.color, width: 2, dash: "dash"}
            }];
            var tAnnots = [
                {
                    x: tStatDisp, y: 1.06, yref: "paper", xref: "x",
                    text: tStatLbl + ": " + tStatDisp + tu.suffix,
                    showarrow: false, font: {size: 11, color: tot.color, family: font},
                },
                {
                    x: 0.5, y: -0.15, xref: "paper", yref: "paper",
                    text: "n=" + tot.n + (tot.nCensored ? " (+" + tot.nCensored + " in progress)" : "") + "  " + tAltLabel + ": " + tAltDisp + tu.suffix + "  (IQR: " + tP25 + "\u2013" + tP75 + tu.suffix + ")",
                    showarrow: false, font: {size: 11, color: "#4B5563", family: font},
                }
            ];
            var tLay = {
                font: {family: font, size: 12},
                margin: {l: 48, r: 16, t: 32, b: 48},
                plot_bgcolor: "#FFFFFF", paper_bgcolor: "#FFFFFF",
                xaxis: {showgrid: false, title: tu.axisTitle, autorange: true},
                yaxis: {gridcolor: "#F0F0F0", gridwidth: 1},
                autosize: true, showlegend: false, hovermode: "closest",
                shapes: tShapes, annotations: tAnnots,
                datarevision: (useKM ? "km" : "naive") + distType + (compareMode ? "cmp" : "") + Date.now(),
            };
            if (distType === "density") {
                var tDensityX = tu.scale === 1 ? tot.density.x : tot.density.x.map(function(v) { return v * tu.scale; });
                var tDensityY = tu.scale === 1 ? tot.density.y : tot.density.y.map(function(v) { return v / tu.scale; });
                var tRgba = (typeof hexToRgba === "function") ? hexToRgba(tot.color, 0.2) : tot.color;
                tLay.yaxis = {gridcolor: "#F0F0F0", gridwidth: 1, title: "Density"};
                return addBOverlay([{
                    data: [{
                        type: "scatter", mode: "lines",
                        x: tDensityX, y: tDensityY,
                        fill: "tozeroy",
                        line: {color: tot.color, width: 2},
                        fillcolor: tRgba,
                        hovertemplate: tu.axisTitle + ": %{x:.1f}<br>Density: %{y:.4f}<extra></extra>",
                    }],
                    layout: tLay
                }, tTitle], flowDetailsB);
            }
            var tHistDays = tu.scale === 1 ? tot.days.map(function(v) { return Math.round(v); }) : tot.days.map(function(v) { return Math.round(v * tu.scale); });
            var tRgbaH = (typeof hexToRgba === "function") ? hexToRgba(tot.color, 0.7) : tot.color;
            tLay.yaxis = {gridcolor: "#F0F0F0", gridwidth: 1, title: "Patients"};
            var tRange = Math.max.apply(null, tHistDays) - Math.min.apply(null, tHistDays);
            if (tRange <= 15) tLay.xaxis.dtick = 1;
            else if (tRange <= 30) tLay.xaxis.dtick = 2;
            tLay.xaxis.tickangle = 0;
            return addBOverlay([{
                data: [{
                    type: "histogram", x: tHistDays,
                    marker: {color: tRgbaH, line: {color: tot.color, width: 1}},
                    xbins: {size: 1},
                    hovertemplate: tu.axisTitle + ": %{x}<br>Count: %{y}<extra></extra>",
                }],
                layout: tLay
            }, tTitle], flowDetailsB);
        }

        // Selected flow → histogram or density
        var t = transitions[selectedFlow];
        if (!t || !t.days || t.days.length === 0) {
            return [emptyFig("No data for this transition"), t ? t.label : ""];
        }

        var title = t.label + " Duration";
        var sVal = pickStat(t);
        var sLbl = pickStatLabel(t);
        var altL = statFunc === "mean" ? "Median" : "Mean";
        var altV = statFunc === "mean" ? t.median : t.mean;
        var u = resolveUnit(t);
        var r1 = function(v) { return Math.round(v * 10) / 10; };  // 1 decimal
        var sDisp = u.scale === 1 ? r1(sVal) : Math.round(sVal * u.scale);
        var altDisp = u.scale === 1 ? r1(altV) : Math.round(altV * u.scale);
        var uP25 = u.scale === 1 ? r1(t.p25) : Math.round(t.p25 * u.scale);
        var uP75 = u.scale === 1 ? r1(t.p75) : Math.round(t.p75 * u.scale);
        var shapes = [{
            type: "line", x0: sDisp, x1: sDisp, y0: 0, y1: 1,
            yref: "paper", line: {color: t.color, width: 2, dash: "dash"}
        }];
        var annots = [
            {
                x: sDisp, y: 1.06, yref: "paper", xref: "x",
                text: sLbl + ": " + sDisp + u.suffix,
                showarrow: false, font: {size: 11, color: t.color, family: font},
            },
            {
                x: 0.5, y: -0.17, xref: "paper", yref: "paper",
                text: "n=" + t.n + (t.nCensored ? " (+" + t.nCensored + " in progress)" : "") + "  " + altL + ": " + altDisp + u.suffix + "  (IQR: " + uP25 + "–" + uP75 + u.suffix + ")",
                showarrow: false, font: {size: 11, color: "#4B5563", family: font},
            }
        ];

        var baseLay = {
            font: {family: font, size: 12},
            margin: {l: 48, r: 16, t: 32, b: 48},
            plot_bgcolor: "#FFFFFF", paper_bgcolor: "#FFFFFF",
            xaxis: {showgrid: false, title: u.axisTitle, autorange: true},
            yaxis: {gridcolor: "#F0F0F0", gridwidth: 1},
            autosize: true, showlegend: false, hovermode: "closest",
            shapes: shapes, annotations: annots,
            datarevision: (useKM ? "km" : "naive") + distType + selectedFlow + (compareMode ? "cmp" : "") + Date.now(),
        };

        if (distType === "density") {
            var densityX = u.scale === 1 ? t.density.x : t.density.x.map(function(v) { return v * u.scale; });
            var densityY = u.scale === 1 ? t.density.y : t.density.y.map(function(v) { return v / u.scale; });
            var rgba = (typeof hexToRgba === "function") ? hexToRgba(t.color, 0.2) : t.color;
            baseLay.yaxis = {gridcolor: "#F0F0F0", gridwidth: 1, title: "Density"};
            return addBOverlay([{
                data: [{
                    type: "scatter", mode: "lines",
                    x: densityX, y: densityY,
                    fill: "tozeroy",
                    line: {color: t.color, width: 2},
                    fillcolor: rgba,
                    hovertemplate: u.axisTitle + ": %{x:.1f}<br>Density: %{y:.4f}<extra></extra>",
                }],
                layout: baseLay
            }, title], flowDetailsB);
        }

        // histogram — integer bins (days or hours)
        var histVals = u.scale === 1 ? t.days.map(function(v) { return Math.round(v); }) : t.days.map(function(v) { return Math.round(v * u.scale); });
        var rgbaH = (typeof hexToRgba === "function") ? hexToRgba(t.color, 0.7) : t.color;
        baseLay.yaxis = {gridcolor: "#F0F0F0", gridwidth: 1, title: "Patients"};
        var hRange = Math.max.apply(null, histVals) - Math.min.apply(null, histVals);
        if (hRange <= 15) baseLay.xaxis.dtick = 1;
        else if (hRange <= 30) baseLay.xaxis.dtick = 2;
        baseLay.xaxis.tickangle = 0;
        return addBOverlay([{
            data: [{
                type: "histogram", x: histVals,
                marker: {color: rgbaH, line: {color: t.color, width: 1}},
                xbins: {size: 1},
                hovertemplate: u.axisTitle + ": %{x}<br>Count: %{y}<extra></extra>",
            }],
            layout: baseLay
        }, title], flowDetailsB);
    },

    // ─── Trend chart driven by flow selection ────────────────────────────
    renderFlowTrend: function(flowDetails, selectedFlow, trendData, smooth, chartType, agg, useKM, flowDetailsB, trendDataB, compareMode, aggToggleA, aggToggleB) {
        var font = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
        agg = agg || "M";
        var aggLabels = {D: "daily", W: "weekly", M: "monthly"};
        var aggLabel = aggLabels[agg] || "monthly";

        function movingAvg(vals, win) {
            if (!win || win <= 1) return vals;
            var out = [];
            for (var i = 0; i < vals.length; i++) {
                var s = Math.max(0, i - Math.floor(win / 2));
                var e = Math.min(vals.length, i + Math.ceil(win / 2));
                var sum = 0, cnt = 0;
                for (var j = s; j < e; j++) {
                    if (vals[j] != null) { sum += vals[j]; cnt++; }
                }
                out.push(cnt > 0 ? sum / cnt : null);
            }
            return out;
        }

        function emptyFig(msg) {
            return {
                data: [],
                layout: {
                    font: {family: font, size: 12},
                    margin: {l: 48, r: 16, t: 16, b: 48},
                    plot_bgcolor: "#FFFFFF", paper_bgcolor: "#FFFFFF",
                    xaxis: {visible: false}, yaxis: {visible: false},
                    autosize: true,
                    annotations: [{
                        text: msg || "No data", showarrow: false,
                        xref: "paper", yref: "paper", x: 0.5, y: 0.5,
                        font: {size: 14, color: "#9CA3AF"}
                    }]
                }
            };
        }

        // Resolve trend data from trendByAgg (new) or trend (legacy fallback)
        function getTrend(obj) {
            if (obj.trendByAgg && obj.trendByAgg[agg]) return obj.trendByAgg[agg];
            if (obj.trend) return obj.trend;
            return null;
        }

        // Determine central tendency from live toggle values (instant, no server round-trip)
        var statFunc = (aggToggleA === "mean") ? "mean" : "median";
        var statLabel = statFunc === "mean" ? "Mean" : "Median";

        // Returns an array of traces. Splits into solid (mature) and dashed
        // (immature) segments when completion rate data is available.
        function buildTraces(tData, name, color, overrideStatFunc) {
            var sf = overrideStatFunc || statFunc;
            // When KM toggle is on, use kmMedians (filter out nulls at edges)
            var baseVals = (sf === "mean" && tData.means) ? tData.means : tData.medians;
            var rawVals = (useKM && tData.kmMedians) ? tData.kmMedians : baseVals;
            // Filter out leading/trailing nulls when using KM
            var startIdx = 0, endIdx = rawVals.length;
            if (useKM && tData.kmMedians) {
                while (startIdx < endIdx && rawVals[startIdx] == null) startIdx++;
                while (endIdx > startIdx && rawVals[endIdx - 1] == null) endIdx--;
            }
            var slicedVals = rawVals.slice(startIdx, endIdx);
            var vals = (smooth > 1 && chartType !== "bar") ? movingAvg(slicedVals, smooth) : slicedVals;
            // Slice all parallel arrays to match
            tData = Object.assign({}, tData, {
                dates: tData.dates.slice(startIdx, endIdx),
                completionRates: (tData.completionRates || []).slice(startIdx, endIdx),
                counts: (tData.counts || []).slice(startIdx, endIdx),
            });
            var rates = tData.completionRates || [];
            var counts = tData.counts || [];

            // Build customdata [count, completionPct] for hover
            var customdata = [];
            for (var i = 0; i < vals.length; i++) {
                customdata.push([
                    counts[i] || 0,
                    rates[i] != null ? Math.round(rates[i] * 100) : 100
                ]);
            }
            var hoverTpl = "%{y:.1f} days  · n=%{customdata[0]}  · %{customdata[1]}% complete<extra>" + name + "</extra>";

            // Find maturity cutoff: last index with completion >= 50%
            // Skip when KM is on — KM already corrects for censoring
            var MATURE_THRESHOLD = 0.5;
            var cutoffIdx = vals.length; // default: all mature
            if (!useKM && rates.length > 0) {
                // Walk backward to find last mature point
                cutoffIdx = 0;
                for (var i = vals.length - 1; i >= 0; i--) {
                    if (rates[i] >= MATURE_THRESHOLD) {
                        cutoffIdx = i + 1;
                        break;
                    }
                }
            }

            if (chartType === "bar") {
                // For bars, tint immature bars lighter
                var barColors = [];
                for (var i = 0; i < vals.length; i++) {
                    barColors.push(i < cutoffIdx
                        ? ((typeof hexToRgba === "function") ? hexToRgba(color, 0.7) : color)
                        : ((typeof hexToRgba === "function") ? hexToRgba(color, 0.25) : color));
                }
                return [{
                    x: tData.dates, y: vals,
                    name: name, type: "bar",
                    marker: {color: barColors, line: {color: color, width: 1}},
                    customdata: customdata,
                    hovertemplate: hoverTpl,
                }];
            }

            // Single trace with per-point marker styling to show maturity.
            // Immature points get open circles + larger size; the line
            // is solid throughout (Plotly doesn't support per-segment dash
            // on a single trace, so we overlay a dashed line for the tail).
            var markerSizes = [], markerSymbols = [], markerColors = [], markerLineW = [];
            for (var i = 0; i < vals.length; i++) {
                if (i < cutoffIdx) {
                    markerSizes.push(4);
                    markerSymbols.push("circle");
                    markerColors.push(color);
                    markerLineW.push(0);
                } else {
                    markerSizes.push(6);
                    markerSymbols.push("circle-open");
                    markerColors.push(color);
                    markerLineW.push(2);
                }
            }
            var mode = (chartType === "area") ? "lines+markers" : "lines+markers";
            var trace = {
                x: tData.dates, y: vals,
                name: name, mode: mode,
                line: {color: color, width: 2},
                marker: {size: markerSizes, symbol: markerSymbols, color: markerColors,
                         line: {color: color, width: markerLineW}},
                customdata: customdata,
                hovertemplate: hoverTpl,
            };
            if (chartType === "area") {
                trace.fill = "tozeroy";
                trace.fillcolor = (typeof hexToRgba === "function") ? hexToRgba(color, 0.15) : color;
            }
            var traces = [trace];
            // Overlay a dashed line on the immature segment for visual distinction
            if (cutoffIdx < vals.length && cutoffIdx > 0) {
                var dashStart = cutoffIdx - 1; // overlap one point for continuity
                traces.push({
                    x: tData.dates.slice(dashStart), y: vals.slice(dashStart),
                    mode: "lines", line: {color: color, width: 2, dash: "dot"},
                    hoverinfo: "skip", showlegend: false,
                });
                // Hide the solid line in the immature region by overwriting with white
                // then dashed — not needed since the dashed overlay is on top.
            }
            return traces;
        }

        var baseLay = {
            font: {family: font, size: 12},
            margin: {l: 48, r: 16, t: 32, b: 48},
            plot_bgcolor: "#FFFFFF", paper_bgcolor: "#FFFFFF",
            xaxis: {showgrid: false},
            yaxis: {gridcolor: "#F0F0F0", gridwidth: 1, title: statLabel + " Days"},
            autosize: true,
            showlegend: false,
            hovermode: "x unified",
        };
        if (chartType === "bar") {
            baseLay.bargap = 0.15;
        }
        var legendHidden = {fontSize: "11px", color: "#6B7280", display: "none", cursor: "help"};
        function legendStyle(show, c) {
            if (!show) return legendHidden;
            return {fontSize: "11px", color: c || "#6B7280", display: "block", cursor: "help"};
        }

        // ── Compare mode: overlay B dataset trend traces ──
        function addBTrend(result, bFlowDetails, bTrendSrc) {
            if (!compareMode || !bFlowDetails) return result;
            var fig = result[0], title = result[1], legStyle = result[2];
            // Get B data object matching current selection
            var bObj, bTrend;
            if (selectedFlow === null || selectedFlow === undefined || selectedFlow < 0) {
                bObj = bFlowDetails.total;
            } else {
                bObj = (bFlowDetails.transitions || [])[selectedFlow];
            }
            if (!bObj) return result;
            bTrend = getTrend(bObj);
            if (!bTrend || !bTrend.dates || bTrend.dates.length === 0) return result;

            var bStatFunc = (aggToggleB === "mean") ? "mean" : "median";
            var bTraces = buildTraces(bTrend, "Dataset B", bObj.color, bStatFunc);
            // Post-process B traces: dashed lines, open markers
            for (var i = 0; i < bTraces.length; i++) {
                var tr = bTraces[i];
                if (tr.line) {
                    tr.line.dash = tr.line.dash === "dot" ? "dashdot" : "dash";
                }
                if (tr.marker && tr.marker.symbol) {
                    // Make all markers open circles for B
                    if (Array.isArray(tr.marker.symbol)) {
                        for (var j = 0; j < tr.marker.symbol.length; j++) {
                            tr.marker.symbol[j] = "circle-open";
                        }
                        // Ensure line width on all markers
                        if (Array.isArray(tr.marker.line && tr.marker.line.width)) {
                            for (var j = 0; j < tr.marker.line.width.length; j++) {
                                tr.marker.line.width[j] = 1.5;
                            }
                        }
                    }
                }
                if (tr.fill === "tozeroy" && tr.fillcolor) {
                    // Stripe pattern fill for B
                    tr.fillcolor = "rgba(0,0,0,0)";
                    tr.fillpattern = {shape: "/", fgcolor: (typeof hexToRgba === "function") ? hexToRgba(bObj.color, 0.25) : tr.fillcolor, solidity: 0.3};
                }
                if (tr.type === "bar" && tr.marker) {
                    // Lighter bars for B
                    if (Array.isArray(tr.marker.color)) {
                        tr.marker.color = tr.marker.color.map(function(c) {
                            return (typeof hexToRgba === "function") ? hexToRgba(bObj.color, 0.25) : c;
                        });
                    }
                    tr.marker.pattern = {shape: "/", fgcolor: bObj.color, solidity: 0.3};
                }
                tr.legendgroup = "B";
            }
            // Label A traces
            for (var i = 0; i < fig.data.length; i++) {
                fig.data[i].legendgroup = "A";
            }
            fig.data = fig.data.concat(bTraces);

            // Update y-axis label if A and B use different agg functions
            var bStatLabel = bStatFunc === "mean" ? "Mean" : "Median";
            if (bStatFunc !== statFunc) {
                fig.layout.yaxis.title = statLabel + " / " + bStatLabel + " Days";
            }

            // Show legend with A/B labels
            fig.layout.showlegend = true;
            fig.layout.legend = {orientation: "h", y: 1.02, x: 0, xanchor: "left", yanchor: "bottom"};
            // Rename first A trace for legend
            if (fig.data.length > 0 && fig.data[0].name) {
                fig.data[0].name = "Dataset A";
            }
            title = title + " (Compare)";
            return [fig, title, legStyle];
        }

        // No selection → show total pipeline trend (Exam → Treatment)
        if (selectedFlow === null || selectedFlow === undefined || selectedFlow < 0) {
            var tot = flowDetails && flowDetails.total;
            if (!tot) return [emptyFig("No total pipeline data"), "Total Pipeline Trend (" + aggLabel + " " + statLabel.toLowerCase() + ")", legendHidden];
            var tTrend = getTrend(tot);
            if (!tTrend || !tTrend.dates || tTrend.dates.length === 0) {
                return [emptyFig("No total pipeline data"), "Total Pipeline Trend (" + aggLabel + " " + statLabel.toLowerCase() + ")", legendHidden];
            }
            var kmSuffix = useKM ? ", KM adjusted" : "";
            var tTraces = buildTraces(tTrend, "Total Pipeline", tot.color);
            var hasImm = !useKM && (tTrend.completionRates || []).some(function(r) { return r < 0.5; });
            return addBTrend([{data: tTraces, layout: baseLay}, "Total Pipeline Trend (" + aggLabel + " " + statLabel.toLowerCase() + kmSuffix + ")", legendStyle(hasImm, tot.color)], flowDetailsB, trendDataB);
        }

        // Selected flow → single-transition trend
        if (!flowDetails || !flowDetails.transitions) {
            return [emptyFig("No flow data"), "", legendHidden];
        }
        var t = flowDetails.transitions[selectedFlow];
        if (!t) return [emptyFig("No trend data"), "", legendHidden];
        var selTrend = getTrend(t);
        if (!selTrend || !selTrend.dates || selTrend.dates.length === 0) {
            return [emptyFig("No trend data"), t.label + " Trend", legendHidden];
        }

        var kmSuffix2 = useKM ? ", KM adjusted" : "";
        var title = t.label + " Trend (" + aggLabel + " " + statLabel.toLowerCase() + kmSuffix2 + ")";
        var traces = buildTraces(selTrend, t.label, t.color);
        var hasImm2 = !useKM && (selTrend.completionRates || []).some(function(r) { return r < 0.5; });
        return addBTrend([{data: traces, layout: baseLay}, title, legendStyle(hasImm2, t.color)], flowDetailsB, trendDataB);
    }
};

// ─── Date Slider Helpers ─────────────────────────────────────────────────
(function() {
    var BASE = 2014;
    var MO = ["Jan","Feb","Mar","Apr","May","Jun",
              "Jul","Aug","Sep","Oct","Nov","Dec"];
    function fmtIdx(idx) {
        return MO[idx % 12] + " " + (BASE + Math.floor(idx / 12));
    }

    // Rewrite slider thumb labels from raw index → "Mon YYYY"
    var SLIDER_IDS = ["wf-date-slider", "wf-b-date-slider"];
    var observer = new MutationObserver(function() {
        SLIDER_IDS.forEach(function(sid) {
            var el = document.getElementById(sid);
            if (!el) return;
            el.querySelectorAll(".mantine-Slider-label").forEach(function(lbl) {
                var n = parseInt(lbl.textContent, 10);
                if (!isNaN(n) && n >= 0 && lbl.textContent === String(n)) {
                    lbl.textContent = fmtIdx(n);
                }
            });
        });
    });
    document.addEventListener("DOMContentLoaded", function() {
        observer.observe(document.body,
            {childList: true, subtree: true, characterData: true});
    });

    // Clientside callback namespace
    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.dateSlider = {
        /**
         * syncSlider: Slider → DatePicker dates + label text.
         * Returns [startDate, endDate, labelText].
         * Uses State of current datepicker values to break update loops.
         */
        syncSlider: function(sliderVal, curStart, curEnd) {
            if (!sliderVal || sliderVal.length !== 2) {
                return [window.dash_clientside.no_update,
                        window.dash_clientside.no_update, ""];
            }
            var label = fmtIdx(sliderVal[0]) + "  \u2014  " + fmtIdx(sliderVal[1]);

            // Compute ISO date strings from slider indices
            var sYear = BASE + Math.floor(sliderVal[0] / 12);
            var sMonth = sliderVal[0] % 12 + 1;
            var startDate = sYear + "-" + String(sMonth).padStart(2, "0") + "-01";

            var eYear = BASE + Math.floor(sliderVal[1] / 12);
            var eMonth = sliderVal[1] % 12 + 1;
            // End of month, capped at today
            var lastDay = new Date(eYear, eMonth, 0).getDate();
            var endDate = eYear + "-" + String(eMonth).padStart(2, "0") + "-"
                        + String(lastDay).padStart(2, "0");
            var today = new Date();
            var todayStr = today.getFullYear() + "-"
                + String(today.getMonth() + 1).padStart(2, "0") + "-"
                + String(today.getDate()).padStart(2, "0");
            if (endDate > todayStr) { endDate = todayStr; }

            // Skip datepicker update if already matching (break loop)
            if (curStart === startDate && curEnd === endDate) {
                return [window.dash_clientside.no_update,
                        window.dash_clientside.no_update, label];
            }
            return [startDate, endDate, label];
        }
    };
})();

// ─── Chip Dropdown Toggle (click-to-open, click-outside-to-close) ────────
(function() {
    var pairs = [
        ["wf-physician-trigger",   "wf-physician-panel"],
        ["wf-technique-trigger",   "wf-technique-panel"],
        ["wf-body-system-trigger", "wf-body-system-panel"],
        ["wf-outlier-trigger",     "wf-outlier-panel"],
        ["wf-b-physician-trigger",   "wf-b-physician-panel"],
        ["wf-b-technique-trigger",   "wf-b-technique-panel"],
        ["wf-b-body-system-trigger", "wf-b-body-system-panel"],
        ["wf-b-outlier-trigger",     "wf-b-outlier-panel"],
        ["cv-physician-trigger",   "cv-physician-panel"],
        ["cv-body-system-trigger", "cv-body-system-panel"],
        ["sim-physician-trigger",  "sim-physician-panel"],
        ["sim-simtype-trigger",    "sim-simtype-panel"],
        ["sim-machine-trigger",    "sim-machine-panel"],
        ["sim-bodysite-trigger",   "sim-bodysite-panel"],
        ["tasks-physician-trigger",  "tasks-physician-panel"],
        ["tasks-diagnosis-trigger",  "tasks-diagnosis-panel"],
        ["tasks-tasktype-trigger",   "tasks-tasktype-panel"]
    ];

    function closeAll(except) {
        pairs.forEach(function(p) {
            var panel = document.getElementById(p[1]);
            if (panel && p[1] !== except) panel.style.display = "none";
        });
    }

    var _clearInProgress = false;
    document.addEventListener("click", function(e) {
        // Handle clear buttons: stop propagation so trigger button doesn't fire,
        // and programmatically clear the associated chip group inputs
        var clearBtn = e.target.closest && e.target.closest(".wf-filter-clear-btn");
        if (clearBtn && !_clearInProgress) {
            e.stopPropagation();
            e.preventDefault();
            closeAll();
            // Find the sibling chip-dropdown panel and deselect all checked chips
            var wrapper = clearBtn.closest("[style*='inline-block']");
            if (wrapper) {
                var panel = wrapper.querySelector(".wf-chip-dropdown");
                if (panel) {
                    panel.querySelectorAll("input[type='radio']:checked, input[type='checkbox']:checked").forEach(function(inp) {
                        inp.click();  // deselect via native click so React state updates
                    });
                }
            }
            // Re-dispatch so Dash sees the n_clicks increment (with guard to avoid loop)
            _clearInProgress = true;
            setTimeout(function() {
                clearBtn.dispatchEvent(new MouseEvent("click", {bubbles: true}));
                _clearInProgress = false;
            }, 0);
            return;
        }
        // Check if click is on a trigger button
        for (var i = 0; i < pairs.length; i++) {
            var btn = document.getElementById(pairs[i][0]);
            var panel = document.getElementById(pairs[i][1]);
            if (!btn || !panel) continue;
            if (btn.contains(e.target)) {
                var open = panel.style.display !== "none";
                closeAll();  // close everything first
                panel.style.display = open ? "none" : "block";
                return;
            }
        }
        // Check if click is inside an open panel (keep it open)
        for (var j = 0; j < pairs.length; j++) {
            var p = document.getElementById(pairs[j][1]);
            if (p && p.contains(e.target)) return;
        }
        // Click outside — close all
        closeAll();
    });
})();


// ---------------------------------------------------------------------------
// Filter cross-check: hide chips whose values aren't available in the data
// ---------------------------------------------------------------------------
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.filterSync = {
    /**
     * applyFilterOptions: reads the wf-filter-options store and hides
     * chip elements that are not in the available options set.
     * Returns a dummy value (written to a hidden div).
     */
    applyFilterOptions: function(options) {
        if (!options) return "";

        // Support multiple pages via _prefix key (default: "workflow" for backward compat)
        var prefix = options._prefix || "workflow";
        var configs = [
            {groupId: prefix + "-filter-department", key: "departments"},
            {groupId: prefix + "-filter-physician",  key: "physicians"},
            {groupId: prefix + "-filter-technique",  key: "techniques"},
            {groupId: prefix + "-filter-body-system", key: "bodySystems"}
        ];

        configs.forEach(function(cfg) {
            var available = new Set(options[cfg.key] || []);
            var group = document.getElementById(cfg.groupId);
            if (!group) return;

            // DMC Chips render as wrapper divs containing an <input> + <label>
            var chips = group.querySelectorAll(
                '[class*="Chip-root"], [class*="chip-root"]'
            );
            if (chips.length === 0) {
                // Fallback: try label elements directly
                chips = group.querySelectorAll("label");
            }
            chips.forEach(function(chip) {
                var input = chip.querySelector("input");
                if (!input) return;
                var val = input.value;
                if (available.size === 0 || available.has(val)) {
                    chip.style.display = "";
                    chip.style.opacity = "";
                    chip.style.pointerEvents = "";
                } else {
                    chip.style.display = "none";
                }
            });
        });

        return "";
    }
};
