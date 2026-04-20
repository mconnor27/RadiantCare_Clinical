"""Clerk-backed session auth for the Dash app's Flask server.

Architecture
------------
1. The user hits any page. A Flask ``before_request`` hook inspects the
   ``__session`` cookie that Clerk's browser SDK manages on our domain.
2. The cookie is a JWT signed by Clerk. We verify it against Clerk's JWKS
   (cached locally for 12 h) and pull the user's Clerk ID + email claims.
3. On a valid JWT we mirror the identity into a Flask session cookie
   (``rc_session``) so subsequent requests don't re-verify on every
   callback. The Flask cookie also holds the JWT expiry so we re-check
   when Clerk's session lapses.
4. Invalid / missing → for HTML navigation we redirect to ``/login``
   (which renders Clerk's hosted SignIn widget in our page shell);
   for Dash AJAX endpoints we return a 401 so the browser console stays
   clean and the front-end can handle it.

Why a second Flask session cookie?
    Clerk's ``__session`` is short-lived (10 min by default) and rotated
    frequently; we verify it, then cache our own longer-lived identity
    cookie so we aren't hitting JWKS on every Dash callback. On expiry
    we transparently re-verify against the still-valid Clerk cookie or
    bounce the user back to Clerk.

Account management (invitations, password resets, MFA, device list) is
all handled by Clerk's hosted UI. We don't implement any of it here.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import timedelta
from functools import lru_cache
from urllib.parse import quote, urlparse

import jwt
from flask import (
    Flask, make_response, redirect, render_template_string, request, session,
)
from werkzeug.middleware.proxy_fix import ProxyFix


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# How long the Flask mirror-session cookie stays valid. Independent of
# Clerk's own session lifetime — if Clerk expires first we re-verify;
# if this expires first the user is bounced through Clerk.
SESSION_LIFETIME = timedelta(days=7)

# Recheck Clerk's __session JWT this often even if our mirror is still valid.
# Keeps revocation latency bounded.
CLERK_RECHECK_INTERVAL = 60 * 15  # 15 min

# Paths that do NOT require a logged-in session.
_PUBLIC_PATH_PREFIXES = (
    "/login",
    "/logout",
    "/no-access",
    "/favicon.ico",
    "/health",
    "/_auth/",   # includes /_auth/debug and /_auth/me
)


# ---------------------------------------------------------------------------
# Login page: renders Clerk's SignIn widget in our app's visual shell
# ---------------------------------------------------------------------------

_LOGIN_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Signing in — RadiantCare Clinical</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body {
    margin: 0; min-height: 100vh;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: linear-gradient(140deg, #F3E8F5 0%, #F5F6F8 55%, #E8EEF5 100%);
    display: flex; align-items: center; justify-content: center;
    padding: 16px; color: #6B7280;
  }
  .spinner {
    width: 36px; height: 36px; margin-bottom: 14px;
    border: 3px solid rgba(124, 42, 131, 0.18);
    border-top-color: #7C2A83; border-radius: 50%;
    animation: rc-spin 0.9s linear infinite;
    display: inline-block;
  }
  @keyframes rc-spin { to { transform: rotate(360deg); } }
  .card { text-align: center; }
  .brand { color: #7C2A83; font-weight: 700; font-size: 20px; letter-spacing: -0.01em; margin: 0 0 4px; }
  .sub { font-size: 13px; margin: 0; }
</style>
</head>
<body>
  <div class="card">
    <span class="spinner" aria-hidden="true"></span>
    <p class="brand">RadiantCare Clinical</p>
    <p class="sub">Signing you in&hellip;</p>
  </div>

  <script
    async
    crossorigin="anonymous"
    data-clerk-publishable-key="{{ clerk_pub_key }}"
    src="https://{{ clerk_frontend_host }}/npm/@clerk/clerk-js@5/dist/clerk.browser.js"
    type="text/javascript"
  ></script>
  <script>
    // This page exists to perform Clerk's cross-subdomain handshake in JS,
    // then bounce the user to the original destination. If no session is
    // available, fall back to the central Clerk Account Portal sign-in so
    // users see a single consistent sign-in UI across all four apps.
    (function () {
      var NEXT = {{ next_url|tojson }};
      var PORTAL = 'https://accounts.radiantcare.app/sign-in?redirect_url='
        + encodeURIComponent(window.location.origin + NEXT);

      // Abort quickly if Clerk never loads (e.g. offline / blocked).
      var fallbackTimer = setTimeout(function () {
        window.location.replace(PORTAL);
      }, 6000);

      function waitForClerk(done) {
        if (window.Clerk) { done(); return; }
        var i = setInterval(function () {
          if (window.Clerk) { clearInterval(i); done(); }
        }, 50);
      }
      waitForClerk(async function () {
        try {
          await window.Clerk.load();
        } catch (e) {
          clearTimeout(fallbackTimer);
          window.location.replace(PORTAL);
          return;
        }
        clearTimeout(fallbackTimer);
        if (window.Clerk.user) {
          window.location.replace(NEXT);
        } else {
          window.location.replace(PORTAL);
        }
      });
    })();
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise RuntimeError(
            f"auth.py: required env var {name!r} is not set. "
            f"Define it in Railway (or your .env for local testing)."
        )
    return v


def _clerk_frontend_host(publishable_key: str) -> str:
    """Derive the Clerk frontend-API hostname from the publishable key.

    Clerk publishable keys encode the instance's Frontend API subdomain as
    a base64-URL-encoded suffix: ``pk_test_<base64(host)>$`` or similar.
    The canonical way to get the host is to decode the key.
    """
    import base64
    try:
        suffix = publishable_key.split("_", 2)[2]
        if suffix.endswith("$"):
            suffix = suffix[:-1]
        padded = suffix + "=" * (-len(suffix) % 4)
        host = base64.urlsafe_b64decode(padded).decode("utf-8").rstrip("$")
        if host.startswith("http://") or host.startswith("https://"):
            host = urlparse(host).netloc
        return host
    except Exception as exc:
        raise RuntimeError(
            f"auth.py: could not parse Clerk frontend host from "
            f"CLERK_PUBLISHABLE_KEY ({publishable_key[:12]}…): {exc}"
        ) from exc


def _is_safe_relative_url(target: str) -> bool:
    if not target:
        return False
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return False
    return target.startswith("/")


def _is_public_path(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in _PUBLIC_PATH_PREFIXES)


def _is_ajax_or_dash_request() -> bool:
    """True if the requestor expects a JSON/data response rather than HTML —
    we return 401 to those so browser consoles stay clean, rather than
    returning 302 HTML and tripping every Dash callback."""
    if request.path.startswith(("/_dash-", "/_reload-hash", "/_favicon")):
        return True
    accept = (request.accept_mimetypes or [])
    if accept and accept.best == "application/json":
        return True
    # Dash sends X-Requested-With on many callbacks
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    return False


# ---------------------------------------------------------------------------
# Clerk JWKS verification — cached
# ---------------------------------------------------------------------------

class _ClerkVerifier:
    """Caches Clerk's JWKS for 12 h and verifies __session JWTs."""

    def __init__(self, frontend_host: str) -> None:
        self._jwks_url = f"https://{frontend_host}/.well-known/jwks.json"
        # Lazy import: PyJWKClient talks to the JWKS URL on first use.
        self._client = jwt.PyJWKClient(
            self._jwks_url, cache_keys=True, lifespan=60 * 60 * 12,
        )

    def verify(self, token: str) -> dict | None:
        try:
            signing_key = self._client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={"verify_aud": False, "verify_iss": True},
                issuer=None,  # we don't pin the issuer here; JWKS URL already
                              # scopes it to one Clerk instance. Could tighten.
                leeway=10,
            )
        except jwt.ExpiredSignatureError:
            logger.debug("auth: __session token expired")
            return None
        except jwt.InvalidTokenError as exc:
            logger.info("auth: __session token invalid: %s", exc)
            return None
        except Exception as exc:
            logger.warning("auth: JWKS verification error: %s", exc)
            return None
        return claims


@lru_cache(maxsize=1)
def _verifier() -> _ClerkVerifier:
    pub = _require_env("CLERK_PUBLISHABLE_KEY")
    host = os.environ.get("CLERK_FRONTEND_HOST", "").strip() or _clerk_frontend_host(pub)
    return _ClerkVerifier(host)


# Small LRU for user->email lookups so we don't hammer Clerk's API every
# callback. Cache for 10 min matches our CLERK_RECHECK_INTERVAL cadence.
_USER_EMAIL_CACHE: dict[str, tuple[float, str]] = {}
_USER_EMAIL_TTL = 600


def _fetch_user_email(user_id: str) -> str:
    """Look up a Clerk user's primary email via the backend API.

    Clerk's default session JWT only carries `sub` (user_id), `sid`, and
    standard timing claims — not email. Fetching via the backend API with
    CLERK_SECRET_KEY gives us the email we need for the ALLOWED_EMAILS
    allowlist. Cached briefly so the allowlist check stays cheap.
    """
    now = time.time()
    cached = _USER_EMAIL_CACHE.get(user_id)
    if cached and cached[0] > now:
        return cached[1]

    secret = os.environ.get("CLERK_SECRET_KEY", "").strip()
    if not secret:
        logger.warning("auth: CLERK_SECRET_KEY not set; cannot fetch user email")
        return ""

    try:
        import httpx
        r = httpx.get(
            f"https://api.clerk.com/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {secret}"},
            timeout=5,
        )
        if r.status_code != 200:
            logger.warning("auth: Clerk user fetch %s returned %d", user_id, r.status_code)
            return ""
        data = r.json()
    except Exception as exc:
        logger.warning("auth: Clerk user fetch %s failed: %s", user_id, exc)
        return ""

    # Primary email — Clerk returns a list of email addresses; pick the one
    # whose id matches `primary_email_address_id`.
    primary_id = data.get("primary_email_address_id")
    email = ""
    for e in data.get("email_addresses", []) or []:
        if e.get("id") == primary_id:
            email = (e.get("email_address") or "").strip().lower()
            break
    if not email:
        # Fallback: first email in the list
        emails = data.get("email_addresses") or []
        if emails:
            email = (emails[0].get("email_address") or "").strip().lower()

    _USER_EMAIL_CACHE[user_id] = (now + _USER_EMAIL_TTL, email)
    return email


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def register_auth(server: Flask) -> None:
    if getattr(server, "_radiantcare_auth_installed", False):
        return
    server._radiantcare_auth_installed = True

    server.secret_key = _require_env("FLASK_SECRET")
    server.permanent_session_lifetime = SESSION_LIFETIME

    server.wsgi_app = ProxyFix(
        server.wsgi_app, x_for=1, x_proto=1, x_host=1,
    )

    cookie_secure = os.environ.get(
        "SESSION_COOKIE_SECURE", "true"
    ).lower() not in ("false", "0", "no", "off")
    server.config.update(
        SESSION_COOKIE_SECURE=cookie_secure,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_NAME="rc_session",
    )

    clerk_pub_key = _require_env("CLERK_PUBLISHABLE_KEY")
    clerk_frontend_host = os.environ.get(
        "CLERK_FRONTEND_HOST", ""
    ).strip() or _clerk_frontend_host(clerk_pub_key)

    # Eagerly build the verifier so misconfigured env fails fast at boot.
    _verifier()

    # ---- Before-request guard ----

    @server.before_request
    def _require_login():
        path = request.path or "/"
        if _is_public_path(path):
            return None

        now = int(time.time())

        # Fast path: mirror-session cookie is fresh and not due for recheck.
        if (session.get("user_id")
                and session.get("clerk_last_check", 0) + CLERK_RECHECK_INTERVAL > now):
            return None

        # Verify Clerk's __session cookie (set by the browser SDK).
        clerk_jwt = request.cookies.get("__session")
        claims = _verifier().verify(clerk_jwt) if clerk_jwt else None
        if claims:
            # Mirror identity into our Flask session for fast subsequent checks.
            user_id = claims.get("sub")
            if user_id:
                # Clerk's default session JWT doesn't carry email — we pull
                # it from the backend API (cached per-user for 10 min).
                email = (
                    claims.get("email")
                    or claims.get("primary_email_address")
                    or _fetch_user_email(user_id)
                    or ""
                )
                # App-level allowlist + role lookup (Clerk's own allowlist is
                # paywalled). Access is gated by a row in clinical.profiles
                # keyed by email; role ∈ {admin, partner, user}.
                from data.profiles_db import get_profile, upsert_profile
                profile = get_profile(email)
                # Fallback: first time Dr. Connor (or any ALLOWED_EMAILS entry)
                # signs in after the profiles table is created, auto-seed an
                # admin row so he's never locked out.
                if not profile:
                    legacy_allowlist = [
                        e.strip().lower()
                        for e in os.environ.get("ALLOWED_EMAILS", "").split(",")
                        if e.strip()
                    ]
                    if email.lower() in legacy_allowlist:
                        upsert_profile(email, role="admin", clerk_user_id=user_id)
                        profile = get_profile(email)
                if not profile:
                    logger.warning("auth: Clerk-verified user %s has no clinical.profile", email)
                    if _is_ajax_or_dash_request():
                        return make_response(("Not authorized", 403))
                    # Do NOT redirect to /logout — Clerk's parent-domain
                    # cookies (shared across all radiantcare.app apps) would
                    # auto-resume the session and send us right back here,
                    # producing an infinite loop. Instead show a friendly
                    # "no access" page while keeping Clerk session alive so
                    # the user can use other apps they have access to.
                    if request.path == "/no-access":
                        return None  # avoid recursion
                    return redirect("/no-access?email=" + quote(email, safe=""))

                # Backfill clerk_user_id on the profile row if missing.
                if profile.get("clerk_user_id") != user_id:
                    try:
                        upsert_profile(
                            email,
                            role=profile["role"],
                            display_name=profile.get("display_name"),
                            clerk_user_id=user_id,
                        )
                    except Exception as exc:
                        logger.warning("auth: backfill clerk_user_id failed: %s", exc)

                if not session.get("user_id") or session.get("user_id") != user_id:
                    session.clear()
                    session.permanent = True
                session["user_id"] = user_id
                session["email"] = email
                session["role"] = profile["role"]
                session["display_name"] = profile.get("display_name") or ""
                session["clerk_last_check"] = now
                # Cache the Clerk session id so /logout can revoke it server-side.
                sid = claims.get("sid")
                if sid:
                    session["clerk_sid"] = sid
                return None

        # Not authenticated.
        if _is_ajax_or_dash_request():
            return make_response(("Not authenticated", 401))

        # Top-level navigation → send to /login, preserving intent.
        next_url = (request.full_path.rstrip("?")
                    if request.args else request.path)
        if not _is_safe_relative_url(next_url):
            next_url = "/"
        return redirect(f"/login?next={quote(next_url, safe='/?=&')}")

    # ---- Routes ----

    @server.route("/login", methods=["GET"])
    def login():
        next_url = request.args.get("next") or "/"
        if not _is_safe_relative_url(next_url):
            next_url = "/"

        # Fast path: per-subdomain __session cookie is present and valid →
        # user is already signed in to Clinical specifically, just send them.
        clerk_jwt = request.cookies.get("__session")
        if clerk_jwt and _verifier().verify(clerk_jwt):
            return redirect(next_url)

        # Otherwise serve a tiny "signing in…" page that loads Clerk JS.
        # Clerk's client SDK does the cross-subdomain handshake natively
        # via the parent-domain __client_uat cookie and sets a per-subdomain
        # __session for us. If the user has no active session anywhere, the
        # page falls through to the shared Clerk Account Portal sign-in.
        return render_template_string(
            _LOGIN_HTML,
            clerk_pub_key=clerk_pub_key,
            clerk_frontend_host=clerk_frontend_host,
            next_url=next_url,
        )

    @server.route("/logout", methods=["GET", "POST"])
    def logout():
        """Fully sign the user out.

        Three coordinated moves, because Clerk sessions survive in
        surprising places otherwise:

        1. Revoke the Clerk session server-side via the Backend API so the
           token is invalid even if a cookie leaks back in.
        2. Clear every Clerk-owned cookie in the current request — both
           per-subdomain (``__session``, ``__clerk_db_jwt`` and their
           suffixed variants) and parent-domain (``__client_uat*``).
           Suffix patterns (``__client_uat_<id>``) vary per instance so
           we enumerate whatever the browser actually sent us rather than
           guessing.
        3. Redirect to our own /login which forwards to the Portal's
           /sign-in. (Clerk has no hosted /sign-out URL — SDK-only.)
        """
        import httpx as _httpx
        sid = session.get("clerk_sid")
        if not sid:
            # Fall back to reading the JWT's sid claim if we didn't cache it.
            clerk_jwt = request.cookies.get("__session")
            if clerk_jwt:
                claims = _verifier().verify(clerk_jwt)
                if claims:
                    sid = claims.get("sid")

        secret = os.environ.get("CLERK_SECRET_KEY", "").strip()
        if sid and secret:
            try:
                _httpx.post(
                    f"https://api.clerk.com/v1/sessions/{sid}/revoke",
                    headers={"Authorization": f"Bearer {secret}"},
                    timeout=5,
                )
            except Exception as exc:
                logger.warning("auth: clerk session revoke failed: %s", exc)

        session.clear()

        host = (request.host or "").split(":", 1)[0]
        parts = host.split(".")
        parent_domain = "." + ".".join(parts[-2:]) if len(parts) >= 2 else None

        resp = redirect("/login")

        # Per-subdomain Clerk + Flask cookies — clear every cookie whose name
        # matches any Clerk pattern, regardless of suffix.
        clerk_subdomain_prefixes = ("__session", "__clerk_db_jwt", "__refresh", "__client")
        for name in request.cookies.keys():
            if name == server.config["SESSION_COOKIE_NAME"] or any(
                name.startswith(p) for p in clerk_subdomain_prefixes
            ):
                resp.set_cookie(
                    name, "", expires=0, path="/",
                    httponly=(name == server.config["SESSION_COOKIE_NAME"]),
                    secure=cookie_secure, samesite="Lax",
                )
                # Also try clearing at the parent-domain in case the cookie was
                # actually set there (e.g. __client_uat_* on .radiantcare.app).
                if parent_domain:
                    resp.set_cookie(
                        name, "", expires=0, path="/",
                        domain=parent_domain,
                        httponly=False, secure=cookie_secure, samesite="Lax",
                    )

        return resp

    @server.route("/health")
    def health():
        return {"status": "ok"}, 200

    @server.route("/no-access")
    def no_access():
        """Friendly 403 page for Clerk-authenticated users who lack a
        clinical.profiles row. Keeps them signed in at Clerk so they can
        navigate to other RadiantCare apps they do have access to."""
        email = request.args.get("email", "").strip()
        safe_email = email.replace("<", "&lt;").replace(">", "&gt;")
        return render_template_string(
            """<!doctype html>
<html lang=\"en\"><head>
<meta charset=\"utf-8\"><title>No access — RadiantCare Clinical</title>
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<style>
 body { margin:0; min-height:100vh; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
        background:linear-gradient(140deg,#F3E8F5 0%,#F5F6F8 55%,#E8EEF5 100%);
        display:flex; align-items:center; justify-content:center; padding:16px; }
 .card { max-width:480px; width:100%; background:#fff; border-radius:16px;
         padding:40px; box-shadow:0 14px 40px rgba(46,0,50,0.12); text-align:center; }
 h1 { color:#7C2A83; margin:0 0 8px; font-weight:700; font-size:22px; }
 p { color:#555; line-height:1.5; margin:8px 0; }
 .mail { font-family:ui-monospace,Menlo,Consolas,monospace; color:#7C2A83; }
 .actions { display:flex; gap:12px; justify-content:center; margin-top:24px; flex-wrap:wrap; }
 .btn { border:0; padding:10px 20px; border-radius:10px; font-size:14px; font-weight:600;
        cursor:pointer; text-decoration:none; display:inline-block; }
 .btn-primary { background:#7C2A83; color:#fff; }
 .btn-secondary { background:transparent; color:#7C2A83; border:1px solid #7C2A83; }
</style></head><body>
<div class=\"card\">
  <h1>No access to Clinical</h1>
  <p>You're signed in as <span class=\"mail\">{{ email }}</span> but this account
     doesn't have access to the Clinical app.</p>
  <p>Contact an administrator if you need access.</p>
  <div class=\"actions\">
    <a class=\"btn btn-primary\" href=\"https://radiantcare.app\">Go to RadiantCare</a>
    <a class=\"btn btn-secondary\" href=\"/logout\">Sign out</a>
  </div>
</div>
</body></html>""",
            email=safe_email,
        ), 200

    @server.route("/_auth/me")
    def whoami():
        if not session.get("user_id"):
            return {"authenticated": False}, 401
        return {
            "authenticated": True,
            "email": session.get("email"),
        }, 200

    @server.route("/_auth/debug")
    def auth_debug():
        """Temporary diagnostic. Safe to ship: returns cookie NAMES only
        (not values), JWT verification status, and claim keys if verified."""
        cookie_names = list(request.cookies.keys())
        clerk_jwt = request.cookies.get("__session")
        verification = None
        claim_keys = None
        if clerk_jwt:
            claims = _verifier().verify(clerk_jwt)
            if claims:
                verification = "valid"
                # Return only claim names, not values, to avoid leaking identity
                claim_keys = sorted(claims.keys())
            else:
                verification = "invalid_or_expired"
        else:
            verification = "no_cookie"
        return {
            "host": request.host,
            "is_secure": request.is_secure,
            "forwarded_proto": request.headers.get("X-Forwarded-Proto"),
            "cookies_received_names": cookie_names,
            "has_clerk_session_cookie": "__session" in request.cookies,
            "clerk_verification": verification,
            "clerk_claim_keys": claim_keys,
            "flask_session_user_id": bool(session.get("user_id")),
            "flask_session_email": session.get("email"),
            "allowed_origins_note": (
                "Verify Clerk's allowed_origins include this host"
            ),
        }, 200
