/**
 * Global loading overlay manager for RadiantCare Clinical Dashboard.
 *
 * Shows a fixed overlay on initial page load and page navigation.
 * Hides it once Dash callbacks have completed (content is rendered).
 *
 * Detection strategy:
 *   1. Watch for _dash-loading class (Dash adds this during callbacks)
 *   2. Track state: WAITING → LOADING → hide overlay
 *   3. Also check for rendered Plotly charts / AG Grid rows as a signal
 *   4. Fallback timeout so the overlay never gets stuck
 */
(function () {
    var POLL_MS = 100;
    var MAX_WAIT_MS = 15000;
    var FADE_MS = 300;
    var pollTimer = null;

    function getOverlay() {
        return document.getElementById("global-loading-overlay");
    }

    function hide() {
        var el = getOverlay();
        if (!el || el.dataset.state === "hidden") return;
        el.dataset.state = "hidden";
        el.style.transition = "opacity " + FADE_MS + "ms ease";
        el.style.opacity = "0";
        setTimeout(function () {
            el.style.display = "none";
        }, FADE_MS);
    }

    function show() {
        var el = getOverlay();
        if (!el) return;
        el.dataset.state = "visible";
        el.style.transition = "none";
        el.style.display = "flex";
        // Force reflow so the display change takes effect before opacity
        void el.offsetHeight;
        el.style.opacity = "1";
    }

    /** True if any Dash component is currently being updated by a callback. */
    function isDashLoading() {
        return document.querySelectorAll("._dash-loading").length > 0;
    }

    /** True if the page has rendered meaningful content (charts with data, grid rows). */
    function hasRenderedContent() {
        // Plotly charts with data points
        var plots = document.querySelectorAll(".js-plotly-plot");
        for (var i = 0; i < plots.length; i++) {
            var data = plots[i].data;
            if (data && data.length > 0) {
                for (var j = 0; j < data.length; j++) {
                    var t = data[j];
                    if (
                        (t.x && t.x.length > 0) ||
                        (t.y && t.y.length > 0) ||
                        (t.values && t.values.length > 0)
                    ) {
                        return true;
                    }
                }
            }
        }
        // AG Grid rows
        if (document.querySelector(".ag-center-cols-container .ag-row")) return true;
        return false;
    }

    function startPolling() {
        if (pollTimer) clearInterval(pollTimer);
        var t0 = Date.now();
        var sawLoading = false;

        pollTimer = setInterval(function () {
            var elapsed = Date.now() - t0;
            var loading = isDashLoading();

            if (loading) sawLoading = true;

            // Hide when:
            //   a) Saw loading state then it cleared (callbacks completed), OR
            //   b) Content has rendered (covers cached-data fast path), OR
            //   c) Fallback timeout
            if (
                (sawLoading && !loading) ||
                hasRenderedContent() ||
                elapsed > MAX_WAIT_MS
            ) {
                clearInterval(pollTimer);
                pollTimer = null;
                setTimeout(hide, 50);
            }
        }, POLL_MS);
    }

    // Intercept history.pushState so we detect Dash page navigation.
    // Skip the full-screen overlay after first page load — per-chart
    // loading spinners handle subsequent navigations.
    var firstLoadDone = false;

    var origPush = history.pushState;
    history.pushState = function () {
        origPush.apply(this, arguments);
        if (!firstLoadDone) {
            show();
            startPolling();
        }
    };
    window.addEventListener("popstate", function () {
        if (!firstLoadDone) {
            show();
            startPolling();
        }
    });

    // Start polling on initial page load
    var origHide = hide;
    hide = function () {
        origHide();
        firstLoadDone = true;
    };
    startPolling();
})();
