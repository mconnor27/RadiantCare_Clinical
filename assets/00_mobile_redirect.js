(function () {
    try {
        var MOBILE_PATH = '/mobile';
        var DESKTOP_PATH = '/';
        var BREAKPOINT = 768;
        var params = new URLSearchParams(window.location.search);
        var forceMode = params.get('force');
        var path = window.location.pathname;

        var onMobilePath = (path === MOBILE_PATH || path.indexOf(MOBILE_PATH + '/') === 0);
        if (onMobilePath || forceMode === 'mobile') {
            document.documentElement.setAttribute('data-mobile-view', 'true');
        }

        if (forceMode === 'desktop' || forceMode === 'mobile') return;

        var ua = navigator.userAgent || '';
        var isMobile = window.innerWidth < BREAKPOINT || /Mobi|Android|iPhone|iPad|iPod/i.test(ua);

        if (isMobile && path === DESKTOP_PATH) {
            window.location.replace(MOBILE_PATH + window.location.search + window.location.hash);
        } else if (!isMobile && path === MOBILE_PATH) {
            window.location.replace(DESKTOP_PATH + window.location.search + window.location.hash);
        }
    } catch (e) { }
})();
