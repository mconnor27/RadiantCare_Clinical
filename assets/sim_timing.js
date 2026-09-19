/**
 * Sim Timing page — clientside chart renderers.
 *
 * Four charts, each compare-aware: when compare mode is on the callback
 * receives a second (Dataset B) payload and both are drawn together.
 *
 *   renderComposition  stacked bar, median minutes per phase, by period
 *   renderDensity      histogram of first -> last milestone minutes
 *   renderDumbbell     booked vs actual, categorical
 *   renderOverrun      % past booked end, trend or total
 *
 * Tooltips always report the underlying value (never a derived/smoothed one),
 * and no chart shows an x-axis hover label.
 */

window.dash_clientside = window.dash_clientside || {};

var ST_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
var ST_A_COLOR = "#2196F3";
var ST_B_COLOR = "#FF9800";

function _stTheme() {
    var isDark = document.documentElement.getAttribute("data-theme") === "dark";
    return {
        isDark: isDark,
        text: isDark ? "#E6E7EC" : "#374151",
        muted: isDark ? "#9BA1AE" : "#6B7280",
        grid: isDark ? "#262932" : "#F0F0F0",
        zero: isDark ? "#3A3E4A" : "#D1D5DB"
    };
}

function _stBaseLayout(extra) {
    var t = _stTheme();
    var layout = {
        font: {family: ST_FONT, size: 12, color: t.text},
        margin: {l: 52, r: 16, t: 28, b: 40},
        plot_bgcolor: "rgba(0,0,0,0)",
        paper_bgcolor: "rgba(0,0,0,0)",
        autosize: true,
        hovermode: "closest",
        legend: {
            orientation: "h", yanchor: "bottom", y: 1.02,
            xanchor: "left", x: 0,
            font: {size: 11}, bgcolor: "rgba(0,0,0,0)"
        },
        xaxis: {
            showgrid: false, zeroline: false,
            showspikes: false, hoverformat: null,
            linecolor: t.grid, tickfont: {size: 11, color: t.muted}
        },
        yaxis: {
            showgrid: true, gridcolor: t.grid, zeroline: false,
            tickfont: {size: 11, color: t.muted}
        }
    };
    if (extra) {
        Object.keys(extra).forEach(function(k) {
            if (layout[k] && typeof layout[k] === "object" && !Array.isArray(layout[k])) {
                layout[k] = Object.assign({}, layout[k], extra[k]);
            } else {
                layout[k] = extra[k];
            }
        });
    }
    return layout;
}

function _stEmpty(msg) {
    return {
        data: [],
        layout: _stBaseLayout({
            xaxis: {visible: false},
            yaxis: {visible: false},
            annotations: [{
                text: msg || "No data for selected filters", showarrow: false,
                xref: "paper", yref: "paper", x: 0.5, y: 0.5,
                font: {size: 13, color: "#9CA3AF"}
            }]
        })
    };
}

/** Dashed-outline styling marks Dataset B in compare mode. */
function _stDatasetTag(isB) {
    return isB ? " (B)" : "";
}

/** Hex colour to rgba at the given alpha. */
function _stAlpha(hex, a) {
    var h = String(hex).replace("#", "");
    if (h.length === 3) h = h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
    var n = parseInt(h, 16);
    return "rgba(" + ((n >> 16) & 255) + "," + ((n >> 8) & 255) + "," +
           (n & 255) + "," + a + ")";
}

function _stFmt(v, digits) {
    if (v === null || v === undefined || isNaN(v)) return "–";
    return Number(v).toFixed(digits === undefined ? 1 : digits);
}

/** Quantile of a sorted numeric array (linear interpolation). */
function _stQuantile(sorted, q) {
    if (!sorted.length) return null;
    var pos = (sorted.length - 1) * q;
    var base = Math.floor(pos);
    var rest = pos - base;
    if (sorted[base + 1] !== undefined) {
        return sorted[base] + rest * (sorted[base + 1] - sorted[base]);
    }
    return sorted[base];
}


// Heatmap cell selection is pushed straight into the drill store with
// set_props, the same way flow_gantt.js does it. dcc.Graph.clickData is not
// used: Plotly emits plotly_click here, but Dash's own clickData prop never
// propagates for this graph, so no callback ever fires.
var _stLastCell = null;

function _stBindHeatmapClick() {
    setTimeout(function () {
        var wrap = document.getElementById("st-chart-heatmap");
        if (!wrap) return;
        var el = wrap.querySelector(".js-plotly-plot") || wrap;
        if (typeof el.on !== "function") return;
        if (el._stClickBound && typeof el.removeListener === "function") {
            el.removeListener("plotly_click", el._stClickBound);
        }
        var handler = function (e) {
            if (!e.points || !e.points.length) return;
            var cd = e.points[0].customdata;
            if (!cd || cd.length < 3) return;
            var dow = cd[1], hour = cd[2];
            var same = _stLastCell && _stLastCell.dow === dow &&
                       _stLastCell.hour === hour;
            _stLastCell = same ? null : {dow: dow, hour: hour};
            if (window.dash_clientside && window.dash_clientside.set_props) {
                window.dash_clientside.set_props("st-store-drill", {
                    data: _stLastCell
                        ? {dow: dow, hour: hour, row: null}
                        : {dow: null, hour: null, row: null}
                });
            }
        };
        el.on("plotly_click", handler);
        el._stClickBound = handler;
    }, 0);
}

window.dash_clientside.simTiming = {

    /**
     * Keep the JS-side cell memory in step with the store, so "Clear
     * selection" and a row selection don't leave the toggle out of sync.
     */
    syncDrill: function(drill) {
        _stLastCell = (drill && drill.dow !== null && drill.dow !== undefined)
            ? {dow: drill.dow, hour: drill.hour}
            : null;
        return window.dash_clientside.no_update;
    },


    /**
     * Stacked bar — aggregate minutes per phase, by period.
     * Negative segments (e.g. patients checking in before their booked start)
     * are drawn below the axis rather than clipped, so the stack stays honest.
     */
    renderComposition: function(dataA, dataB, compareMode, stackMode) {
        if (!dataA || !dataA.series || !dataA.series.length) {
            return _stEmpty("Select at least two milestones");
        }
        var t = _stTheme();
        var traces = [];
        var aggLabel = dataA.agg === "mean" ? "Mean" : "Median";
        var anyNegative = false;

        function addSet(d, isB) {
            if (!d || !d.series) return;
            d.series.forEach(function(s, i) {
                var custom = s.values.map(function(v, j) {
                    return [d.counts[j], s.label,
                            (d.span && d.span[j] != null) ? d.span[j] : "–"];
                });
                s.values.forEach(function(v) { if (v !== null && v < 0) anyNegative = true; });
                traces.push({
                    type: "bar",
                    name: s.label + (s.crossClock ? " ⚠" : "") + _stDatasetTag(isB),
                    x: d.periods,
                    y: s.values,
                    offsetgroup: isB ? "B" : "A",
                    alignmentgroup: "phases",
                    marker: {
                        color: s.color,
                        opacity: isB ? 0.55 : 1,
                        line: isB
                            ? {color: ST_B_COLOR, width: 1.5}
                            : {width: 0}
                    },
                    customdata: custom,
                    hovertemplate:
                        "<b>%{customdata[1]}</b>" + _stDatasetTag(isB) + "<br>" +
                        "%{x}<br>" +
                        aggLabel + ": %{y:.1f} min<br>" +
                        "total: %{customdata[2]} min<br>" +
                        "n = %{customdata[0]}<extra></extra>"
                });
            });
        }

        addSet(dataA, false);
        if (compareMode && dataB) addSet(dataB, true);

        // The stack adds up to a real duration now that segments are position
        // differences, so name it on the axis rather than leaving the reader to
        // guess what the bar height means.
        var spanLabel = (dataA.spanLabel && stackMode !== "grouped")
            ? aggLabel + " minutes  ·  stack = " + dataA.spanLabel
            : aggLabel + " minutes";
        var layout = _stBaseLayout({
            barmode: "relative",
            bargap: 0.25,
            yaxis: {
                title: {text: spanLabel, font: {size: 11}},
                zeroline: anyNegative,
                zerolinecolor: t.zero,
                zerolinewidth: 1
            }
        });
        // "relative" keeps the phases stacked; in compare mode the distinct
        // offsetgroups still place A and B side by side. "grouped" is the
        // gear's opt-in for reading each phase against the others directly,
        // at the cost of the stack no longer summing to the span.
        if (stackMode === "grouped") layout.barmode = "group";
        return {data: traces, layout: layout};
    },

    /**
     * Histogram of the full first-milestone -> last-milestone interval.
     */
    renderDensity: function(dataA, dataB, compareMode) {
        if (!dataA || !dataA.values || !dataA.values.length) {
            return _stEmpty("Select at least two milestones");
        }
        var t = _stTheme();
        var traces = [];

        function bounds(d) {
            var s = d.values.slice().sort(function(a, b) { return a - b; });
            return [_stQuantile(s, 0.005), _stQuantile(s, 0.995)];
        }
        var lo = bounds(dataA)[0], hi = bounds(dataA)[1];
        if (compareMode && dataB && dataB.values && dataB.values.length) {
            var bb = bounds(dataB);
            lo = Math.min(lo, bb[0]);
            hi = Math.max(hi, bb[1]);
        }
        var bs = dataA.binSize || 10;
        lo = Math.floor(lo / bs) * bs;
        hi = Math.ceil(hi / bs) * bs;

        function addSet(d, isB) {
            if (!d || !d.values || !d.values.length) return;
            traces.push({
                type: "histogram",
                name: (isB ? "B" : "A") + " · n = " + d.n,
                x: d.values,
                xbins: {start: lo, end: hi + bs, size: bs},
                marker: {
                    color: isB ? ST_B_COLOR : ST_A_COLOR,
                    opacity: compareMode ? 0.55 : 0.85,
                    line: {width: 0}
                },
                // No dataset prefix on a single series — it is just noise.
                // In compare mode the two histograms overlay, so they do need
                // telling apart.
                hovertemplate:
                    (compareMode ? (isB ? "B" : "A") + "<br>" : "") +
                    "%{x} min<br>%{y} sims<extra></extra>"
            });
        }

        addSet(dataA, false);
        if (compareMode && dataB) addSet(dataB, true);

        var shapes = [];
        var annotations = [];
        function addMedian(d, isB) {
            if (!d || d.median === null || d.median === undefined) return;
            shapes.push({
                type: "line", x0: d.median, x1: d.median,
                y0: 0, y1: 1, yref: "paper",
                line: {color: isB ? ST_B_COLOR : ST_A_COLOR, width: 2, dash: "dash"}
            });
            annotations.push({
                x: d.median, y: isB ? 1.09 : 1.02, yref: "paper",
                text: "med " + _stFmt(d.median, 0) + "m",
                showarrow: false, font: {size: 11, color: isB ? ST_B_COLOR : ST_A_COLOR},
                xanchor: "center", yanchor: "bottom"
            });
        }
        addMedian(dataA, false);
        if (compareMode && dataB) addMedian(dataB, true);

        var title = dataA.label + (dataA.crossClock ? "  ⚠ cross-clock" : "");

        return {
            data: traces,
            layout: _stBaseLayout({
                barmode: "overlay",
                bargap: 0.04,
                margin: {l: 52, r: 16, t: 42, b: 40},
                shapes: shapes,
                annotations: annotations,
                showlegend: !!(compareMode && dataB),
                xaxis: {title: {text: title + " (minutes)", font: {size: 11}}},
                yaxis: {title: {text: "Sims", font: {size: 11}}}
            })
        };
    },

    /**
     * Booked slot vs the actual occupied span, per category.
     *
     * Violin shows the whole distribution with the booked length drawn as a
     * reference tick; Dumbbell is the compact median-only reading. Both come
     * from one payload, and the span follows the milestone picker.
     */
    renderDumbbell: function(dataA, dataB, compareMode, chartType) {
        if (!dataA || !dataA.rows || !dataA.rows.length) return _stEmpty();
        var t = _stTheme();
        var useViolin = chartType !== "dumbbell";
        var sets = (compareMode && dataB && dataB.rows && dataB.rows.length)
            ? [dataA, dataB] : [dataA];

        var traces = [], shapes = [], annotations = [];
        var cats = dataA.rows.map(function(r) { return r.category; });

        sets.forEach(function(d, di) {
            var isB = di === 1;
            var color = isB ? ST_B_COLOR : ST_A_COLOR;
            var suffix = sets.length > 1 ? _stDatasetTag(isB) : "";

            if (useViolin) {
                d.rows.forEach(function(r, i) {
                    traces.push({
                        type: "violin", orientation: "h",
                        x: r.values,
                        y: r.values.map(function() { return r.category + suffix; }),
                        name: (isB ? "B" : "A"),
                        legendgroup: isB ? "B" : "A",
                        showlegend: sets.length > 1 && i === 0,
                        side: sets.length > 1 ? (isB ? "negative" : "positive") : "both",
                        width: sets.length > 1 ? 1.4 : 0.9,
                        points: false,
                        spanmode: "hard",
                        line: {color: color, width: 1},
                        fillcolor: _stAlpha(color, isB ? 0.22 : 0.32),
                        meanline: {visible: false},
                        box: {visible: true, width: 0.12,
                              line: {color: t.isDark ? "#E6E7EC" : "#374151", width: 1}},
                        hoverinfo: "skip"
                    });
                });
            }

            // Booked reference + median marker, drawn for both chart types.
            d.rows.forEach(function(r) {
                if (r.booked == null) return;
                shapes.push({
                    type: "line", xref: "x", yref: "y",
                    x0: r.booked, x1: r.booked,
                    y0: r.category + suffix, y1: r.category + suffix,
                    y0shift: -0.34, y1shift: 0.34,
                    line: {color: t.muted, width: 2, dash: isB ? "dot" : "solid"}
                });
                if (!useViolin) {
                    shapes.push({
                        type: "line", xref: "x", yref: "y",
                        x0: r.booked, x1: r.actual,
                        y0: r.category + suffix, y1: r.category + suffix,
                        line: {color: r.actual > r.booked ? "#F44336" : "#4CAF50",
                               width: isB ? 2 : 3, dash: isB ? "dot" : "solid"},
                        layer: "below"
                    });
                }
            });

            traces.push({
                type: "scatter", mode: "markers",
                name: "Median" + (sets.length > 1 ? " " + (isB ? "B" : "A") : ""),
                x: d.rows.map(function(r) { return r.actual; }),
                y: d.rows.map(function(r) { return r.category + suffix; }),
                marker: {
                    size: 11, symbol: isB ? "diamond-open" : "diamond",
                    color: color, line: {width: 2, color: color}
                },
                customdata: d.rows.map(function(r) {
                    return [r.n, r.booked == null ? "–" : r.booked,
                            r.booked == null ? "–" : (r.actual - r.booked).toFixed(0),
                            r.p25, r.p75];
                }),
                hovertemplate:
                    "<b>%{y}</b><br>" +
                    "median: %{x:.0f} min<br>" +
                    "IQR: %{customdata[3]:.0f}–%{customdata[4]:.0f}<br>" +
                    "booked: %{customdata[1]} min (%{customdata[2]:+} vs booked)<br>" +
                    "n = %{customdata[0]}<extra></extra>",
                showlegend: false
            });
        });

        var note = [];
        if (dataA.crossClock) note.push("⚠ cross-clock");
        if (dataA.droppedCategories) {
            note.push(dataA.droppedCategories + " group" +
                      (dataA.droppedCategories === 1 ? "" : "s") +
                      " under n=" + dataA.minN + " hidden");
        }
        if (note.length) {
            annotations.push({
                xref: "paper", yref: "paper", x: 1, y: 1.04, xanchor: "right",
                text: note.join("  ·  "), showarrow: false,
                font: {size: 10, color: "#9CA3AF"}
            });
        }

        var height = Math.max(240, cats.length * (useViolin ? 56 : 40) + 90);
        return {
            data: traces,
            layout: _stBaseLayout({
                margin: {l: 150, r: 20, t: 34, b: 44},
                shapes: shapes,
                annotations: annotations,
                violinmode: sets.length > 1 ? "overlay" : "overlay",
                xaxis: {title: {text: dataA.spanLabel + " (minutes)  ·  grey tick = booked",
                                font: {size: 11}}},
                yaxis: {
                    type: "category", automargin: true, showgrid: false,
                    tickfont: {size: 11, color: t.muted}
                },
                showlegend: sets.length > 1
            })
        };
    },

    /**
     * The cohort's "typical sim" — one lane per milestone, a shaded spread bar
     * and a centre tick, on the same minutes-from-booked-start axis the
     * drill-down strip uses. Compare mode offsets A and B into half-lanes.
     */
    renderTypical: function(dataA, dataB, compareMode) {
        if (!dataA || !dataA.milestones || !dataA.milestones.length) {
            return _stEmpty();
        }
        var t = _stTheme();
        var COLORS = {
            sched_start: "#9CA3AF", checkin: "#2196F3", ct_first: "#7C2A83",
            ct_done: "#7C2A83", appt_end: "#F44336", note: "#4CAF50",
            sched_end: "#9CA3AF"
        };
        var both = (compareMode && dataB && dataB.milestones) ? [dataA, dataB] : [dataA];
        var ys = dataA.milestones.map(function(m) { return m.label; }).reverse();

        var shapes = [];
        if (dataA.bookedLen) {
            shapes.push({
                type: "rect", xref: "x", yref: "paper",
                x0: 0, x1: dataA.bookedLen, y0: 0, y1: 1,
                fillcolor: t.isDark ? "rgba(124,42,131,0.13)" : "rgba(124,42,131,0.07)",
                line: {width: 0}, layer: "below"
            });
        }

        var traces = [];
        both.forEach(function(d, di) {
            var isB = di === 1;
            var shift = both.length > 1 ? (isB ? 0.20 : -0.20) : 0;
            var half = both.length > 1 ? 0.15 : 0.26;

            d.milestones.forEach(function(m) {
                shapes.push({
                    type: "rect", xref: "x", yref: "y",
                    x0: m.lo, x1: m.hi, y0: m.label, y1: m.label,
                    y0shift: shift - half, y1shift: shift + half,
                    fillcolor: _stAlpha(COLORS[m.key] || "#9CA3AF", isB ? 0.20 : 0.30),
                    line: {width: isB ? 1 : 0, color: ST_B_COLOR, dash: "dot"},
                    layer: "below"
                });
            });

            traces.push({
                type: "scatter", mode: "markers",
                name: both.length > 1 ? (isB ? "B" : "A")
                                      : (d.center === "mean" ? "Mean" : "Median"),
                x: d.milestones.map(function(m) { return m.center; }),
                y: d.milestones.map(function(m) { return m.label; }),
                offsetgroup: isB ? "B" : "A",
                marker: {
                    size: 12, symbol: "line-ns-open",
                    color: d.milestones.map(function(m) { return COLORS[m.key] || "#9CA3AF"; }),
                    line: {width: 3,
                           color: d.milestones.map(function(m) { return COLORS[m.key] || "#9CA3AF"; })}
                },
                customdata: d.milestones.map(function(m) {
                    return [m.lo, m.hi, m.n, m.p10, m.p90, (isB ? "B" : "A"),
                            (m.clock === "ct" && d.reliableShare < 100) ? " ⚠ cross-clock" : ""];
                }),
                hovertemplate:
                    "<b>%{y}</b>%{customdata[6]}<br>" +
                    (both.length > 1 ? "Dataset %{customdata[5]}<br>" : "") +
                    (d.center === "mean" ? "Mean" : "Median") + ": %{x:+.0f} min<br>" +
                    d.spreadLabel + ": %{customdata[0]:+.0f} to %{customdata[1]:+.0f}<br>" +
                    "P10–90: %{customdata[3]:+.0f} to %{customdata[4]:+.0f}<br>" +
                    "n = %{customdata[2]}<extra></extra>",
                showlegend: both.length > 1
            });
        });

        var annotations = [];
        if (dataA.bookedLen) {
            annotations.push({
                x: dataA.bookedLen, y: 1.02, xref: "x", yref: "paper",
                text: "median booked end", showarrow: false, xanchor: "right",
                font: {size: 10, color: "#9CA3AF"}
            });
        }

        return {
            data: traces,
            layout: _stBaseLayout({
                margin: {l: 130, r: 24, t: 28, b: 42},
                shapes: shapes,
                annotations: annotations,
                xaxis: {
                    title: {text: "Minutes from booked start", font: {size: 11}},
                    zeroline: true, zerolinecolor: t.zero, zerolinewidth: 1,
                    showgrid: false, tickfont: {size: 11, color: t.muted}
                },
                yaxis: {
                    type: "category", categoryorder: "array", categoryarray: ys,
                    showgrid: false, automargin: true,
                    tickfont: {size: 11, color: t.muted}
                }
            })
        };
    },

    /**
     * Weekday x booked-start-hour heatmap. Compare mode is deliberately
     * ignored here: two overlaid grids are unreadable, and the cell click is
     * the drill-down entry point, which only makes sense for Dataset A.
     */
    renderHeatmap: function(dataA, dataB, compareMode, drill) {
        if (!dataA || !dataA.z || !dataA.z.length) return _stEmpty();
        var t = _stTheme();
        var d = dataA;

        var custom = d.z.map(function(row, i) {
            return row.map(function(_v, j) {
                return [d.counts[i][j], d.dayIdx[i], d.hours[j], d.detail[i][j]];
            });
        });

        var isOverrun = d.metric === "overrun";
        var minN = d.minN || 0;
        _stBindHeatmapClick();

        var scale = isOverrun
            ? [[0, t.isDark ? "#12202b" : "#EAF3FA"], [0.5, "#7FB3D9"], [1, "#F44336"]]
            : [[0, t.isDark ? "#1b1430" : "#F3E8F5"], [1, "#7C2A83"]];
        var extra = isOverrun ? "<br>median overrun: %{customdata[3]} min" : "";

        // Outline the drilled-into cell so the selection is visible on the
        // grid itself, not only in the breadcrumb.
        var shapes = [];
        if (drill && drill.dow !== null && drill.dow !== undefined) {
            var ri = d.dayIdx.indexOf(drill.dow);
            var ci = d.hours.indexOf(drill.hour);
            if (ri >= 0 && ci >= 0) {
                shapes.push({
                    type: "rect", xref: "x", yref: "y",
                    x0: d.hourLabels[ci], x1: d.hourLabels[ci],
                    x0shift: -0.5, x1shift: 0.5,
                    y0: d.days[ri], y1: d.days[ri],
                    y0shift: -0.5, y1shift: 0.5,
                    line: {color: t.isDark ? "#E6E7EC" : "#1F2937", width: 2.5},
                    fillcolor: "rgba(0,0,0,0)", layer: "above"
                });
            }
        }

        return {
            data: [{
                type: "heatmap",
                z: d.z, x: d.hourLabels, y: d.days,
                customdata: custom,
                colorscale: scale,
                xgap: 2, ygap: 2,
                colorbar: {
                    thickness: 10, len: 0.9, outlinewidth: 0,
                    tickfont: {size: 10, color: t.muted},
                    title: {text: d.label, font: {size: 10, color: t.muted},
                            side: "right"}
                },
                hovertemplate:
                    "<b>%{y} %{x}</b><br>" + d.label + ": %{z}<br>" +
                    "n = %{customdata[0]}" + extra + "<extra></extra>",
                hoverongaps: false
            }],
            layout: _stBaseLayout({
                margin: {l: 52, r: 16, t: 10, b: 34},
                shapes: shapes,
                xaxis: {showgrid: false, zeroline: false, type: "category",
                        tickfont: {size: 11, color: t.muted}},
                yaxis: {showgrid: false, zeroline: false, type: "category",
                        autorange: "reversed",
                        tickfont: {size: 11, color: t.muted}},
                showlegend: false
            })
        };
    },

    /**
     * Level 2 — every appointment in the selected heatmap cell, one lane each,
     * aligned on its own booked start. Booked slots are shaded, so a lane whose
     * Appointment End sits outside the band ran over.
     */
    _renderCohort: function(tl) {
        var t = _stTheme();
        var COLORS = {
            sched_start: "#9CA3AF", checkin: "#2196F3", ct_first: "#7C2A83",
            ct_done: "#7C2A83", appt_end: "#F44336", note: "#4CAF50",
            sched_end: "#9CA3AF"
        };
        var LABELS = {
            sched_start: "Scheduled Start", checkin: "Check-In",
            ct_first: "CT First Series", ct_done: "CT Complete",
            appt_end: "Appointment End", note: "Note Entered",
            sched_end: "Scheduled End"
        };

        var lanes = tl.lanes.slice().reverse();
        var ys = lanes.map(function(l) { return l.label; });

        var shapes = [];
        lanes.forEach(function(l) {
            if (!l.bookedLen) return;
            shapes.push({
                type: "rect", xref: "x", yref: "y",
                x0: 0, x1: l.bookedLen, y0: l.label, y1: l.label,
                y0shift: -0.36, y1shift: 0.36,
                fillcolor: t.isDark ? "rgba(124,42,131,0.16)" : "rgba(124,42,131,0.09)",
                line: {width: 0}, layer: "below"
            });
        });

        var byKey = {};
        lanes.forEach(function(l) {
            l.marks.forEach(function(m) {
                (byKey[m.key] = byKey[m.key] || []).push({
                    x: m.at, y: l.label, clock: m.clock, reliable: l.reliable,
                    therapist: l.therapist
                });
            });
        });

        var order = ["checkin", "sched_start", "ct_first", "ct_done",
                     "note", "appt_end", "sched_end"];
        var traces = order.filter(function(k) { return byKey[k]; }).map(function(k) {
            var pts = byKey[k];
            return {
                type: "scatter", mode: "markers",
                name: LABELS[k],
                x: pts.map(function(p) { return p.x; }),
                y: pts.map(function(p) { return p.y; }),
                marker: {
                    size: 9, color: COLORS[k],
                    symbol: pts.map(function(p) {
                        return (p.clock === "ct" && !p.reliable) ? "circle-open" : "circle";
                    }),
                    line: {width: 1.5, color: COLORS[k]}
                },
                customdata: pts.map(function(p) {
                    return [LABELS[k], p.therapist,
                            (p.clock === "ct" && !p.reliable) ? " (CT corrected)" : ""];
                }),
                hovertemplate:
                    "<b>%{customdata[0]}</b>%{customdata[2]}<br>" +
                    "%{y}<br>%{x:+.0f} min from booked start<br>" +
                    "%{customdata[1]}<extra></extra>"
            };
        });

        // A single far-out mark would compress every other lane into a sliver.
        // Clamp to the bulk and say out loud how many fell outside.
        var allX = [];
        lanes.forEach(function(l) {
            l.marks.forEach(function(m) { allX.push(m.at); });
            if (l.bookedLen) allX.push(l.bookedLen);
        });
        allX.sort(function(a, b) { return a - b; });
        var lo = _stQuantile(allX, 0.01), hi = _stQuantile(allX, 0.99);
        var span = Math.max(30, hi - lo);
        lo = Math.min(lo - span * 0.06, -5);
        hi = hi + span * 0.06;
        var outside = allX.filter(function(v) { return v < lo || v > hi; }).length;

        var annotations = [];
        if (outside > 0) {
            annotations.push({
                xref: "paper", yref: "paper", x: 1, y: 1.03, xanchor: "right",
                text: outside + " mark" + (outside === 1 ? "" : "s") + " beyond axis",
                showarrow: false, font: {size: 10, color: "#9CA3AF"}
            });
        }

        return {
            data: traces,
            layout: _stBaseLayout({
                margin: {l: 96, r: 24, t: 30, b: 42},
                shapes: shapes,
                annotations: annotations,
                xaxis: {
                    title: {text: "Minutes from each appointment's booked start",
                            font: {size: 11}},
                    range: [lo, hi],
                    zeroline: true, zerolinecolor: t.zero, zerolinewidth: 1,
                    showgrid: false, tickfont: {size: 11, color: t.muted}
                },
                yaxis: {
                    type: "category", categoryorder: "array", categoryarray: ys,
                    showgrid: false, automargin: true,
                    tickfont: {size: 10, color: t.muted}
                },
                showlegend: true
            })
        };
    },

    /**
     * One appointment, as a milestone strip relative to its booked start.
     * The booked slot is drawn as a band so overrun is visible directly.
     */
    renderTimeline: function(tl) {
        if (!tl) return _stEmpty("Select an appointment from the table");
        if (tl.mode === "cohort") {
            return window.dash_clientside.simTiming._renderCohort(tl);
        }
        var t = _stTheme();
        var COLORS = {
            sched_start: "#9CA3AF", checkin: "#2196F3", ct_first: "#7C2A83",
            ct_done: "#7C2A83", appt_end: "#F44336", note: "#4CAF50",
            sched_end: "#9CA3AF"
        };

        var xs = tl.marks.map(function(m) { return m.at; });
        var lo = Math.min.apply(null, xs.concat([0]));
        var hi = Math.max.apply(null, xs.concat([tl.bookedLen || 0]));
        var pad = Math.max(8, (hi - lo) * 0.08);

        var shapes = [];
        if (tl.bookedLen) {
            shapes.push({
                type: "rect", x0: 0, x1: tl.bookedLen, y0: 0.35, y1: 0.65,
                fillcolor: t.isDark ? "rgba(124,42,131,0.16)" : "rgba(124,42,131,0.09)",
                line: {width: 0}, layer: "below"
            });
        }
        shapes.push({
            type: "line", x0: lo - pad / 2, x1: hi + pad / 2, y0: 0.5, y1: 0.5,
            line: {color: t.grid, width: 2}, layer: "below"
        });

        var traces = [{
            type: "scatter", mode: "markers+text",
            x: xs,
            y: tl.marks.map(function() { return 0.5; }),
            text: tl.marks.map(function(m) { return m.label; }),
            textposition: tl.marks.map(function(_m, i) {
                return i % 2 === 0 ? "top center" : "bottom center";
            }),
            textfont: {size: 10, color: t.muted},
            marker: {
                size: 13,
                color: tl.marks.map(function(m) { return COLORS[m.key] || "#9CA3AF"; }),
                symbol: tl.marks.map(function(m) {
                    return (m.clock === "ct" && !tl.reliable) ? "circle-open" : "circle";
                }),
                line: {width: 2,
                       color: tl.marks.map(function(m) { return COLORS[m.key] || "#9CA3AF"; })}
            },
            customdata: tl.marks.map(function(m) {
                return [m.label, m.clock === "ct" && !tl.reliable ? " (corrected)" : ""];
            }),
            hovertemplate:
                "<b>%{customdata[0]}</b>%{customdata[1]}<br>" +
                "%{x:+.0f} min from booked start<extra></extra>",
            showlegend: false
        }];

        var annotations = [];
        if (tl.bookedLen) {
            annotations.push({
                x: tl.bookedLen, y: 0.70, xref: "x", yref: "y",
                text: "booked end", showarrow: false, xanchor: "center",
                font: {size: 10, color: "#9CA3AF"}
            });
        }

        return {
            data: traces,
            layout: _stBaseLayout({
                margin: {l: 24, r: 24, t: 34, b: 40},
                shapes: shapes,
                annotations: annotations,
                xaxis: {
                    title: {text: "Minutes from booked start (" + tl.bookedStart +
                                  " on " + tl.date + ")", font: {size: 11}},
                    range: [lo - pad, hi + pad],
                    zeroline: true, zerolinecolor: t.zero, zerolinewidth: 1,
                    showgrid: false, tickfont: {size: 11, color: t.muted}
                },
                yaxis: {visible: false, range: [0.2, 0.85], fixedrange: true},
                showlegend: false
            })
        };
    },

    /**
     * Overrun rate — % of sims past the booked end, as a trend. The period
     * average is a dashed reference line; it is hoverable rather than being a
     * separate "Total" view. Optional LOESS-style smoothing comes from the
     * gear, and the tooltip always reports the raw rate, never the smoothed
     * one.
     */
    renderOverrun: function(dataA, dataB, compareMode, smoothFrac) {
        if (!dataA || !dataA.periods) return _stEmpty();
        var t = _stTheme();
        var traces = [];
        var frac = Number(smoothFrac) || 0;

        function smooth(vals) {
            if (frac <= 0 || vals.length < 4) return vals.slice();
            var win = Math.max(2, Math.round(vals.length * frac));
            return vals.map(function(_v, i) {
                var a = Math.max(0, i - Math.floor(win / 2));
                var b = Math.min(vals.length, a + win);
                var seg = vals.slice(a, b).filter(function(x) { return x != null; });
                if (!seg.length) return null;
                return seg.reduce(function(p, c) { return p + c; }, 0) / seg.length;
            });
        }

        function addSet(d, isB) {
            if (!d || !d.periods || !d.periods.length) return;
            var shown = smooth(d.rate);
            traces.push({
                type: "scatter", mode: "lines+markers",
                name: (compareMode ? (isB ? "B" : "A") + " · " : "") + d.label,
                x: d.periods, y: shown,
                line: {
                    color: isB ? ST_B_COLOR : ST_A_COLOR,
                    width: 2, dash: isB ? "dot" : "solid",
                    // Deliberately linear. Plotly's spline shape is a second,
                    // hidden smoother: with it on, the line still curved
                    // between points at slider 0, so "no smoothing" did not
                    // look like no smoothing. The slider is the only smoother.
                    shape: "linear"
                },
                marker: {size: frac > 0 ? 4 : 6},
                customdata: d.over.map(function(o, i) {
                    return [o, d.counts[i], d.rate[i]];
                }),
                hovertemplate:
                    (compareMode ? (isB ? "B" : "A") + "<br>" : "") +
                    "%{x}<br>%{customdata[2]:.1f}% over<br>" +
                    "%{customdata[0]} of %{customdata[1]} sims<extra></extra>"
            });
            // Period average — a hoverable reference line rather than a
            // separate view. Drawn as a trace (not a shape) so it can report
            // its own numbers on hover.
            traces.push({
                type: "scatter", mode: "lines",
                name: (isB ? "B" : "A") + " average",
                x: d.periods,
                y: d.periods.map(function() { return d.overall; }),
                line: {color: isB ? ST_B_COLOR : ST_A_COLOR, width: 1, dash: "dash"},
                opacity: 0.5,
                customdata: d.periods.map(function() {
                    return [d.totalOver, d.totalN,
                            d.medianOverMinutes == null ? "–" : d.medianOverMinutes];
                }),
                hovertemplate:
                    "<b>Period average</b>" + (compareMode ? " (" + (isB ? "B" : "A") + ")" : "") +
                    "<br>%{y:.1f}% over<br>" +
                    "%{customdata[0]} of %{customdata[1]} sims<br>" +
                    "median overrun: %{customdata[2]} min<extra></extra>",
                showlegend: false
            });
        }
        addSet(dataA, false);
        if (compareMode && dataB) addSet(dataB, true);

        return {
            data: traces,
            layout: _stBaseLayout({
                hovermode: "closest",
                yaxis: {
                    title: {text: "% past booked end", font: {size: 11}},
                    rangemode: "tozero", ticksuffix: "%"
                },
                showlegend: !!(compareMode && dataB),
                annotations: dataA.crossClock ? [{
                    text: "⚠ cross-clock definition",
                    xref: "paper", yref: "paper", x: 1, y: 1.06,
                    xanchor: "right", showarrow: false,
                    font: {size: 10, color: "#F59E0B"}
                }] : []
            })
        };
    }
};
