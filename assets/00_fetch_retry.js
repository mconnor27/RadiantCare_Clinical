// Retry transient network failures on Dash callback requests.
//
// After a deploy/restart, pooled keep-alive connections (notably iOS Safari
// behind iCloud Private Relay) can go stale: the browser transparently
// retries GETs on a fresh connection, but a POST fetch() rejects immediately
// and dash-renderer gives up — leaving a blank page until the stale pool
// expires. Retrying on a fresh connection succeeds right away. Dash callback
// POSTs are pure renders (no server-side mutation), so retrying is safe.
//
// Loads before 00_session_recover.js (alphabetical), whose own fetch wrapper
// then sees the final (post-retry) outcome — including its 401 handling.
(function () {
  if (window.__rcFetchRetryInstalled) return;
  window.__rcFetchRetryInstalled = true;

  var RETRY_DELAYS = [400, 1500]; // ms between attempts
  var RETRY_STATUSES = { 502: 1, 503: 1, 504: 1 }; // edge errors during restart

  var orig = window.fetch;
  if (typeof orig !== "function") return;

  function isDashUrl(input) {
    var url = typeof input === "string" ? input : (input && input.url) || "";
    return url.indexOf("/_dash-") !== -1;
  }

  window.fetch = function (input) {
    var self = this;
    var args = arguments;
    if (!isDashUrl(input)) return orig.apply(self, args);
    var attempt = 0;
    function wait(ms) {
      return new Promise(function (resolve) { setTimeout(resolve, ms); });
    }
    function run() {
      return orig.apply(self, args).then(function (res) {
        if (res && RETRY_STATUSES[res.status] && attempt < RETRY_DELAYS.length) {
          return wait(RETRY_DELAYS[attempt++]).then(run);
        }
        return res;
      }, function (err) {
        if (attempt >= RETRY_DELAYS.length) throw err;
        return wait(RETRY_DELAYS[attempt++]).then(run);
      });
    }
    return run();
  };
})();
