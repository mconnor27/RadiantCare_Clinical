/**
 * Clientside horizontal grouped-bar chart: Actual vs Allowed time.
 * Used on the Tasks page to compare median completion time against SLA.
 */

window.dash_clientside = window.dash_clientside || {};

window.dash_clientside.timeCompare = {

    /**
     * Render horizontal grouped bars from store data.
     * @param {Object} rawData - {rows: [{label, actual, allowed, color, n}], tickSuffix, accentColor}
     * @param {Object} currentFig - existing figure (unused, for Dash wiring)
     */
    render: function(rawData, currentFig) {
        if (!rawData || !rawData.rows || rawData.rows.length === 0) {
            return Object.assign({}, window.dash_clientside.census._emptyFig("No time comparison data"));
        }

        var rows = rawData.rows;
        var tickSuffix = rawData.tickSuffix || "";
        var nRows = rows.length;

        // Extract labels (reversed so first row appears at top)
        var labels = [];
        var actualVals = [];
        var allowedVals = [];
        var rowColors = [];
        var counts = [];

        for (var i = nRows - 1; i >= 0; i--) {
            labels.push(rows[i].label);
            actualVals.push(rows[i].actual);
            allowedVals.push(rows[i].allowed);
            rowColors.push(rows[i].color);
            counts.push(rows[i].n);
        }

        // Check if any rows have valid allowed values
        var hasAnyAllowed = allowedVals.some(function(v) { return v !== null && v !== undefined; });

        var actualColors = rowColors.map(function(c) { return hexToRgba(c, 0.85); });
        var allowedColor = "#B0BEC5";

        var traces = [];

        // Only show Allowed trace if at least one row has SLA data
        if (hasAnyAllowed) {
            // Replace nulls with 0 so Plotly doesn't break
            var displayAllowed = allowedVals.map(function(v) { return v != null ? v : 0; });
            traces.push({
                type: "bar",
                y: labels,
                x: displayAllowed,
                name: "Allowed",
                orientation: "h",
                marker: {
                    color: hexToRgba(allowedColor, 0.45),
                    line: {color: allowedColor, width: 1}
                },
                hovertemplate: "%{y}<br>Allowed: %{x:,.1f}" + tickSuffix + "<extra></extra>",
                hoverlabel: {bgcolor: "#E8ECEF", font: {color: "#333"}}
            });
        }

        traces.push({
            type: "bar",
            y: labels,
            x: actualVals,
            name: "Actual",
            orientation: "h",
            marker: {
                color: actualColors,
                line: {color: rowColors, width: 1}
            },
            customdata: counts,
            hovertemplate: "%{y}<br>Actual: %{x:,.1f}" + tickSuffix + "  (n=%{customdata:,})<extra></extra>",
            hoverlabel: {bgcolor: rowColors, font: {color: "white"}}
        });

        // Dynamic height based on row count
        var barHeight = nRows === 1 ? 80 : 38;
        var chartHeight = Math.max(200, nRows * barHeight + 80);

        var layout = {
            xaxis: {
                showgrid: true,
                gridcolor: "#F0F0F0",
                gridwidth: 1,
                zeroline: false,
                ticksuffix: tickSuffix,
                title: {text: "Median Time", font: {size: 11, color: "#9CA3AF"}}
            },
            yaxis: {
                autorange: true,
                showgrid: false,
                automargin: true
            },
            barmode: "group",
            bargap: 0.25,
            bargroupgap: 0.15,
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            margin: {l: 10, r: 16, t: 28, b: 40},
            height: chartHeight,
            showlegend: hasAnyAllowed,
            legend: {
                orientation: "h",
                y: 1.02,
                x: 0,
                xanchor: "left",
                yanchor: "bottom",
                font: {size: 11},
                tracegroupgap: 0,
                itemwidth: 30
            },
            hovermode: "closest"
        };

        return {data: traces, layout: layout};
    }
};
