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
        hoverBg:   '#374151',
        hoverBord: '#4B5563',
        hoverFont: '#FFFFFF',
        mapboxStyle: 'dark',
    };

    // Metric colors that are too dark to read on dark bg when used as
    // annotation font colors. Bidirectional swap lets us restore on theme flip.
    // Purple was previously '#E4A7EA' (pastel) — bumped to '#CD8AD0' so the
    // brand purple is uniformly brighter across UI, charts, and annotations
    // in dark mode (matches the bumped CSS --color-primary). The brighter
    // dark-mode value is also used for trace line/marker/fill colors
    // (see remapTraceColor below).
    var METRIC_COLOR_LIGHT_TO_DARK = {
        '#7c2a83': '#CD8AD0',  // PRIMARY (purple)
        '#2196f3': '#64B5F6',  // blue
        '#f44336': '#EF9A9A',  // red
        '#4caf50': '#81C784',  // green
        '#ff9800': '#FFB74D',  // orange
    };
    var METRIC_COLOR_DARK_TO_LIGHT = {};
    Object.keys(METRIC_COLOR_LIGHT_TO_DARK).forEach(function(k) {
        METRIC_COLOR_DARK_TO_LIGHT[METRIC_COLOR_LIGHT_TO_DARK[k].toLowerCase()] = k;
    });
    // Neutral muted-text annotation pair. Applied ONLY to annotation font
    // colors (not to traces, hoverlabel borders, or other places where
    // #4B5563 has independent meaning — e.g. p.hoverBord in dark mode).
    // Lets chart annotations like "n=… Mean: …" appear pure white on the
    // dark Paper background and mid-gray on light, with both directions
    // round-tripping cleanly across theme toggles.
    var ANNOTATION_NEUTRAL_LIGHT_TO_DARK = {'#4b5563': '#ffffff'};
    var ANNOTATION_NEUTRAL_DARK_TO_LIGHT = {'#ffffff': '#4b5563'};
    // RGB triplets of the source colors so we can remap rgba/rgb strings in
    // trace fillcolors and gradient stops — those bake an alpha channel into
    // the CSS-style color string and so don't match the hex map directly.
    var METRIC_RGB = {
        '124,42,131': {dark: '205,138,208', hex: '#7c2a83'},   // PRIMARY
        '33,150,243': {dark: '100,181,246', hex: '#2196f3'},
        '244,67,54':  {dark: '239,154,154', hex: '#f44336'},
        '76,175,80':  {dark: '129,199,132', hex: '#4caf50'},
        '255,152,0':  {dark: '255,183,77',  hex: '#ff9800'},
    };
    var METRIC_RGB_DARK_TO_LIGHT = {};
    Object.keys(METRIC_RGB).forEach(function(rgb) {
        METRIC_RGB_DARK_TO_LIGHT[METRIC_RGB[rgb].dark] = {light: rgb, hex: METRIC_RGB[rgb].hex};
    });
    function remapAnnotationColor(color, theme) {
        if (!color) return null;
        var key = String(color).toLowerCase();
        if (theme === 'dark') {
            return METRIC_COLOR_LIGHT_TO_DARK[key]
                || ANNOTATION_NEUTRAL_LIGHT_TO_DARK[key]
                || null;
        }
        return METRIC_COLOR_DARK_TO_LIGHT[key]
            || ANNOTATION_NEUTRAL_DARK_TO_LIGHT[key]
            || null;
    }
    // Remap a color value that may be either a single string or a per-point
    // array (Plotly accepts both for marker.color, sankey link/node.color,
    // marker.line.color, etc.). Returns the new value (string or array) if
    // any element changed, null otherwise — callers do `if (r) x = r;`.
    function remapTraceColorOrArray(value, theme) {
        if (typeof value === 'string') {
            return remapTraceColor(value, theme);
        }
        if (Array.isArray(value)) {
            var changed = false;
            var out = value.map(function(c) {
                if (typeof c !== 'string') return c;
                var r = remapTraceColor(c, theme);
                if (r) { changed = true; return r; }
                return c;
            });
            return changed ? out : null;
        }
        return null;
    }

    // Remap trace colors (line.color, marker.color, fillcolor, gradient
    // stops). Accepts both hex (#7C2A83) and rgba/rgb strings — fill colors
    // bake the swatch alpha into the string so we can't just hex-swap.
    // Returns null when the color isn't one of our known brand colors.
    function remapTraceColor(color, theme) {
        if (!color || typeof color !== 'string') return null;
        var hex = color.toLowerCase();
        // Hex form
        if (hex.charAt(0) === '#') {
            return theme === 'dark'
                ? (METRIC_COLOR_LIGHT_TO_DARK[hex] || null)
                : (METRIC_COLOR_DARK_TO_LIGHT[hex] || null);
        }
        // rgba(r,g,b,a) / rgb(r,g,b) — extract triplet, swap, preserve alpha.
        var m = color.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)$/i);
        if (!m) return null;
        var triplet = m[1] + ',' + m[2] + ',' + m[3];
        var alpha = m[4];
        var swap = null;
        if (theme === 'dark' && METRIC_RGB[triplet]) {
            swap = METRIC_RGB[triplet].dark;
        } else if (theme === 'light' && METRIC_RGB_DARK_TO_LIGHT[triplet]) {
            swap = METRIC_RGB_DARK_TO_LIGHT[triplet].light;
        }
        if (!swap) return null;
        return alpha != null
            ? 'rgba(' + swap + ', ' + alpha + ')'
            : 'rgb(' + swap + ')';
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

        // Directly mutate the chart's live layout object and force a redraw.
        // Using Plotly.relayout with nested dot-paths was unreliable here —
        // some charts (e.g. flow_gantt distribution/trend) kept their old
        // gridcolor/linecolor after toggle until a full page reload.
        // Mutating the layout in place + Plotly.redraw guarantees the axis
        // paths get repainted with the new theme colors.
        function applyThemeToLayout(L) {
            if (!L) return;
            if (L.font) L.font.color = p.font;
            else L.font = {color: p.font};
            if (L.legend) {
                if (L.legend.font) L.legend.font.color = p.font;
                else L.legend.font = {color: p.font};
                L.legend.bgcolor = 'rgba(0,0,0,0)';
            }
            if (L.hoverlabel && !L.hoverlabel._preserve) {
                L.hoverlabel.bgcolor = p.hoverBg;
                L.hoverlabel.bordercolor = p.hoverBord;
                if (L.hoverlabel.font) L.hoverlabel.font.color = p.hoverFont;
                else L.hoverlabel.font = {color: p.hoverFont};
            }
            // INTENTIONALLY NOT swapping L.mapbox.style on theme change.
            // Mapbox-gl reacts to style changes by tearing down the WebGL
            // canvas, re-downloading the new style + tile set, and re-tiling
            // synchronously inside Plotly.redraw — this hard-freezes Safari
            // on the patients page (mapbox layer + many DMC components).
            // The page bg is transparent so the tile-style mismatch in dark
            // mode is minor; we accept lighter tiles to keep dark mode usable.
            // if (L.mapbox) L.mapbox.style = p.mapboxStyle;

            Object.keys(L).forEach(function(key) {
                if (/^(x|y)axis\d*$/.test(key)) {
                    var ax = L[key];
                    if (!ax || typeof ax !== 'object') return;
                    ax.gridcolor = p.grid;
                    ax.linecolor = p.axisLine;
                    ax.zerolinecolor = p.grid;
                    if (ax.tickfont) ax.tickfont.color = p.font;
                    else ax.tickfont = {color: p.font};
                    if (ax.title && typeof ax.title === 'object') {
                        if (ax.title.font) ax.title.font.color = p.font;
                        else ax.title.font = {color: p.font};
                    }
                }
            });

            // Remap any annotation font/bg/border colors from our metric
            // palette (e.g. PRIMARY #7C2A83 stays dark on dark bg — use
            // brighter dark-mode variant).
            var theme = currentTheme();
            var anns = L.annotations || [];
            for (var i = 0; i < anns.length; i++) {
                var ann = anns[i];
                if (!ann) continue;
                if (ann.font && ann.font.color) {
                    var fr = remapAnnotationColor(ann.font.color, theme);
                    if (fr) ann.font.color = fr;
                }
                if (typeof ann.bgcolor === 'string') {
                    var br = remapTraceColor(ann.bgcolor, theme);
                    if (br) ann.bgcolor = br;
                }
                if (typeof ann.bordercolor === 'string') {
                    var bdr = remapTraceColor(ann.bordercolor, theme);
                    if (bdr) ann.bordercolor = bdr;
                }
            }
            // Layout shapes — reference lines, fill regions, etc. Many pages
            // draw a brand-purple shape to indicate a benchmark or threshold.
            // Skip the hours-calendar / ops-heatmap shapes whose colors are
            // already managed by their own restyle helpers below.
            var shapes = L.shapes || [];
            for (var si = 0; si < shapes.length; si++) {
                var sh = shapes[si];
                if (!sh) continue;
                if (sh.line && typeof sh.line.color === 'string') {
                    var sr = remapTraceColor(sh.line.color, theme);
                    if (sr) sh.line.color = sr;
                }
                if (typeof sh.fillcolor === 'string') {
                    var sfr = remapTraceColor(sh.fillcolor, theme);
                    if (sfr) sh.fillcolor = sfr;
                }
            }
        }

        // Walk a chart's traces and remap any of our brand colors (purple,
        // blue, red, green, orange) to their theme-aware variants. Handles
        // hex-string colors (line.color, marker.color) and rgba strings
        // (fillcolor, fillgradient.colorscale entries) — fill colors bake an
        // alpha into the string so a hex-only swap would miss them.
        function applyThemeToTraces(data, theme) {
            if (!Array.isArray(data)) return;
            data.forEach(function(trace) {
                if (!trace || typeof trace !== 'object') return;
                // Bars/histograms keep their raw brand color in dark mode —
                // the deep purple/red/etc. reads as a richer "filled" bar
                // against the dark Paper bg, while the bumped pastel
                // variants washed bars out and lost their brand association.
                // Line/area still get remapped so the trace stays legible.
                var isBar = trace.type === 'bar' || trace.type === 'histogram';
                // Single-color props: line.color, fillcolor (always strings).
                if (trace.line && typeof trace.line.color === 'string') {
                    var r = remapTraceColor(trace.line.color, theme);
                    if (r) trace.line.color = r;
                }
                if (typeof trace.fillcolor === 'string') {
                    var r = remapTraceColor(trace.fillcolor, theme);
                    if (r) trace.fillcolor = r;
                }
                // Marker color — string OR per-point array (e.g. one bar
                // per dimension where each bar has its own brand color).
                if (trace.marker && !isBar) {
                    var mr = remapTraceColorOrArray(trace.marker.color, theme);
                    if (mr) trace.marker.color = mr;
                    if (trace.marker.line) {
                        var mlr = remapTraceColorOrArray(trace.marker.line.color, theme);
                        if (mlr) trace.marker.line.color = mlr;
                    }
                }
                // Sankey link colors — almost always per-link arrays.
                if (trace.link) {
                    var lkr = remapTraceColorOrArray(trace.link.color, theme);
                    if (lkr) trace.link.color = lkr;
                    // Hover bg can be string or array
                    var lhr = remapTraceColorOrArray(trace.link.hovercolor, theme);
                    if (lhr) trace.link.hovercolor = lhr;
                    if (trace.link.line) {
                        var llr = remapTraceColorOrArray(trace.link.line.color, theme);
                        if (llr) trace.link.line.color = llr;
                    }
                }
                // Sankey node colors — also typically per-node arrays.
                if (trace.node) {
                    var ndr = remapTraceColorOrArray(trace.node.color, theme);
                    if (ndr) trace.node.color = ndr;
                    if (trace.node.line) {
                        var nlr = remapTraceColorOrArray(trace.node.line.color, theme);
                        if (nlr) trace.node.line.color = nlr;
                    }
                }
                if (trace.fillgradient && Array.isArray(trace.fillgradient.colorscale)) {
                    trace.fillgradient.colorscale.forEach(function(stop) {
                        if (Array.isArray(stop) && typeof stop[1] === 'string') {
                            var r = remapTraceColor(stop[1], theme);
                            if (r) stop[1] = r;
                        }
                    });
                }
                if (trace.textfont && typeof trace.textfont.color === 'string') {
                    // textfont (bar labels etc.) needs the same swap menu as
                    // annotations: brand colors AND the neutral mid-gray pair.
                    var r = remapAnnotationColor(trace.textfont.color, theme);
                    if (!r) r = remapTraceColor(trace.textfont.color, theme);
                    if (r) trace.textfont.color = r;
                }
                if (trace.hoverlabel) {
                    if (typeof trace.hoverlabel.bgcolor === 'string') {
                        var r = remapTraceColor(trace.hoverlabel.bgcolor, theme);
                        if (r) trace.hoverlabel.bgcolor = r;
                    }
                    if (typeof trace.hoverlabel.bordercolor === 'string') {
                        var r = remapTraceColor(trace.hoverlabel.bordercolor, theme);
                        if (r) trace.hoverlabel.bordercolor = r;
                    }
                }
            });
        }

        var charts = document.querySelectorAll('.js-plotly-plot');
        var theme = currentTheme();
        charts.forEach(function(el) {
            try {
                // Skip mapbox-backed charts entirely. Plotly.redraw on a
                // Scattermapbox/Choroplethmapbox trace triggers a synchronous
                // mapbox-gl restyle that hard-freezes Safari. The map stays
                // in its initial light styling in dark mode — acceptable.
                if (el.layout && el.layout.mapbox) return;
                // Skip if already on the current theme AND the traces don't
                // still carry the wrong-theme brand colors. The
                // tracesNeedRemap guard catches the case where
                // _rcThemeApplied was set when the chart was still empty
                // (no data populated yet), so the marker is misleading and
                // the chart actually needs a fresh remap pass.
                if (el._rcThemeApplied === theme
                    && !tracesNeedRemap(el.data, theme)) return;
                applyThemeToLayout(el.layout);
                applyThemeToTraces(el.data, theme);
                Plotly.redraw(el);
                el._rcThemeApplied = theme;
            } catch(e) {}
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

    // Hours-calendar shapes (gridlines + day separators) bake their colors
    // in at build time. Restyle them on theme change so they track dark/light.
    function restyleHoursCalendar() {
        if (typeof Plotly === 'undefined' || !Plotly.relayout) return;
        var isDark = currentTheme() === 'dark';
        var hourGridColor = isDark ? "rgba(140,145,160,0.08)" : "#E5E7EB";
        var daySepColor   = isDark ? "rgba(140,145,160,0.14)" : "#E5E7EB";
        var wrappers = document.querySelectorAll('[id$="-chart-hours"]');
        wrappers.forEach(function(wrap) {
            var el = wrap.querySelector('.js-plotly-plot');
            if (!el || !el.layout || !el.layout.shapes) return;
            var updates = {};
            el.layout.shapes.forEach(function(shape, idx) {
                if (!shape || shape.type !== 'line' || !shape.line) return;
                // Horizontal gridline: y0 === y1
                if (shape.y0 === shape.y1) {
                    updates['shapes[' + idx + '].line.color'] = hourGridColor;
                }
                // Vertical day separator: x0 === x1
                else if (shape.x0 === shape.x1) {
                    updates['shapes[' + idx + '].line.color'] = daySepColor;
                }
            });
            if (Object.keys(updates).length > 0) {
                try { Plotly.relayout(el, updates); } catch(e) {}
            }
        });
    }

    // Ops schedule/availability heatmap uses shape-based week separators +
    // subplot-group borders. Bake-in colors are light; darken them in dark mode.
    function restyleOpsHeatmap() {
        if (typeof Plotly === 'undefined' || !Plotly.relayout) return;
        var isDark = currentTheme() === 'dark';
        var weekSepColor  = isDark ? "#1F222A" : "#FFFFFF";
        var groupBorderColor = isDark ? "#3A3D46" : "#D1D5DB";
        var wrap = document.getElementById('ops-chart-heatmap');
        if (!wrap) return;
        var el = wrap.querySelector('.js-plotly-plot');
        if (!el || !el.layout || !el.layout.shapes) return;
        var updates = {};
        el.layout.shapes.forEach(function(shape, idx) {
            if (!shape || !shape.line) return;
            if (shape.type === 'line' && shape.x0 === shape.x1) {
                updates['shapes[' + idx + '].line.color'] = weekSepColor;
            } else if (shape.type === 'rect') {
                updates['shapes[' + idx + '].line.color'] = groupBorderColor;
            }
        });
        if (Object.keys(updates).length > 0) {
            try { Plotly.relayout(el, updates); } catch(e) {}
        }
    }

    function applyTheme() {
        restyleCharts();
        restyleGrids();
        restyleHoursCalendar();
        restyleOpsHeatmap();
    }

    // Trace-level invalidation guard. Catches the case where a clientside
    // callback rebuilds the figure with theme-aware layout (font.color,
    // axis colors) but leaves trace colors as the raw light-mode brand hex
    // straight from the Store — e.g. census_chart.js smoothChartWithType
    // passes s.color through unchanged. Returns true if any trace has a
    // color that maps to the *other* theme, meaning it still needs remap.
    function tracesNeedRemap(data, theme) {
        if (!Array.isArray(data)) return false;
        var unremapped = theme === 'dark'
            ? METRIC_COLOR_LIGHT_TO_DARK
            : METRIC_COLOR_DARK_TO_LIGHT;
        for (var i = 0; i < data.length; i++) {
            var trace = data[i];
            if (!trace) continue;
            // Bars/histograms intentionally keep their raw brand color in
            // dark mode (see applyThemeToTraces). Don't flag them as needing
            // remap or we get an infinite Plotly.redraw → afterplot loop.
            var isBar = trace.type === 'bar' || trace.type === 'histogram';
            if (trace.line && typeof trace.line.color === 'string'
                && unremapped[trace.line.color.toLowerCase()]) return true;
            if (!isBar && trace.marker && typeof trace.marker.color === 'string'
                && unremapped[trace.marker.color.toLowerCase()]) return true;
        }
        return false;
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
                    var theme = currentTheme();
                    var p = paletteFor(theme);
                    var cur = el.layout || {};
                    var curFont = (cur.font && cur.font.color) || '';
                    // If this redraw was produced by a clientside callback
                    // that baked in the wrong theme colors, invalidate the
                    // applied-theme marker so restyleCharts will pick it up
                    // on the next sweep (or mutation-observer firing).
                    // The font check catches callbacks that ignore theme
                    // entirely; the trace check catches callbacks that ARE
                    // layout-theme-aware but pass through raw brand colors
                    // for line/marker (e.g. smoothChartWithType).
                    if (curFont !== p.font || tracesNeedRemap(el.data, theme)) {
                        el._rcThemeApplied = null;
                        // Kick off an immediate restyle so the user doesn't
                        // have to wait for the 2s sweep.
                        restyleCharts();
                    }
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

    // --- Page-route tagging -------------------------------------------------
    // Tag <html data-page="..."> with the current top-level route so page-
    // specific CSS can target it. Used today to un-fix the global controls
    // strip on pages (e.g. /operations) that don't have a sticky filter bar
    // to anchor the icons against.
    function pageFromPath() {
        var p = (location && location.pathname) || '/';
        p = p.replace(/^\/+/, '').replace(/\/.*$/, '');
        return p || 'home';
    }
    function syncPageAttr() {
        document.documentElement.setAttribute('data-page', pageFromPath());
    }
    syncPageAttr();
    window.addEventListener('popstate', syncPageAttr);
    // Dash pages navigate via history.pushState rather than full reloads;
    // wrap it so we catch SPA route changes.
    var _origPush = history.pushState;
    history.pushState = function() {
        var r = _origPush.apply(this, arguments);
        syncPageAttr();
        return r;
    };
})();
