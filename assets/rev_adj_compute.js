// Shared compute helper for the billing revenue-adjustments plot.
// Used by both the main-rebuild clientside callback and the fast-path
// Plotly.restyle callback so they produce identical output.
(function () {
    // Least-squares fit helpers for the Auto-fit menu.
    // Find the best realization (closed-form) for a given est/act cumulative pair.
    window._revAdjFitBestR = function (est_x, est_y, act_x, act_y) {
        var estMap = {};
        for (var i = 0; i < est_x.length; i++) estMap[est_x[i]] = est_y[i];
        var sumEA = 0, sumE2 = 0, sumA2 = 0, matched = 0;
        for (var i = 0; i < act_x.length; i++) {
            var e = estMap[act_x[i]];
            if (e !== undefined) {
                var a = act_y[i];
                sumEA += e * a;
                sumE2 += e * e;
                sumA2 += a * a;
                matched++;
            }
        }
        if (matched < 2 || sumE2 === 0) return null;
        return {
            r: sumEA / sumE2,
            ssr: sumA2 - (sumEA * sumEA) / sumE2,
        };
    };

    // SSR at a fixed realization r — used when fitting lag alone.
    window._revAdjSsrAtR = function (est_x, est_y, act_x, act_y, r) {
        var estMap = {};
        for (var i = 0; i < est_x.length; i++) estMap[est_x[i]] = est_y[i];
        var total = 0, matched = 0;
        for (var i = 0; i < act_x.length; i++) {
            var e = estMap[act_x[i]];
            if (e !== undefined) {
                var diff = r * e - act_y[i];
                total += diff * diff;
                matched++;
            }
        }
        return matched >= 2 ? total : null;
    };

    window._revAdjClampPct = function (x) {
        var p = Math.round(x * 100);
        if (p < 0) p = 0;
        if (p > 100) p = 100;
        return p;
    };

    // Fit an est/act cumulative pair after re-basing both series to zero at
    // their start (so the fit reflects local slope, not accumulated history).
    function _fitLocal(est_x, est_y, act_x, act_y) {
        if (est_y.length < 3 || act_y.length < 3) return null;
        var eStart = est_y[0], aStart = act_y[0];
        var eY0 = est_y.map(function (v) { return v - eStart; });
        var aY0 = act_y.map(function (v) { return v - aStart; });
        return window._revAdjFitBestR(est_x, eY0, act_x, aY0);
    }

    // Slice (est, act) series by date range [startDate, endDate] inclusive.
    function _slice(est_x, est_y, act_x, act_y, startDate, endDate) {
        var eX = [], eY = [], aX = [], aY = [];
        for (var i = 0; i < est_x.length; i++) {
            if (est_x[i] >= startDate && est_x[i] <= endDate) {
                eX.push(est_x[i]); eY.push(est_y[i]);
            }
        }
        for (var i = 0; i < act_x.length; i++) {
            if (act_x[i] >= startDate && act_x[i] <= endDate) {
                aX.push(act_x[i]); aY.push(act_y[i]);
            }
        }
        return { eX: eX, eY: eY, aX: aX, aY: aY };
    }

    // Find the best single split inside [s, e] (inclusive) — the split index
    // within act_x that most reduces the combined SSR of the two halves.
    // Returns { split_date, improvement, left, right } or null.
    function _bestSplit(est_x, est_y, act_x, act_y) {
        var parent = _fitLocal(est_x, est_y, act_x, act_y);
        if (!parent || parent.ssr <= 0) return null;
        var best = null;
        var n = act_x.length;
        var minSide = Math.max(8, Math.round(n * 0.12));
        for (var i = minSide; i <= n - minSide; i++) {
            var splitDate = act_x[i];
            // Slice by date (est dates may be offset from act).
            var L = _slice(est_x, est_y, act_x.slice(0, i + 1), act_y.slice(0, i + 1),
                           act_x[0], splitDate);
            var R = _slice(est_x, est_y, act_x.slice(i), act_y.slice(i),
                           splitDate, act_x[n - 1]);
            // Use direct slices for the act side
            L.aX = act_x.slice(0, i + 1); L.aY = act_y.slice(0, i + 1);
            R.aX = act_x.slice(i);        R.aY = act_y.slice(i);
            var fL = _fitLocal(L.eX, L.eY, L.aX, L.aY);
            var fR = _fitLocal(R.eX, R.eY, R.aX, R.aY);
            if (!fL || !fR) continue;
            var ssr = fL.ssr + fR.ssr;
            if (!best || ssr < best.ssr) {
                best = {
                    split_idx: i,
                    split_date: splitDate,
                    ssr: ssr,
                    improvement: (parent.ssr - ssr) / parent.ssr,
                    left: { x: L, y: null, fit: fL },
                    right: { x: R, y: null, fit: fR },
                };
            }
        }
        return best;
    }

    // Recursive binary segmentation. Splits only when a split reduces
    // SSR by at least `minImprovement` AND each half is at least minSize
    // points long. Returns array of split dates (not including endpoints).
    function _binarySegment(est_x, est_y, act_x, act_y, minImprovement, maxDepth, depth) {
        depth = depth || 0;
        if (depth >= maxDepth) return [];
        if (act_x.length < 20) return [];
        var b = _bestSplit(est_x, est_y, act_x, act_y);
        if (!b || b.improvement < minImprovement) return [];
        var leftActX = act_x.slice(0, b.split_idx + 1);
        var leftActY = act_y.slice(0, b.split_idx + 1);
        var leftEst = _slice(est_x, est_y, leftActX, leftActY, act_x[0], b.split_date);
        var rightActX = act_x.slice(b.split_idx);
        var rightActY = act_y.slice(b.split_idx);
        var rightEst = _slice(est_x, est_y, rightActX, rightActY, b.split_date, act_x[act_x.length - 1]);
        var leftSplits = _binarySegment(
            leftEst.eX, leftEst.eY, leftActX, leftActY, minImprovement, maxDepth, depth + 1
        );
        var rightSplits = _binarySegment(
            rightEst.eX, rightEst.eY, rightActX, rightActY, minImprovement, maxDepth, depth + 1
        );
        return leftSplits.concat([b.split_date]).concat(rightSplits);
    }

    // Segment-wise realization fit using binary segmentation. Only returns
    // segments when the data actually justifies a split (SSR improves by
    // at least `minImprovementPct`% at each cut).
    window._revAdjSegmentFit = function (
        store, smooth, ar_lag, enabled, mults,
        sensitivityPct, thresholdPct
    ) {
        if (!store || !window._revAdjCompute || !window._revAdjFitBestR) return null;
        var c = window._revAdjCompute(store, 100, smooth, ar_lag, enabled, mults);
        if (!c || !c.est_x.length || c.act_x.length < 20) return null;

        var globalFit = window._revAdjFitBestR(c.est_x, c.est_y, c.act_x, c.act_y);
        if (!globalFit) return null;
        var globalR = globalFit.r;

        // Binary segmentation parameters (sensitivity = required SSR
        // reduction at each cut, as a fraction).
        var MIN_IMPROVEMENT = (sensitivityPct != null ? sensitivityPct : 15) / 100;
        var MAX_DEPTH = 3;

        var splits = _binarySegment(
            c.est_x, c.est_y, c.act_x, c.act_y, MIN_IMPROVEMENT, MAX_DEPTH
        );
        splits.sort();

        // Build segments from the discovered split dates.
        var boundaries = [c.act_x[0]].concat(splits).concat([c.act_x[c.act_x.length - 1]]);
        var segs = [];
        for (var s = 0; s < boundaries.length - 1; s++) {
            var segStart = boundaries[s];
            var segEnd = boundaries[s + 1];
            var sl = _slice(c.est_x, c.est_y, c.act_x, c.act_y, segStart, segEnd);
            if (sl.eX.length < 3 || sl.aX.length < 3) continue;
            var fit = _fitLocal(sl.eX, sl.eY, sl.aX, sl.aY);
            if (!fit) continue;
            var rPct = window._revAdjClampPct(fit.r);
            segs.push({
                start: segStart,
                end: segEnd,
                r: fit.r,
                r_pct: rPct,
                mid: sl.aX[Math.floor(sl.aX.length / 2)],
                drift: rPct - window._revAdjClampPct(globalR),
            });
        }
        return {
            global_r_pct: window._revAdjClampPct(globalR),
            threshold_pct: thresholdPct,
            segments: segs,
            split_dates: splits,
        };
    };

    // Apply / clear segment-drift overlays on the revenue-adjustments plot.
    // Annotations stagger vertically (3 rows) to reduce overlap when
    // segment midpoints fall close together.
    window._revAdjOverlaySegments = function (analysis) {
        if (!window.Plotly) return;
        var wrap = document.getElementById('billing-rev-adj-plot');
        if (!wrap) return;
        var el = wrap.classList && wrap.classList.contains('js-plotly-plot')
            ? wrap
            : wrap.querySelector('.js-plotly-plot');
        if (!el) return;

        if (!analysis) {
            try {
                var layout = el.layout || {};
                var keepShapes = (layout.shapes || []).filter(function (s) {
                    return !s || !s.name || String(s.name).indexOf('rev-adj-drift') !== 0;
                });
                var keepAnns = (layout.annotations || []).filter(function (a) {
                    return !a || !a.name || String(a.name).indexOf('rev-adj-drift') !== 0;
                });
                window.Plotly.relayout(el, {
                    shapes: keepShapes, annotations: keepAnns,
                });
            } catch (e) { /* ignore */ }
            return;
        }

        var shapes = [];
        var annotations = [];
        var thr = analysis.threshold_pct || 3;
        // All labels on a single row INSIDE the plot, near the top.
        var LABEL_Y = 0.94;

        analysis.segments.forEach(function (seg, idx) {
            var flagged = Math.abs(seg.drift) >= thr;
            if (idx < analysis.segments.length - 1) {
                shapes.push({
                    name: 'rev-adj-drift-sep',
                    type: 'line',
                    xref: 'x', yref: 'paper',
                    x0: seg.end, x1: seg.end, y0: 0, y1: 1,
                    line: {
                        color: flagged || Math.abs(analysis.segments[idx + 1].drift) >= thr
                            ? 'rgba(249,115,22,0.55)' : 'rgba(150,150,150,0.45)',
                        width: 1.25, dash: 'dot',
                    },
                });
            }
            var text = '<b>' + seg.r_pct + '%</b>';
            if (flagged) {
                text += ' <span style="color:#F97316">' +
                    (seg.drift > 0 ? '+' : '') + seg.drift + '</span>';
            }
            annotations.push({
                name: 'rev-adj-drift-label-' + idx,
                x: seg.mid,
                y: LABEL_Y,
                xref: 'x', yref: 'paper',
                xanchor: 'center', yanchor: 'middle',
                text: text,
                showarrow: false,
                font: {
                    size: 11,
                    color: flagged ? '#F97316' : '#374151',
                    family: 'Inter, system-ui, sans-serif',
                },
                bgcolor: 'rgba(255,255,255,0.92)',
                bordercolor: flagged ? '#F97316' : 'rgba(150,150,150,0.35)',
                borderwidth: 1,
                borderpad: 3,
            });
        });

        try {
            window.Plotly.relayout(el, {
                shapes: shapes,
                annotations: annotations,
            });
        } catch (e) { /* ignore */ }
    };

    window._revAdjFlashAuto = function (label) {
        var btn = document.getElementById('billing-rev-adj-auto-realization');
        if (!btn) return;
        var labelEl = btn.querySelector('.mantine-Button-label') || btn;
        var original = labelEl.innerText || 'Auto';
        labelEl.innerText = label;
        btn.classList.add('auto-fit-flash');
        setTimeout(function () {
            labelEl.innerText = original;
            btn.classList.remove('auto-fit-flash');
        }, 1800);
    };

    window._revAdjCompute = function (store, realization, smooth, lag, enabled, mults) {
        if (!store || store.error) return null;
        var r = (realization == null ? 90 : realization) / 100;
        var w = (smooth == null ? 0 : parseInt(smooth, 10));
        var lagN = (lag == null ? 0 : parseInt(lag, 10));
        var cats = [
            "Medicare", "Medicaid", "Private", "Military/VA",
            "Workers Comp", "Tribal/IHS", "Self Pay", "Other/Unknown",
        ];
        function smoothArr(arr, win) {
            if (!win || win <= 1) return arr;
            var n = arr.length, out = new Array(n);
            var half = Math.floor(win / 2);
            for (var i = 0; i < n; i++) {
                var lo = Math.max(0, i - half);
                var hi = Math.min(n - 1, i + half);
                var s = 0, c = 0;
                for (var j = lo; j <= hi; j++) { s += arr[j]; c++; }
                out[i] = s / c;
            }
            return out;
        }
        function shiftDays(dateStr, days) {
            var d = new Date(dateStr + "T00:00:00Z");
            d.setUTCDate(d.getUTCDate() + days);
            var y = d.getUTCFullYear();
            var m = String(d.getUTCMonth() + 1).padStart(2, "0");
            var dd = String(d.getUTCDate()).padStart(2, "0");
            return y + "-" + m + "-" + dd;
        }
        function subsample(xs, ys, maxPts) {
            var n = xs.length;
            if (n <= maxPts) return [xs, ys];
            var stride = Math.ceil(n / maxPts);
            var xo = [], yo = [];
            for (var i = 0; i < n; i += stride) { xo.push(xs[i]); yo.push(ys[i]); }
            if (xo[xo.length - 1] !== xs[n - 1]) {
                xo.push(xs[n - 1]); yo.push(ys[n - 1]);
            }
            return [xo, yo];
        }
        var MAX_POINTS = 400;

        var est_x = [], est_y = [];
        if (store.est) {
            var dates = store.est.dates;
            var byCat = store.est.by_category;
            var n = dates.length;
            var daily = new Array(n).fill(0);
            for (var ci = 0; ci < cats.length; ci++) {
                var cat = cats[ci];
                var mm = enabled
                    ? ((mults[cat] == null ? 100 : mults[cat]) / 100)
                    : 1;
                var arr = byCat[cat] || [];
                for (var i = 0; i < n; i++) daily[i] += (arr[i] || 0) * mm;
            }
            var dosStart = shiftDays(store.est.start, -lagN);
            var dosEnd = shiftDays(store.est.end, -lagN);
            var cum = 0;
            for (var i = 0; i < n; i++) {
                if (dates[i] >= dosStart && dates[i] <= dosEnd) {
                    cum += daily[i];
                    est_x.push(lagN === 0 ? dates[i] : shiftDays(dates[i], lagN));
                    est_y.push(cum * r);
                }
            }
            est_y = smoothArr(est_y, w);
            var sub = subsample(est_x, est_y, MAX_POINTS);
            est_x = sub[0]; est_y = sub[1];
        }
        var act_x = [], act_y = [];
        if (store.act) {
            var n2 = store.act.daily.length;
            var ac = new Array(n2);
            var s = 0;
            for (var i = 0; i < n2; i++) { s += store.act.daily[i]; ac[i] = s; }
            ac = smoothArr(ac, w);
            var sub2 = subsample(store.act.dates, ac, MAX_POINTS);
            act_x = sub2[0]; act_y = sub2[1];
        }
        return { est_x: est_x, est_y: est_y, act_x: act_x, act_y: act_y };
    };
})();
