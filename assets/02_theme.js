/* Theme swap for Plotly charts + AG Grid + Mapbox.
 *
 * CSS variables already handle DMC components and our custom CSS.
 * Plotly figures serialize color values into their JSON, so they
 * need runtime patching. This file:
 *   1. Watches <html data-theme> for changes
 *   2. On change, re-layouts every Plotly chart with theme-aware colors
 *   3. Toggles AG Grid class (ag-theme-alpine <-> ag-theme-alpine-dark)
 *   4. Updates Mapbox style to a dark variant
 */

(function() {
    var LIGHT = {
        paper:     '#FFFFFF',
        plot:      '#FFFFFF',
        font:      '#1A1A2E',
        grid:      '#F0F0F0',
        axisLine:  '#E0E0E0',
        hoverBg:   '#FFFFFF',
        hoverBord: '#E0E0E0',
        hoverFont: '#1A1A2E',
        mapboxStyle: 'light',
    };

    var DARK = {
        paper:     '#1F222A',
        plot:      '#1F222A',
        font:      '#E6E7EC',
        grid:      '#262932',
        axisLine:  '#2D3039',
        hoverBg:   '#25282F',
        hoverBord: '#2D3039',
        hoverFont: '#E6E7EC',
        mapboxStyle: 'dark',
    };

    // Metric colors that are too dark to read on dark bg when used as
    // annotation font colors. Bidirectional swap lets us restore on theme flip.
    var METRIC_COLOR_LIGHT_TO_DARK = {
        '#7c2a83': '#B866BE',  // PRIMARY (purple)
        '#2196f3': '#64B5F6',  // blue
        '#f44336': '#EF9A9A',  // red
        '#4caf50': '#81C784',  // green
        '#ff9800': '#FFB74D',  // orange
    };
    var METRIC_COLOR_DARK_TO_LIGHT = {};
    Object.keys(METRIC_COLOR_LIGHT_TO_DARK).forEach(function(k) {
        METRIC_COLOR_DARK_TO_LIGHT[METRIC_COLOR_LIGHT_TO_DARK[k].toLowerCase()] = k;
    });
    function remapAnnotationColor(color, theme) {
        if (!color) return null;
        var key = String(color).toLowerCase();
        return theme === 'dark'
            ? (METRIC_COLOR_LIGHT_TO_DARK[key] || null)
            : (METRIC_COLOR_DARK_TO_LIGHT[key] || null);
    }
    function collectAnnotationUpdates(layout, theme) {
        var anns = (layout && layout.annotations) || [];
        var updates = {};
        for (var i = 0; i < anns.length; i++) {
            var ann = anns[i] || {};
            var col = (ann.font && ann.font.color) || null;
            var remapped = remapAnnotationColor(col, theme);
            if (remapped) {
                updates['annotations[' + i + '].font.color'] = remapped;
            }
        }
        return updates;
    }

    function currentTheme() {
        return document.documentElement.getAttribute('data-theme') || 'light';
    }

    function paletteFor(theme) {
        return theme === 'dark' ? DARK : LIGHT;
    }

    function restyleCharts() {
        if (typeof Plotly === 'undefined' || !Plotly.relayout) return;
        var p = paletteFor(currentTheme());

        function buildUpdate(el) {
            // Do NOT touch paper_bgcolor / plot_bgcolor — charts now use
            // rgba(0,0,0,0) and inherit from the themed card via CSS.
            var update = {
                'font.color':            p.font,
                'legend.font.color':     p.font,
                'legend.bgcolor':        'rgba(0,0,0,0)',
                'hoverlabel.bgcolor':    p.hoverBg,
                'hoverlabel.bordercolor':p.hoverBord,
                'hoverlabel.font.color': p.hoverFont,
                'mapbox.style':          p.mapboxStyle,
            };
            var layout = (el && el.layout) || {};
            Object.keys(layout).forEach(function(key) {
                if (/^(x|y)axis\d*$/.test(key)) {
                    update[key + '.gridcolor']        = p.grid;
                    update[key + '.linecolor']        = p.axisLine;
                    update[key + '.zerolinecolor']    = p.grid;
                    update[key + '.tickfont.color']   = p.font;
                    update[key + '.title.font.color'] = p.font;
                }
            });
            // Remap any annotation font colors from our metric palette
            // (e.g. PRIMARY #7C2A83 stays dark on dark bg — use brighter #B866BE).
            Object.assign(update, collectAnnotationUpdates(layout, currentTheme()));
            return update;
        }

        var charts = document.querySelectorAll('.js-plotly-plot');
        charts.forEach(function(el) {
            try { Plotly.relayout(el, buildUpdate(el)); } catch(e) {}
        });
    }

    function restyleGrids() {
        var theme = currentTheme();
        var grids = document.querySelectorAll('.ag-theme-alpine, .ag-theme-alpine-dark');
        grids.forEach(function(el) {
            el.classList.remove('ag-theme-alpine', 'ag-theme-alpine-dark');
            el.classList.add(theme === 'dark' ? 'ag-theme-alpine-dark' : 'ag-theme-alpine');
        });
    }

    function applyTheme() {
        restyleCharts();
        restyleGrids();
    }

    // --- Per-chart Plotly event hooks -----------------------------
    // Each .js-plotly-plot element exposes an `.on(event, handler)` method
    // (injected by plotly.js). Hooking 'plotly_afterplot' catches every
    // redraw — including page re-renders, callback-triggered figure
    // updates, and interactive restyling. This is the definitive fix
    // for the "chart flashes light during nav" problem.
    var hookedCharts = new WeakSet();

    function hookChart(el) {
        if (hookedCharts.has(el)) return;
        if (typeof el.on !== 'function') return;  // Plotly hasn't initialized it yet
        try {
            el.on('plotly_afterplot', function() {
                try {
                    var p = paletteFor(currentTheme());
                    // Infinite-loop guard: relayout triggers afterplot again.
                    // Skip if font.color is already themed (cheap string check
                    // that captures whether our handler has run post-render).
                    var cur = el.layout || {};
                    var curFont = (cur.font && cur.font.color) || '';
                    if (curFont === p.font) return;

                    // Do NOT touch bgs — chart is transparent and inherits
                    // from the themed card via CSS.
                    var update = {
                        'font.color':            p.font,
                        'legend.font.color':     p.font,
                        'legend.bgcolor':        'rgba(0,0,0,0)',
                        'hoverlabel.bgcolor':    p.hoverBg,
                        'hoverlabel.bordercolor':p.hoverBord,
                        'hoverlabel.font.color': p.hoverFont,
                        'mapbox.style':          p.mapboxStyle,
                    };
                    Object.keys(cur).forEach(function(key) {
                        if (/^(x|y)axis\d*$/.test(key)) {
                            update[key + '.gridcolor']        = p.grid;
                            update[key + '.linecolor']        = p.axisLine;
                            update[key + '.zerolinecolor']    = p.grid;
                            update[key + '.tickfont.color']   = p.font;
                            update[key + '.title.font.color'] = p.font;
                        }
                    });
                    Object.assign(update, collectAnnotationUpdates(cur, currentTheme()));
                    Plotly.relayout(el, update);
                } catch(e) {}
            });
            hookedCharts.add(el);
        } catch(e) {}
    }

    function hookAllCharts() {
        document.querySelectorAll('.js-plotly-plot').forEach(hookChart);
    }

    // Initial apply + hook pass — charts may render before or after this
    // script depending on load order, so retry aggressively at first.
    var tries = 0;
    var initInterval = setInterval(function() {
        hookAllCharts();
        applyTheme();
        tries++;
        if (tries > 40) clearInterval(initInterval);
    }, 500);

    // Cheap safety-net: sweep every 2s forever. `hookChart` is idempotent
    // (WeakSet guard) and Plotly.relayout no-ops when values match.
    setInterval(function() {
        hookAllCharts();
        applyTheme();
    }, 2000);

    // Watch for <html data-theme> changes (fired by the toggle callback)
    var observer = new MutationObserver(function(mutations) {
        for (var i = 0; i < mutations.length; i++) {
            if (mutations[i].attributeName === 'data-theme') {
                applyTheme();
                break;
            }
        }
    });
    observer.observe(document.documentElement, { attributes: true });

    // Re-apply + hook whenever a new chart enters the DOM
    var chartObserver = new MutationObserver(function(mutations) {
        for (var i = 0; i < mutations.length; i++) {
            var added = mutations[i].addedNodes;
            for (var j = 0; j < added.length; j++) {
                var node = added[j];
                if (node.nodeType !== 1) continue;
                var isChart = node.classList && node.classList.contains('js-plotly-plot');
                var hasChart = node.querySelector && node.querySelector('.js-plotly-plot');
                if (isChart || hasChart) {
                    hookAllCharts();
                    restyleCharts();
                    return;
                }
            }
        }
    });
    chartObserver.observe(document.body, { childList: true, subtree: true });

    // Expose for debugging
    window._rcApplyTheme = applyTheme;
    window._rcHookCharts = hookAllCharts;
})();
