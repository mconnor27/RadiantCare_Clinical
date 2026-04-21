/**
 * KPI card sparkline rendering.
 * Depends on: 00_utils.js (hexToRgba, loess)
 */

window.dash_clientside = window.dash_clientside || {};

function buildSparkline(data, smoothPct, key) {
    if (!data || !data[key]) {
        return window.dash_clientside.no_update;
    }

    var spark = data[key];
    var frac = (smoothPct || 0) * 0.5;  // slider 0-1 maps to frac 0-0.5
    var rawVals = spark.values;
    var yVals = frac > 0 && rawVals.length >= 4 ? loess(rawVals, frac) : rawVals;
    var color = spark.color || "#7C2A83";
    // Dark-mode: fill at 0.2 over a dark bg disappears. Bump top-stop
    // opacity so the area under the spark line stays readable.
    var _isDark = document.documentElement.getAttribute("data-theme") === "dark";
    var _fillTop = _isDark ? 0.38 : 0.2;
    // Use customdata for raw values so hover always shows actual numbers
    var hoverFmt = spark.hover_fmt
        ? spark.hover_fmt.replace(/%\{y/g, "%{customdata")
        : "%{x|%b %d}: %{customdata:,.0f}<extra></extra>";

    // Compute y range for gradient fill
    var yMin = Math.min.apply(null, yVals);
    var yMax = Math.max.apply(null, yVals);
    var yRange = yMax - yMin || 1;

    var yFloor = yMin - yRange * 0.3;
    var baseline = Array(spark.labels.length).fill(yFloor);

    return {
        data: [
        // Invisible baseline at y-axis bottom (fill anchor)
        {
            x: spark.labels,
            y: baseline,
            mode: "lines",
            line: {width: 0, color: "transparent"},
            hoverinfo: "skip",
            showlegend: false
        },
        // Sparkline trace fills down to baseline
        {
            x: spark.labels,
            y: yVals,
            customdata: rawVals,
            mode: "lines",
            line: {color: color, width: 1.5},
            fill: "tonexty",
            fillgradient: {
                type: "vertical",
                start: yFloor,
                stop: yMax,
                colorscale: [
                    [0, hexToRgba(color, 0)],
                    [1, hexToRgba(color, _fillTop)]
                ]
            },
            fillcolor: hexToRgba(color, 0),
            hovertemplate: hoverFmt
        }],
        layout: {
            margin: {l: 0, r: 0, t: 0, b: 0},
            height: 44,
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
            yaxis: {
                visible: false,
                range: [yFloor, yMax + yRange * 0.05]
            },
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
    smoothOpsConsultLead: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "consult_lead");
    },
    smoothOpsSimLead: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "sim_lead");
    },
    smoothOpsNewStarts: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "newstarts");
    },
    // Clinic Visits page sparklines
    smoothCvTotal: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "total");
    },
    smoothCvConsults: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "consults");
    },
    smoothCvFollowups: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "followups");
    },
    smoothCvLead: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "lead_time");
    },
    smoothCvSimConv: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "sim_conv");
    },
    smoothCvDaysToSim: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "days_to_sim");
    },
    // Simulations page sparklines (prefixed "smoothSp" to avoid collision with home-page smoothSim*)
    smoothSpTotal: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "total");
    },
    smoothSpInitial: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "initial");
    },
    smoothSpLead: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "lead");
    },
    smoothSpConsultSim: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "consult_sim");
    },
    smoothSpTimeTx: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "time_to_tx");
    },
    smoothSpResim: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "resim");
    },

    /**
     * Generic sparkline updater keyed by component ID suffix.
     * Used by pages that don't need individual named wrappers.
     * Delegates to buildSparkline() for full visual quality (gradient fill,
     * spike crosshair, styled hoverlabel, LOESS smoothing, y-axis padding).
     *
     * Accepts two data formats:
     *   - Named wrapper format: { key: { values: [...], labels: [...], color, hover_fmt } }
     *   - Simple format:        { key: { x: [...], y: [...], color } }
     *
     * @param {object} data        - Store data keyed by sparkline name
     * @param {string} componentId - Graph component ID (e.g., "tasks-spark-open")
     * @param {number} [smoothPct] - Smoothing value (0-1), default 0.3. Optional.
     */
    updateFromStore: function(data, componentId, smoothPct) {
        if (!data || !componentId) return window.dash_clientside.no_update;

        // Extract key from component ID: "tasks-spark-open" → "open"
        var parts = componentId.split("-");
        var key = parts[parts.length - 1];

        var spark = data[key];
        if (!spark) return window.dash_clientside.no_update;

        // Normalize: convert {x, y} format to {values, labels} for buildSparkline
        var normalized = {};
        normalized[key] = {
            values: spark.values || spark.y,
            labels: spark.labels || spark.x,
            color: spark.color || "#7C2A83",
            hover_fmt: spark.hover_fmt
        };

        if (!normalized[key].values || normalized[key].values.length === 0) {
            return window.dash_clientside.no_update;
        }

        return buildSparkline(normalized, smoothPct != null ? smoothPct : 0.3, key);
    },
    // Treatment page sparklines
    smoothTxVolume: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "volume");
    },
    smoothTxNewstarts: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "newstarts");
    },
    smoothTxPatients: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "patients");
    },
    smoothTxElapsed: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "elapsed");
    },
    smoothTxFields: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "fields");
    },
    smoothTxGating: function(data, smoothPct) {
        return buildSparkline(data, smoothPct, "gating");
    }
};
