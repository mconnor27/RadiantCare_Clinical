// Re-tap cycling for the mobile "Prior Yr" range segment: 1 → 3 → 5 years
// back. A SegmentedControl fires no change event when the already-selected
// item is tapped again, so a capture-phase listener detects the re-tap (the
// radio is still checked at capture time) and advances the offset store via
// dash_clientside.set_props. Freshly selecting Prior Yr from another range
// resets the cycle to 1 year back.
(function () {
  var NEXT = { 1: 3, 3: 5, 5: 1 };
  var off = 1;

  document.addEventListener(
    "click",
    function (e) {
      var t = e.target;
      if (!t || !t.closest) return;
      if (!t.closest("#mobilehome-range")) return;
      var label = t.closest("label");
      if (!label) return;
      var input = label.querySelector("input[type=radio]");
      if (!input) {
        var forId = label.getAttribute("for");
        input = forId ? document.getElementById(forId) : null;
      }
      if (!input || input.value !== "py") return;
      var setProps = window.dash_clientside && window.dash_clientside.set_props;
      if (!setProps) return;
      if (input.checked) {
        // Already selected → advance the cycle.
        off = NEXT[off] || 1;
        setProps("mobilehome-py-offset", { data: off });
      } else if (off !== 1) {
        // Fresh selection from another range → reset to 1 year back.
        off = 1;
        setProps("mobilehome-py-offset", { data: 1 });
      }
    },
    true
  );
})();
