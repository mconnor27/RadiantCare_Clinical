/**
 * Referral Flow-Gantt wrapper.
 * Reuses the core flow_gantt.js _renderSinglePipeline by temporarily
 * swapping the container ID to "wf-flow-gantt" (which the renderer expects),
 * rendering, then restoring the original ID.
 *
 * After rendering, patches the click handlers on flow bands to dispatch
 * selection to "referrals-store-selected-flow" instead of workflow stores.
 *
 * Depends on: flow_gantt.js (must load first — Dash loads assets alphabetically,
 * and "r" > "f" so this loads after flow_gantt.js).
 */
(function() {
    "use strict";

    window.dash_clientside = window.dash_clientside || {};

    window.dash_clientside.referralFlowGantt = {
        render: function(rawData) {
            var container = document.getElementById("referrals-flow-gantt");
            if (!container || !rawData) return window.dash_clientside.no_update;

            // Temporarily rename so the core renderer can find it
            container.id = "wf-flow-gantt";

            try {
                window.dash_clientside.flowGantt._renderSinglePipeline(
                    rawData, false, null
                );
            } finally {
                // Restore original ID
                container.id = "referrals-flow-gantt";
            }

            // ── Patch click handlers to target referrals stores ──────────
            var svg = container.querySelector("svg");
            if (svg) {
                var bands = svg.querySelectorAll(".flow-gantt-band");
                for (var b = 0; b < bands.length; b++) {
                    (function(band, bandIdx) {
                        // Clone to remove old listeners from _renderSinglePipeline
                        var clone = band.cloneNode(true);
                        band.parentNode.replaceChild(clone, band);

                        // Re-attach hover (copy data attrs)
                        clone.addEventListener("mouseenter", function() {
                            clone.style.fill = clone.getAttribute("data-hover-fill");
                            clone.style.stroke = clone.getAttribute("data-hover-stroke");
                            clone.style.strokeWidth = clone.getAttribute("data-hover-stroke-width");
                        });
                        clone.addEventListener("mouseleave", function() {
                            clone.style.fill = clone.getAttribute("data-base-fill");
                            clone.style.stroke = clone.getAttribute("data-base-stroke");
                            clone.style.strokeWidth = clone.getAttribute("data-base-stroke-width");
                        });

                        // Click → toggle selection and dispatch to referrals store
                        clone.addEventListener("click", function(e) {
                            e.stopPropagation();
                            var cur = container.__rfgSelectedFlow;
                            var sel = (cur === bandIdx) ? null : bandIdx;
                            container.__rfgSelectedFlow = sel;

                            // Update band visual highlighting
                            var allBands = svg.querySelectorAll(".flow-gantt-band");
                            for (var i = 0; i < allBands.length; i++) {
                                var ab = allBands[i];
                                var idx = parseInt(ab.getAttribute("data-flow-index"), 10);
                                if (sel === null || sel === undefined) {
                                    ab.style.fill = ab.getAttribute("data-orig-fill");
                                    ab.style.stroke = ab.getAttribute("data-orig-stroke");
                                    ab.style.strokeWidth = ab.getAttribute("data-orig-stroke-width");
                                    ab.style.opacity = "";
                                } else if (idx === sel) {
                                    ab.style.fill = ab.getAttribute("data-hover-fill");
                                    ab.style.stroke = ab.getAttribute("data-hover-stroke");
                                    ab.style.strokeWidth = ab.getAttribute("data-hover-stroke-width");
                                    ab.style.opacity = "";
                                } else {
                                    ab.style.fill = ab.getAttribute("data-orig-fill");
                                    ab.style.stroke = ab.getAttribute("data-orig-stroke");
                                    ab.style.strokeWidth = ab.getAttribute("data-orig-stroke-width");
                                    ab.style.opacity = "0.3";
                                }
                            }

                            // Dispatch to referrals-specific store
                            if (window.dash_clientside && window.dash_clientside.set_props) {
                                window.dash_clientside.set_props(
                                    "referrals-store-selected-flow", {data: sel}
                                );
                            }
                        });
                    })(bands[b], parseInt(bands[b].getAttribute("data-flow-index"), 10));
                }

                // Click SVG background to deselect
                svg.addEventListener("click", function(e) {
                    if (e.target === svg) {
                        container.__rfgSelectedFlow = null;
                        var allBands = svg.querySelectorAll(".flow-gantt-band");
                        for (var i = 0; i < allBands.length; i++) {
                            var ab = allBands[i];
                            ab.style.fill = ab.getAttribute("data-orig-fill");
                            ab.style.stroke = ab.getAttribute("data-orig-stroke");
                            ab.style.strokeWidth = ab.getAttribute("data-orig-stroke-width");
                            ab.style.opacity = "";
                        }
                        if (window.dash_clientside && window.dash_clientside.set_props) {
                            window.dash_clientside.set_props(
                                "referrals-store-selected-flow", {data: null}
                            );
                        }
                    }
                });
            }

            // Store data for resize re-renders
            container.__rfgData = rawData;

            // Set up ResizeObserver (once)
            if (window.ResizeObserver && !container.__rfgRO) {
                var debounce;
                container.__rfgRO = new ResizeObserver(function() {
                    var nw = container.clientWidth;
                    var nh = container.clientHeight;
                    if (nw && nh && (nw !== container.__rfgW || nh !== container.__rfgH)) {
                        clearTimeout(debounce);
                        debounce = setTimeout(function() {
                            window.dash_clientside.referralFlowGantt.render(
                                container.__rfgData
                            );
                        }, 150);
                    }
                });
                container.__rfgRO.observe(container);
            }
            container.__rfgW = container.clientWidth;
            container.__rfgH = container.clientHeight;

            return window.dash_clientside.no_update;
        }
    };
})();
