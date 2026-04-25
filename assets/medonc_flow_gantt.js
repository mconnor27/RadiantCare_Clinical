/**
 * Med-Onc Cross-Referrals Flow-Gantt wrapper.
 * Reuses the core flow_gantt.js _renderSinglePipeline by temporarily
 * swapping the container ID to "wf-flow-gantt" (which the renderer expects),
 * rendering, then restoring the original ID.
 *
 * After rendering, patches the click handlers on flow bands to dispatch
 * selection to "medonc-store-selected-flow" instead of workflow stores.
 *
 * Modeled directly on referral_flow_gantt.js.
 *
 * Depends on: flow_gantt.js (must load first — Dash loads assets alphabetically,
 * and "m" > "f" so this loads after flow_gantt.js).
 */
(function() {
    "use strict";

    window.dash_clientside = window.dash_clientside || {};

    // Custom conversion chart for band 2 (Med-Onc Appt → Rad-Onc Referral).
    // The shared flow_gantt.js renderer only handles bands 0 and 1, so we
    // draw this one ourselves. Uses the `radrefPct` series the server
    // provides in convByAgg for this purpose.
    function _renderMedoncBand2(flowDetails, agg, chartType, smooth) {
        var font = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
        agg = agg || "M";
        chartType = chartType || "line";
        smooth = smooth || 0;
        var aggLabels = {D: "daily", W: "weekly", M: "monthly", Y: "yearly"};
        var aggLabel = aggLabels[agg] || "monthly";

        var conv = flowDetails.convByAgg[agg];
        var title = "Appt → Rad-Onc Ref Rate (" + aggLabel + ")";

        function emptyFig(msg) {
            return [{
                data: [],
                layout: {
                    font: {family: font, size: 12, color: "#6B7280"},
                    margin: {l: 48, r: 16, t: 32, b: 42},
                    plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)",
                    xaxis: {visible: false}, yaxis: {visible: false},
                    autosize: true,
                    annotations: [{
                        text: msg, showarrow: false,
                        xref: "paper", yref: "paper", x: 0.5, y: 0.5,
                        font: {size: 14, color: "#9CA3AF"}
                    }]
                }
            }, title];
        }

        if (!conv || !conv.dates || conv.dates.length === 0 || !conv.radrefPct) {
            return emptyFig("No conversion data");
        }

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

        // Match the color the shared JS uses for the other transitions:
        // selectedFlow=N → colors[N]. Transition 2 = "Appt → Rad-Onc Ref",
        // which is drawn in the green band color (the Med-Onc Appt bar) —
        // same convention as the distribution and duration-trend charts.
        var colors = flowDetails.colors || ["#7C2A83", "#2196F3", "#4CAF50", "#F59E0B"];
        var color = colors[2] || "#4CAF50";
        var vals = (smooth > 1 && chartType !== "bar")
            ? movingAvg(conv.radrefPct, smooth) : conv.radrefPct;

        var customdata = [];
        for (var i = 0; i < vals.length; i++) {
            customdata.push([conv.radrefPct[i], conv.completed[i] || 0]);
        }
        var hoverTpl = "%{y:.1f}%  · n=%{customdata[1]}<extra>"
            + "Appt → Rad-Onc Ref</extra>";

        var hexToRgba = window.dash_clientside
            && window.dash_clientside.flowGantt
            && window.dash_clientside.flowGantt.hexToRgba;

        var trace;
        if (chartType === "bar") {
            trace = {
                x: conv.dates, y: vals, name: "Appt → Rad-Onc Ref",
                type: "bar",
                marker: {
                    color: (typeof hexToRgba === "function") ? hexToRgba(color, 0.7) : color,
                    line: {color: color, width: 1},
                },
                customdata: customdata, hovertemplate: hoverTpl,
            };
        } else {
            var fillMode = chartType === "area" ? "tozeroy" : "none";
            var fillColor = (chartType === "area" && typeof hexToRgba === "function")
                ? hexToRgba(color, 0.15) : undefined;
            trace = {
                x: conv.dates, y: vals, name: "Appt → Rad-Onc Ref",
                type: "scatter", mode: "lines+markers",
                line: {color: color, width: 2},
                marker: {color: color, size: 4},
                fill: fillMode, fillcolor: fillColor,
                customdata: customdata, hovertemplate: hoverTpl,
            };
        }

        var layout = {
            font: {family: font, size: 12, color: "#6B7280"},
            margin: {l: 48, r: 16, t: 32, b: 42},
            plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)",
            xaxis: {showgrid: false},
            yaxis: {gridcolor: "#E5E7EB", gridwidth: 1, title: "%", rangemode: "tozero"},
            autosize: true,
            showlegend: false,
            hovermode: "x unified",
            hoverlabel: {
                bgcolor: "#FFFFFF", bordercolor: "#D1D5DB",
                font: {color: "#1A1A2E", family: font, size: 12},
            },
        };
        return [{data: [trace], layout: layout}, title];
    }

    // Overall-pipeline conversion chart used when NO band is selected.
    // Shows three cumulative-from-Created rates on one chart:
    //   Created → Scheduled  (schedPct)
    //   Created → Seen        (completePctOverall)
    //   Created → Rad-Onc Ref (radrefPctOverall)
    // Together they paint the full funnel retention over time — each
    // line is denominated by the same Created count, so the vertical
    // gap between lines is the dropoff at that stage.
    function _renderMedoncOverall(flowDetails, agg, chartType, smooth) {
        var font = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
        agg = agg || "M";
        chartType = chartType || "line";
        smooth = smooth || 0;
        var aggLabels = {D: "daily", W: "weekly", M: "monthly", Y: "yearly"};
        var aggLabel = aggLabels[agg] || "monthly";

        var conv = flowDetails.convByAgg[agg];
        var title = "Overall Pipeline Conversion (" + aggLabel + ")";

        function emptyFig(msg) {
            return [{
                data: [],
                layout: {
                    font: {family: font, size: 12, color: "#6B7280"},
                    margin: {l: 48, r: 16, t: 32, b: 42},
                    plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)",
                    xaxis: {visible: false}, yaxis: {visible: false},
                    autosize: true,
                    annotations: [{
                        text: msg, showarrow: false,
                        xref: "paper", yref: "paper", x: 0.5, y: 0.5,
                        font: {size: 14, color: "#9CA3AF"}
                    }]
                }
            }, title];
        }

        if (!conv || !conv.dates || conv.dates.length === 0) {
            return emptyFig("No conversion data");
        }

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

        var colors = flowDetails.colors || ["#7C2A83", "#2196F3", "#4CAF50", "#F59E0B"];
        var hexToRgba = window.dash_clientside
            && window.dash_clientside.flowGantt
            && window.dash_clientside.flowGantt.hexToRgba;

        // Color each line with the destination-stage color so the chart's
        // palette matches the flow gantt bars: Scheduled (blue), Seen
        // (green), Rad-Onc Ref (orange).
        var series = [
            {name: "Created → Scheduled",   values: conv.schedPct,           color: colors[1] || "#2196F3"},
            {name: "Created → Seen",        values: conv.completePctOverall, color: colors[2] || "#4CAF50"},
            {name: "Created → Rad-Onc Ref", values: conv.radrefPctOverall,   color: colors[3] || "#F59E0B"},
        ];

        var traces = [];
        for (var si = 0; si < series.length; si++) {
            var sr = series[si];
            if (!sr.values) continue;
            var vals = (smooth > 1 && chartType !== "bar")
                ? movingAvg(sr.values, smooth) : sr.values;

            var customdata = [];
            for (var i = 0; i < vals.length; i++) {
                customdata.push([sr.values[i], conv.created[i] || 0]);
            }
            var hoverTpl = "%{y:.1f}%  · n=%{customdata[1]}<extra>" + sr.name + "</extra>";

            if (chartType === "bar") {
                traces.push({
                    x: conv.dates, y: vals, name: sr.name, type: "bar",
                    marker: {
                        color: (typeof hexToRgba === "function") ? hexToRgba(sr.color, 0.7) : sr.color,
                        line: {color: sr.color, width: 1},
                    },
                    customdata: customdata, hovertemplate: hoverTpl,
                });
            } else {
                var fillMode = chartType === "area" ? "tozeroy" : "none";
                var fillColor = (chartType === "area" && typeof hexToRgba === "function")
                    ? hexToRgba(sr.color, 0.12) : undefined;
                traces.push({
                    x: conv.dates, y: vals, name: sr.name,
                    type: "scatter", mode: "lines+markers",
                    line: {color: sr.color, width: 2},
                    marker: {color: sr.color, size: 4},
                    fill: fillMode, fillcolor: fillColor,
                    customdata: customdata, hovertemplate: hoverTpl,
                });
            }
        }

        var layout = {
            font: {family: font, size: 12, color: "#6B7280"},
            margin: {l: 48, r: 16, t: 32, b: 42},
            plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)",
            xaxis: {showgrid: false},
            yaxis: {gridcolor: "#E5E7EB", gridwidth: 1, title: "%", rangemode: "tozero"},
            autosize: true,
            showlegend: true,
            legend: {orientation: "h", y: 1.14, x: 0, xanchor: "left", yanchor: "bottom"},
            hovermode: "x unified",
            hoverlabel: {
                bgcolor: "#FFFFFF", bordercolor: "#D1D5DB",
                font: {color: "#1A1A2E", family: font, size: 12},
            },
        };
        return [{data: traces, layout: layout}, title];
    }


    window.dash_clientside.medoncFlowGantt = {
        render: function(rawData) {
            var container = document.getElementById("medonc-flow-gantt");
            if (!container || !rawData) return window.dash_clientside.no_update;

            // Temporarily rename so the core renderer can find it
            container.id = "wf-flow-gantt";

            try {
                window.dash_clientside.flowGantt._renderSinglePipeline(
                    rawData, false, null
                );
            } finally {
                container.id = "medonc-flow-gantt";
            }

            // ── Patch click handlers to target med-onc stores ──────────
            var svg = container.querySelector("svg");
            if (svg) {
                var bands = svg.querySelectorAll(".flow-gantt-band");
                for (var b = 0; b < bands.length; b++) {
                    (function(band, bandIdx) {
                        var clone = band.cloneNode(true);
                        band.parentNode.replaceChild(clone, band);

                        clone.addEventListener("mouseenter", function() {
                            clone.style.fill = clone.getAttribute("data-hover-fill");
                            clone.style.stroke = clone.getAttribute("data-hover-stroke");
                            clone.style.strokeWidth = clone.getAttribute("data-hover-stroke-width");
                        });
                        clone.addEventListener("mouseleave", function() {
                            clone.style.fill = clone.getAttribute("data-base-fill");
                            clone.style.stroke = clone.getAttribute("data-base-stroke");
                            clone.style.strokeWidth = clone.getAttribute("data-base-stroke-width");
                        });

                        clone.addEventListener("click", function(e) {
                            e.stopPropagation();
                            var cur = container.__mfgSelectedFlow;
                            var sel = (cur === bandIdx) ? null : bandIdx;
                            container.__mfgSelectedFlow = sel;

                            var allBands = svg.querySelectorAll(".flow-gantt-band");
                            for (var i = 0; i < allBands.length; i++) {
                                var ab = allBands[i];
                                var idx = parseInt(ab.getAttribute("data-flow-index"), 10);
                                if (sel === null || sel === undefined) {
                                    ab.style.fill = ab.getAttribute("data-orig-fill");
                                    ab.style.stroke = ab.getAttribute("data-orig-stroke");
                                    ab.style.strokeWidth = ab.getAttribute("data-orig-stroke-width");
                                    ab.style.opacity = "";
                                } else if (idx === sel) {
                                    ab.style.fill = ab.getAttribute("data-hover-fill");
                                    ab.style.stroke = ab.getAttribute("data-hover-stroke");
                                    ab.style.strokeWidth = ab.getAttribute("data-hover-stroke-width");
                                    ab.style.opacity = "";
                                } else {
                                    ab.style.fill = ab.getAttribute("data-orig-fill");
                                    ab.style.stroke = ab.getAttribute("data-orig-stroke");
                                    ab.style.strokeWidth = ab.getAttribute("data-orig-stroke-width");
                                    ab.style.opacity = "0.3";
                                }
                            }

                            if (window.dash_clientside && window.dash_clientside.set_props) {
                                window.dash_clientside.set_props(
                                    "medonc-store-selected-flow", {data: sel}
                                );
                            }
                        });
                    })(bands[b], parseInt(bands[b].getAttribute("data-flow-index"), 10));
                }

                // Click SVG background to deselect
                svg.addEventListener("click", function(e) {
                    if (e.target === svg) {
                        container.__mfgSelectedFlow = null;
                        var allBands = svg.querySelectorAll(".flow-gantt-band");
                        for (var i = 0; i < allBands.length; i++) {
                            var ab = allBands[i];
                            ab.style.fill = ab.getAttribute("data-orig-fill");
                            ab.style.stroke = ab.getAttribute("data-orig-stroke");
                            ab.style.strokeWidth = ab.getAttribute("data-orig-stroke-width");
                            ab.style.opacity = "";
                        }
                        if (window.dash_clientside && window.dash_clientside.set_props) {
                            window.dash_clientside.set_props(
                                "medonc-store-selected-flow", {data: null}
                            );
                        }
                    }
                });
            }

            container.__mfgData = rawData;

            if (window.ResizeObserver && !container.__mfgRO) {
                var debounce;
                container.__mfgRO = new ResizeObserver(function() {
                    var nw = container.clientWidth;
                    var nh = container.clientHeight;
                    if (nw && nh && (nw !== container.__mfgW || nh !== container.__mfgH)) {
                        clearTimeout(debounce);
                        debounce = setTimeout(function() {
                            window.dash_clientside.medoncFlowGantt.render(
                                container.__mfgData
                            );
                        }, 150);
                    }
                });
                container.__mfgRO.observe(container);
            }
            container.__mfgW = container.clientWidth;
            container.__mfgH = container.clientHeight;

            return window.dash_clientside.no_update;
        },

        // --- Companion chart proxies --------------------------------------
        // Supply safe defaults for the compare-mode / KM args the shared
        // flow_gantt.js renderers expect. This page doesn't implement
        // compare mode or Kaplan-Meier, so those are hard-coded off.

        renderDist: function(flowDetails, selectedFlow, distType, bwSlider) {
            return window.dash_clientside.flowGantt.renderFlowDistribution(
                flowDetails, selectedFlow, distType,
                /* useKM */ false,
                /* flowDetailsB */ null,
                /* compareMode */ false,
                /* aggA */ null,
                /* aggB */ null,
                bwSlider
            );
        },

        renderTrend: function(flowDetails, selectedFlow, smoothVal, typeVal, aggVal) {
            return window.dash_clientside.flowGantt.renderFlowTrend(
                flowDetails, selectedFlow,
                /* storeTrendLegacy */ null,
                smoothVal, typeVal, aggVal,
                /* useKM */ false,
                /* flowDetailsB */ null,
                /* storeTrendLegacyB */ null,
                /* compareMode */ false,
                /* aggA */ null,
                /* aggB */ null
            );
        },

        renderConv: function(flowDetails, selectedFlow, aggVal, typeVal, smoothVal) {
            // Dispatch by selection:
            //   No selection    → _renderMedoncOverall (3 Created→X lines)
            //   Band 0 (→Sched) → shared renderer
            //   Band 1 (→Appt)  → shared renderer
            //   Band 2 (→RadRef)→ _renderMedoncBand2 (custom, 4th stage)
            // The shared renderConversionTrend only understands 3 stages
            // and the old "Created → Completed" default, neither of which
            // fits this page's full 4-stage pipeline.

            if (!flowDetails || !flowDetails.convByAgg) {
                return window.dash_clientside.flowGantt.renderConversionTrend(
                    flowDetails, selectedFlow, aggVal, typeVal, smoothVal
                );
            }

            // ── No selection: overall pipeline view (3 lines) ──────────────
            if (selectedFlow == null || selectedFlow < 0) {
                return _renderMedoncOverall(flowDetails, aggVal, typeVal, smoothVal);
            }

            // ── Band 2: custom 4th-stage renderer ──────────────────────────
            if (selectedFlow === 2) {
                return _renderMedoncBand2(flowDetails, aggVal, typeVal, smoothVal);
            }

            // ── Band 0 / band 1: shared renderer ───────────────────────────
            return window.dash_clientside.flowGantt.renderConversionTrend(
                flowDetails, selectedFlow, aggVal, typeVal, smoothVal
            );
        }
    };
})();
