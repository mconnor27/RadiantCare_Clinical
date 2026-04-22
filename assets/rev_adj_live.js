// Real-time drag handler for the revenue-adjustments Realization Factor
// and A/R Lag sliders. Bypasses Dash callbacks entirely during a drag:
//
// 1. Small Dash clientside callbacks mirror the relevant state onto
//    `window._revAdjCache` whenever the store / other sliders change.
// 2. On pointerdown over one of the two sliders we start a rAF loop
//    that reads the thumb's current aria-valuenow, recomputes traces
//    via window._revAdjCompute, and calls Plotly.react in place.
// 3. On pointerup we stop the loop. Dash picks up the final value via
//    the slider's updatemode="mouseup" and the debounced callback
//    performs any server-side sync if needed.
(function () {
    var rafId = null;
    var activeSelector = null;
    var lastR = null, lastLag = null;

    function getThumbVal(containerSelector) {
        var container = document.querySelector(containerSelector);
        if (!container) return null;
        var thumb = container.querySelector('[role="slider"]');
        if (!thumb) return null;
        var v = thumb.getAttribute('aria-valuenow');
        return v == null ? null : parseFloat(v);
    }

    function render() {
        if (!window._revAdjCache || !window._revAdjCache.store
            || !window._revAdjCompute || !window.Plotly) return;

        var cache = window._revAdjCache;
        var rNow = getThumbVal('#billing-rev-adj-realization');
        var lagNow = getThumbVal('#billing-rev-adj-ar-lag');
        if (rNow == null) rNow = cache.realization;
        if (lagNow == null) lagNow = cache.ar_lag;

        // Early out — no change since last frame.
        if (rNow === lastR && lagNow === lastLag) return;
        lastR = rNow; lastLag = lagNow;

        var c = window._revAdjCompute(
            cache.store, rNow, cache.smooth, lagNow, cache.enabled, cache.mults
        );
        if (!c) return;

        var wrap = document.getElementById('billing-rev-adj-plot');
        if (!wrap) return;
        var el = wrap.classList && wrap.classList.contains('js-plotly-plot')
            ? wrap
            : wrap.querySelector('.js-plotly-plot');
        if (!el || !el.data) return;

        var newData = el.data.map(function (tr) {
            var nm = tr.name || '';
            if (nm.indexOf('Estimated') === 0) {
                return Object.assign({}, tr, { x: c.est_x, y: c.est_y });
            }
            if (nm.indexOf('Actual') === 0) {
                return Object.assign({}, tr, { x: c.act_x, y: c.act_y });
            }
            return tr;
        });
        try {
            window.Plotly.react(el, newData, el.layout || {},
                Object.assign({}, el.config || {},
                    { displayModeBar: false, responsive: false }));
        } catch (e) {
            // Plotly sometimes throws mid-drag if the DOM mutates; just
            // swallow and try again next frame.
        }
    }

    function loop() {
        render();
        rafId = requestAnimationFrame(loop);
    }

    function start() {
        if (rafId !== null) return;
        lastR = null; lastLag = null;
        rafId = requestAnimationFrame(loop);
    }

    function stop() {
        if (rafId !== null) {
            cancelAnimationFrame(rafId);
            rafId = null;
            render();  // one final commit
        }
        activeSelector = null;
    }

    // Delegate pointerdown across the document — the sliders may mount
    // and unmount as the user opens/closes the modal.
    document.addEventListener('pointerdown', function (e) {
        var inRealization = e.target.closest && e.target.closest('#billing-rev-adj-realization');
        var inLag = e.target.closest && e.target.closest('#billing-rev-adj-ar-lag');
        if (inRealization || inLag) {
            activeSelector = inRealization ? '#billing-rev-adj-realization' : '#billing-rev-adj-ar-lag';
            start();
        }
    });
    document.addEventListener('pointerup', stop);
    document.addEventListener('pointercancel', stop);
})();
