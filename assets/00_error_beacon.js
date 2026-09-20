// Temporary diagnostic: report client-side JS errors into the server access
// log via a GET query string, so device-specific failures (e.g. iOS Safari)
// are visible without remote debugging. Capped, truncated, and safe to leave
// in place, but intended to be removed once the blank-page issue is resolved.
(function () {
  if (window.__rcErrBeacon) return;
  window.__rcErrBeacon = true;
  var sent = 0;
  function report(kind, msg) {
    if (sent >= 5 || !msg) return;
    sent++;
    try {
      var q = encodeURIComponent(String(msg).slice(0, 400));
      fetch("/healthz?jskind=" + kind + "&jserr=" + q, { keepalive: true });
    } catch (e) { /* never break the page from the error reporter */ }
  }
  window.addEventListener("error", function (e) {
    var m = (e && e.message) || "";
    var f = (e && e.filename) || "";
    var l = (e && e.lineno) || "";
    report("err", m + " @ " + f + ":" + l);
  });
  window.addEventListener("unhandledrejection", function (e) {
    var r = e && e.reason;
    report("rej", (r && (r.stack || r.message)) || String(r));
  });
  // React/dash-renderer render errors surface via console.error, not
  // window.onerror — mirror the first few into the beacon too.
  var origErr = console.error;
  console.error = function () {
    try {
      var parts = [];
      for (var i = 0; i < arguments.length && i < 3; i++) {
        var a = arguments[i];
        parts.push(typeof a === "string" ? a : (a && (a.stack || a.message)) || String(a));
      }
      report("console", parts.join(" | "));
    } catch (e) {}
    return origErr.apply(console, arguments);
  };
})();
