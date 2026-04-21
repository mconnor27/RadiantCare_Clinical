// Session recovery for idle tabs.
//
// The app's auth layer (auth.py) rechecks Clerk every 15 min. Clerk's own
// __session cookie is 10 min and is only rotated while Clerk JS is running,
// which we don't load on app pages. So when a tab sits idle past those
// windows, the next Dash callback 401s and the UI appears broken.
//
// Two recovery paths:
//   1. Proactive: if the tab was hidden >10 min, reload as soon as it
//      becomes visible — the /login handshake re-mints cookies via the
//      parent-domain __client_uat (still valid for longer) before the
//      user tries to interact.
//   2. Reactive: intercept fetch; on a 401 from a Dash endpoint, reload
//      once. Covers cases where the proactive path missed (e.g. tab
//      stayed focused but we lost the Clerk side).

(function () {
  if (window.__rcSessionRecoverInstalled) return;
  window.__rcSessionRecoverInstalled = true;

  var IDLE_RELOAD_MS = 10 * 60 * 1000;
  var reloading = false;

  function reloadOnce() {
    if (reloading) return;
    reloading = true;
    window.location.reload();
  }

  // --- Reactive: wrap fetch to catch 401s on Dash callbacks ---
  var origFetch = window.fetch;
  if (typeof origFetch === "function") {
    window.fetch = function (input, init) {
      var url = typeof input === "string" ? input : (input && input.url) || "";
      var isDash = url.indexOf("/_dash-") !== -1 || url.indexOf("/_reload-hash") !== -1;
      var p = origFetch.apply(this, arguments);
      if (!isDash) return p;
      return p.then(function (res) {
        if (res && res.status === 401) reloadOnce();
        return res;
      });
    };
  }

  // --- Proactive: reload after returning from a long-hidden state ---
  var hiddenAt = null;
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      hiddenAt = Date.now();
    } else if (hiddenAt) {
      var idleMs = Date.now() - hiddenAt;
      hiddenAt = null;
      if (idleMs > IDLE_RELOAD_MS) reloadOnce();
    }
  });
})();
