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
    // Use customdata for raw values so hover always shows actual numbers
    var hoverFmt = spark.hover_fmt
        ? spark.hover_fmt.replace(/%\{y/g, "%{customdata")
        : "%{x|%b %d}: %{customdata:,.0f}<extra></extra>";

    // Compute y range for gradient fill
    var yMin = Math.min.apply(null, yVals);
    var yMax = Math.max.apply(null, yVals);
    var yRange = yMax - yMin || 1;

    return {
        data: [{
            x: spark.labels,
            y: yVals,
            customdata: rawVals,
            mode: "lines",
            line: {color: color, width: 1.5},
            fill: "tozeroy",
            fillgradient: {
                type: "vertical",
                start: yMin - yRange * 0.3,
                stop: yMax,
                colorscale: [
                    [0, hexToRgba(color, 0)],
                    [1, hexToRgba(color, 0.2)]
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
                range: [yMin - yRange * 0.3, yMax + yRange * 0.05]
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

    /**
     * Generic sparkline updater keyed by component ID suffix.
     * Used by tasks page KPI cards where the data key is derived from
     * the graph component's ID (e.g., "tasks-spark-open" → key "open").
     * Data format: { key: { x: [...], y: [...] } }
     */
    updateFromStore: function(data, componentId) {
        if (!data || !componentId) return window.dash_clientside.no_update;

        // Extract key from component ID: "tasks-spark-open" → "open"
        var parts = componentId.split("-");
        var key = parts[parts.length - 1];

        var spark = data[key];
        if (!spark || !spark.x || !spark.y) return window.dash_clientside.no_update;

        var color = spark.color || "#7C2A83";
        return {
            data: [{
                x: spark.x,
                y: spark.y,
                mode: "lines",
                line: {color: color, width: 1.5},
                hovertemplate: "%{x|%b %d}: %{y:,.0f}<extra></extra>"
            }],
            layout: {
                margin: {l: 0, r: 0, t: 0, b: 0},
                height: 44,
                plot_bgcolor: "rgba(0,0,0,0)",
                paper_bgcolor: "rgba(0,0,0,0)",
                xaxis: {visible: false},
                yaxis: {visible: false},
                showlegend: false,
                dragmode: false,
                hovermode: "x"
            }
        };
    }
};
