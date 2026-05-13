/**
 * billing_deferred.js — Billing-specific wrappers around chartDeferred.
 *
 * Core logic lives in assets/00_chart_deferred.js. This file keeps the
 * billing-specific helpers that build the figure (renderTrend / renderCum)
 * and delegates final placeholder/enqueue to chartDeferred.wrap().
 */
(function () {
    "use strict";

    window.dash_clientside = window.dash_clientside || {};
    var NO = window.dash_clientside.no_update;

    window.dash_clientside.billingDeferred = {

        renderTrend: function (chartId, storeData, sliceMode, agg,
                               smoothPct, chartType, stackVal) {
            if (!storeData) return NO;
            var slice = storeData[sliceMode || "category"];
            if (!slice) return NO;
            var raw = slice[agg || "M"];
            if (!raw) return NO;

            var fig = window.dash_clientside.census.smoothChartWithType(
                raw, smoothPct, chartType, null, stackVal
            );
            if (fig && fig.layout && fig.layout.margin) fig.layout.margin.l = 36;
            return window.dash_clientside.chartDeferred.wrap(chartId, fig, true);
        },

        renderCum: function (chartId, rawData, smoothPct, chartType,
                             stackVal, maxPrior, projectOn) {
            if (!rawData) return NO;

            if (projectOn === false) {
                rawData = JSON.parse(JSON.stringify(rawData));
                if (rawData.current) delete rawData.current.projection;
                delete rawData.projectionTotal;
            }
            var fig = window.dash_clientside.cumulative.renderCumulative(
                rawData, smoothPct, chartType, null, stackVal, maxPrior
            );
            if (fig && fig.layout && fig.layout.margin) fig.layout.margin.l = 36;
            return window.dash_clientside.chartDeferred.wrap(chartId, fig, true);
        }
    };
})();
