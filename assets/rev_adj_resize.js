// The revenue-adjustments plot runs with Plotly `responsive: false` so
// Plotly's own ResizeObserver can't animate the chart during drift-bar
// toggles or other container-size changes. We manually resize the plot
// once on debounced window resize events.
(function () {
    var pending = null;

    function resizePlot() {
        pending = null;
        if (!window.Plotly) return;
        var wrap = document.getElementById('billing-rev-adj-plot');
        if (!wrap) return;
        var el = wrap.classList.contains('js-plotly-plot')
            ? wrap
            : wrap.querySelector('.js-plotly-plot');
        if (!el) return;
        try { window.Plotly.Plots.resize(el); } catch (e) { /* ignore */ }
    }

    function schedule() {
        if (pending !== null) return;
        pending = setTimeout(resizePlot, 120);
    }

    window.addEventListener('resize', schedule);
})();
