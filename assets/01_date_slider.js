/**
 * Shared date-slider helpers for filter bars.
 * Each page registers with its own BASE year so slider indices
 * map to the correct calendar dates.
 *
 * Usage (Python):
 *   ClientsideFunction(namespace="cvDateSlider", function_name="syncSlider")
 *
 * Depends on: nothing (standalone).
 */

(function() {
    "use strict";

    var MO = ["Jan","Feb","Mar","Apr","May","Jun",
              "Jul","Aug","Sep","Oct","Nov","Dec"];

    /**
     * Build a {syncSlider} namespace for the given base year and
     * attach a MutationObserver to rewrite slider thumb labels.
     */
    function registerSlider(namespaceName, baseYear, sliderIds) {

        function fmtIdx(idx) {
            return MO[idx % 12] + " " + (baseYear + Math.floor(idx / 12));
        }

        // Rewrite slider thumb labels from raw index → "Mon YYYY"
        var observer = new MutationObserver(function() {
            sliderIds.forEach(function(sid) {
                var el = document.getElementById(sid);
                if (!el) return;
                el.querySelectorAll(".mantine-Slider-label").forEach(function(lbl) {
                    var n = parseInt(lbl.textContent, 10);
                    if (!isNaN(n) && n >= 0 && lbl.textContent === String(n)) {
                        lbl.textContent = fmtIdx(n);
                    }
                });
            });
        });
        document.addEventListener("DOMContentLoaded", function() {
            observer.observe(document.body,
                {childList: true, subtree: true, characterData: true});
        });

        // Register clientside callback namespace
        window.dash_clientside = window.dash_clientside || {};
        window.dash_clientside[namespaceName] = {
            syncSlider: function(sliderVal, curStart, curEnd) {
                if (!sliderVal || sliderVal.length !== 2) {
                    return [window.dash_clientside.no_update,
                            window.dash_clientside.no_update, ""];
                }
                var label = fmtIdx(sliderVal[0]) + "  \u2014  " + fmtIdx(sliderVal[1]);

                var sYear = baseYear + Math.floor(sliderVal[0] / 12);
                var sMonth = sliderVal[0] % 12 + 1;
                var startDate = sYear + "-" + String(sMonth).padStart(2, "0") + "-01";

                var eYear = baseYear + Math.floor(sliderVal[1] / 12);
                var eMonth = sliderVal[1] % 12 + 1;
                var lastDay = new Date(eYear, eMonth, 0).getDate();
                var endDate = eYear + "-" + String(eMonth).padStart(2, "0") + "-"
                            + String(lastDay).padStart(2, "0");

                // Cap end date at today
                var today = new Date();
                var todayStr = today.getFullYear() + "-"
                    + String(today.getMonth() + 1).padStart(2, "0") + "-"
                    + String(today.getDate()).padStart(2, "0");
                if (endDate > todayStr) { endDate = todayStr; }

                if (curStart === startDate && curEnd === endDate) {
                    return [window.dash_clientside.no_update,
                            window.dash_clientside.no_update, label];
                }
                return [startDate, endDate, label];
            }
        };
    }

    // ── Page registrations ───────────────────────────────────────────────
    // Clinic Visits: data goes back to 2004
    registerSlider("cvDateSlider", 2004, ["cv-date-slider"]);

    // Simulations: same BASE_YEAR as Python utils/date_slider.py
    registerSlider("simDateSlider", 2004, ["sim-date-slider"]);

    // Tasks: same BASE_YEAR as Python utils/date_slider.py
    registerSlider("tasksDateSlider", 2004, ["tasks-date-slider"]);

    // OTVs: same BASE_YEAR as Python utils/date_slider.py
    registerSlider("otvsDateSlider", 2004, ["otvs-date-slider"]);

    // Courses: same BASE_YEAR as Python utils/date_slider.py
    registerSlider("coursesDateSlider", 2004, ["courses-date-slider"]);

    // Plans: same BASE_YEAR as Python utils/date_slider.py
    registerSlider("plansDateSlider", 2004, ["plans-date-slider"]);

    // Machine Downtime: same BASE_YEAR as Python utils/date_slider.py
    registerSlider("machinesDateSlider", 2004, ["machines-date-slider"]);

    // Procedures: same BASE_YEAR as Python utils/date_slider.py
    registerSlider("proceduresDateSlider", 2004, ["proc-date-slider"]);

    // Physicians: same BASE_YEAR as Python utils/date_slider.py
    registerSlider("physDateSlider", 2004, ["phys-date-slider"]);
    registerSlider("billingDateSlider", 2004, ["billing-date-slider"]);
    registerSlider("cptDateSlider", 2004, ["cpt-date-slider"]);
    registerSlider("patientsDateSlider", 2004, ["patients-date-slider"]);
    registerSlider("diagDateSlider", 2004, ["diag-date-slider"]);
    registerSlider("referralsDateSlider", 2004, ["referrals-date-slider"]);
    registerSlider("txDateSlider", 2004, ["tx-date-slider"]);

    // Expose factory for future pages
    window._registerDateSlider = registerSlider;

    // ── Physicians after-hours slider: rewrite thumb labels ───────────
    // Slider uses 0-48 scale (each tick = 30 min, 0 = midnight)
    function fmtHalfHour(tick) {
        var totalMin = tick * 30;
        var h = Math.floor(totalMin / 60);
        var m = totalMin % 60;
        var suffix = h < 12 || h === 24 ? "AM" : "PM";
        var h12 = h % 12 || 12;
        return h12 + ":" + String(m).padStart(2, "0") + " " + suffix;
    }
    var ahObserver = new MutationObserver(function() {
        var el = document.getElementById("phys-ah-hours");
        if (!el) return;
        el.querySelectorAll(".mantine-Slider-label").forEach(function(lbl) {
            var n = parseInt(lbl.textContent, 10);
            if (!isNaN(n) && lbl.textContent === String(n)) {
                lbl.textContent = fmtHalfHour(n);
            }
        });
    });
    document.addEventListener("DOMContentLoaded", function() {
        ahObserver.observe(document.body,
            {childList: true, subtree: true, characterData: true});
    });

})();
