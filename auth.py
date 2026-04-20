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
<title>Sign in — RadiantCare Clinical</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    min-height: 100vh;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: linear-gradient(140deg, #F3E8F5 0%, #F5F6F8 55%, #E8EEF5 100%);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 16px;
  }
  .brand {
    color: #7C2A83;
    font-weight: 700;
    font-size: 22px;
    letter-spacing: -0.01em;
    margin: 0 0 4px;
  }
  .sub {
    color: #6B7280;
    margin: 0 0 24px;
    font-size: 13px;
    line-height: 1.5;
    text-align: center;
    max-width: 360px;
  }
  /* The widget itself — let Clerk style it but contain it visually. */
  #sign-in-mount {
    width: 100%;
    max-width: 400px;
  }
  .footer {
    margin-top: 20px;
    color: #9CA3AF;
    font-size: 11px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .footer::before {
    content: '';
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #7C2A83;
  }
  .error {
    color: #991B1B;
    background: #FEF2F2;
    border: 1px solid #FECACA;
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 13px;
    max-width: 380px;
    margin-top: 16px;
  }
</style>
</head>
<body>
  <p class="brand">RadiantCare Clinical</p>
  <p class="sub">Sign in to continue. Accounts are invite-only.</p>

  <div id="sign-in-mount"></div>

  {% if error %}<div class="error">{{ error }}</div>{% endif %}

  <div class="footer">De-Identified Data</div>

  <script
    async
    crossorigin="anonymous"
    data-clerk-publishable-key="{{ clerk_pub_key }}"
    src="https://{{ clerk_frontend_host }}/npm/@clerk/clerk-js@5/dist/clerk.browser.js"
    type="text/javascript"
  ></script>
  <script>
    window.addEventListener('load', async function () {
      if (!window.Clerk) {
        document.body.insertAdjacentHTML('beforeend',
          '<div class="error">Could not load sign-in. Check network and reload.</div>');
        return;
      }
      try {
        await window.Clerk.load();
      } catch (e) {
        document.body.insertAdjacentHTML('beforeend',
          '<div class="error">Sign-in failed to initialize: ' + (e && e.message || e) + '</div>');
        return;
      }

      // If Clerk already has a session (came back from password reset etc.),
      // kick the server so it can mint our Flask mirror cookie.
      if (window.Clerk.user) {
        window.location.replace({{ next_url|tojson }});
        return;
      }

      window.Clerk.mountSignIn(document.getElementById('sign-in-mount'), {
        afterSignInUrl: {{ next_url|tojson }},
        afterSignUpUrl: {{ next_url|tojson }},
        signUpUrl: null,  // no public signup — invitations only
        appearance: {
          variables: {
            colorPrimary: '#7C2A83',
            colorText: '#1A1A2E',
            colorBackground: '#FFFFFF',
            borderRadius: '8px',
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
          },
          elements: {
            card: { boxShadow: '0 1px 3px rgba(0,0,0,0.04), 0 14px 40px rgba(46,0,50,0.12)' },
            footer: { display: 'none' },  // hide Clerk's branding footer
          },
        },
      });
    });
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
                # App-level allowlist. Clerk's own allowlist is paywalled, so
                # we enforce it here: only emails explicitly listed in the
                # ALLOWED_EMAILS env var (comma-separated) can complete login.
                # If ALLOWED_EMAILS is unset, any Clerk-verified user is allowed
                # (useful for local dev). In Railway, always set this.
                allowlist = [
                    e.strip().lower()
                    for e in os.environ.get("ALLOWED_EMAILS", "").split(",")
                    if e.strip()
                ]
                if allowlist and email.lower() not in allowlist:
                    logger.warning(
                        "auth: Clerk-verified user %s not in ALLOWED_EMAILS",
                        email,
                    )
                    session.clear()
                    if _is_ajax_or_dash_request():
                        return make_response(("Not authorized", 403))
                    # Bounce to /logout so Clerk's __session cookie is cleared too,
                    # then /logout redirects to /login where they can try another email.
                    return redirect("/logout")

                if not session.get("user_id") or session.get("user_id") != user_id:
                    session.clear()
                    session.permanent = True
                session["user_id"] = user_id
                session["email"] = email
                session["clerk_last_check"] = now
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

        # If Clerk already has a valid session (cross-subdomain SSO), send the
        # user straight to their destination — no portal round-trip needed.
        clerk_jwt = request.cookies.get("__session")
        if clerk_jwt and _verifier().verify(clerk_jwt):
            return redirect(next_url)

        # Otherwise bounce to the shared Clerk Account Portal. Single
        # sign-in UI for all RadiantCare apps, no double-branded shells.
        host = (request.host or "").split(":", 1)[0]
        parts = host.split(".")
        parent = ".".join(parts[-2:]) if len(parts) >= 2 else host
        accounts_host = f"accounts.{parent}"
        proto = "https" if request.is_secure else "http"
        full_return = f"{proto}://{host}{next_url}"
        portal_url = (
            f"https://{accounts_host}/sign-in?redirect_url="
            f"{quote(full_return, safe=':/?=&')}"
        )
        return redirect(portal_url)

    @server.route("/logout", methods=["GET", "POST"])
    def logout():
        """Fully sign the user out.

        Clerk uses both per-subdomain cookies (``__session``, ``__clerk_db_jwt``)
        and parent-domain "client" cookies (``__client_uat``, ``__client_uat_*``)
        scoped to ``.radiantcare.app``. If we only clear the per-subdomain
        ones, the browser will immediately re-authenticate on refresh using
        the parent-domain ``__client_uat`` via Clerk's handshake protocol.

        We clear both local + parent-domain cookies, *then* redirect to Clerk's
        hosted sign-out endpoint which revokes the session server-side and
        returns the user to our /login page.
        """
        session.clear()

        # Figure out the parent-domain we should scope cookie clears against.
        # In production that's ``.radiantcare.app``; in local dev the Host
        # header is the right default and Flask will scope cookies correctly
        # without an explicit domain.
        host = (request.host or "").split(":", 1)[0]
        parts = host.split(".")
        parent_domain = "." + ".".join(parts[-2:]) if len(parts) >= 2 else None

        # For Clerk hosted sign-out we use the Account Portal host
        # (accounts.<root>), NOT the Frontend API host (clerk.<root>).
        # The portal handles the full sign-out + revocation flow and then
        # 302s back to our /login.
        proto = "https" if request.is_secure else "http"
        return_to = f"{proto}://{host}/login"
        if parent_domain:
            accounts_host = "accounts" + parent_domain  # ".radiantcare.app" → "accounts.radiantcare.app"
            final_redirect = (
                f"https://{accounts_host}/sign-out?redirect_url="
                f"{quote(return_to, safe=':/?=&')}"
            )
        else:
            final_redirect = "/login"

        resp = redirect(final_redirect)

        # Per-subdomain cookies
        for name in (server.config["SESSION_COOKIE_NAME"], "__session"):
            resp.set_cookie(
                name, "", expires=0, path="/",
                httponly=(name == server.config["SESSION_COOKIE_NAME"]),
                secure=cookie_secure, samesite="Lax",
            )

        # Parent-domain Clerk client-session cookies. There are base + suffixed
        # variants (e.g. ``__client_uat_juP2OGU-``); since we can't enumerate
        # unknown suffixes from the server, we just clear the known base names
        # and rely on Clerk's sign-out endpoint to clear the rest.
        if parent_domain:
            for name in ("__client_uat", "__client"):
                resp.set_cookie(
                    name, "", expires=0, path="/",
                    domain=parent_domain,
                    httponly=False, secure=cookie_secure, samesite="Lax",
                )

        return resp

    @server.route("/health")
    def health():
        return {"status": "ok"}, 200

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
