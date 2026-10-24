"""Google account login and a separately approved, read-only calendar connection."""

from datetime import date, datetime, timedelta
import logging
import os
from pathlib import Path
import secrets
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from flask import Flask, abort, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException, SecurityError

from auth import (authorization_request, calendar_authorization_request, client_configuration,
                  exchange_calendar, exchange_identity)
from calendar_api import CalendarError, GoogleCalendar, disconnect, require_secure_keyring, save_credentials
from storage import DraftStore
from meetings import meetings
from auth import WRITE_SCOPE

ROOT = Path(__file__).resolve().parent


def create_app(test_config=None):
    load_dotenv(ROOT / ".env")
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or None,
        DATABASE=str(ROOT / "instance" / "meeting-assistant.sqlite3"),
        GOOGLE_CLIENT_CONFIG=os.environ.get("GOOGLE_CLIENT_CONFIG", str(ROOT / "credentials.json")),
        GOOGLE_REDIRECT_URI=os.environ.get("GOOGLE_REDIRECT_URI", "http://127.0.0.1:5000/oauth/callback"),
        MAX_CONTENT_LENGTH=32768,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        TRUSTED_HOSTS=["127.0.0.1", "localhost"],
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("Set FLASK_SECRET_KEY to a random value of at least 32 characters in the local .env file.")
    callback = urlparse(app.config["GOOGLE_REDIRECT_URI"])
    app.config["SESSION_COOKIE_SECURE"] = callback.scheme == "https"
    if callback.hostname:
        app.config["TRUSTED_HOSTS"] = list(set(app.config["TRUSTED_HOSTS"] + [callback.hostname]))
    config_path = Path(app.config["GOOGLE_CLIENT_CONFIG"])
    if not config_path.is_absolute():
        app.config["GOOGLE_CLIENT_CONFIG"] = str(ROOT / config_path)
    Path(app.config["DATABASE"]).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    store = DraftStore(app.config["DATABASE"])
    os.chmod(app.config["DATABASE"], 0o600)
    app.extensions["store"] = store
    app.extensions["calendar"] = GoogleCalendar()

    # Werkzeug access logs include OAuth callback query strings. Log safe stages instead.
    logging.getLogger("werkzeug").disabled = True
    for name in ("oauthlib", "requests_oauthlib", "google.auth", "urllib3", "google.adk", "google_adk", "google.genai", "httpx", "mcp"):
        logging.getLogger(name).setLevel(logging.WARNING)

    def google_config():
        return client_configuration(app.config["GOOGLE_CLIENT_CONFIG"], app.config["GOOGLE_REDIRECT_URI"])

    @app.before_request
    def identify_request():
        g.request_id = secrets.token_hex(4)
        session.setdefault("browser", secrets.token_urlsafe(24))
        session.setdefault("csrf", secrets.token_urlsafe(32))
        g.user = store.current_user(session.get("login"))
        if request.method == "POST":
            csrf = request.form.get("csrf_token", "")
            if not csrf or not secrets.compare_digest(csrf, session["csrf"]):
                abort(403, description="Request verification failed. Reload the page and try again.")

    @app.after_request
    def security_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            # Browsers can apply form-action to the POST's redirect destination too.
            "img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'self' https://accounts.google.com"
        )
        if app.config["SESSION_COOKIE_SECURE"]:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    def home(error=None, availability=None):
        try:
            google_config()
            configured = True
        except ValueError:
            configured = False
        today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
        search_start = date.fromisoformat(today)
        while search_start.weekday() >= 5:
            search_start += timedelta(days=1)
        selected_draft = None
        if g.user:
            store.expire()
            if session.get("draft_id"):
                try:
                    selected_draft = store.get(session["draft_id"], g.user["id"])
                except LookupError:
                    session.pop("draft_id", None)
        defaults = {"title": "", "purpose": "", "agenda": "", "attendees": [],
                    "duration": 30, "timezone": "Asia/Kolkata", "date_from": search_start.isoformat(),
                    "date_to": (search_start + timedelta(days=7)).isoformat(),
                    "hour_start": 9, "hour_end": 17, "include_weekends": False}
        return render_template("dashboard.html" if g.user else "index.html", user=g.user, configured=configured,
                               calendar_connected=bool(g.user and store.calendar_connected(g.user["id"])),
                               calendar_writable=bool(g.user and store.calendar_writable(g.user["id"])),
                               csrf_token=session["csrf"], error=error, availability=availability, today=today,
                               draft=selected_draft, meeting=selected_draft["data"]["meeting"] if selected_draft else defaults,
                               pending_operations=store.pending_operations(g.user["id"]) if g.user else [],
                               ai_ready=bool(os.getenv("GOOGLE_API_KEY")))

    @app.template_filter("meeting_time")
    def meeting_time(value, zone_name):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZoneInfo(zone_name)).strftime("%a %d %b %Y, %H:%M")

    @app.get("/")
    def index():
        return home()

    @app.post("/meetings/reset")
    def reset_meeting():
        require_user()
        store.clear_chats(g.user["id"])
        session.pop("draft_id", None)
        return redirect(url_for("index") + "#meeting")

    def require_user():
        if not g.user:
            abort(401, description="Sign in with Google before connecting your calendar.")

    @app.post("/calendar/connect")
    def connect_calendar():
        require_user()
        try:
            require_secure_keyring()
            pending = calendar_authorization_request(google_config(), app.config["GOOGLE_REDIRECT_URI"], g.user["email"])
        except Exception:
            app.logger.warning("request=%s stage=calendar_consent status=setup_failed", g.request_id)
            abort(503, description="Calendar connection could not start. Check OAuth settings and your OS credential store; see README.md.")
        store.save_oauth_request(pending, session["browser"], intent="calendar", user_id=g.user["id"])
        app.logger.info("request=%s stage=calendar_consent status=redirect", g.request_id)
        return redirect(pending["url"])

    @app.post("/calendar/enable-scheduling")
    def enable_scheduling():
        require_user()
        try:
            require_secure_keyring()
            pending = calendar_authorization_request(google_config(), app.config["GOOGLE_REDIRECT_URI"], g.user["email"], write=True)
        except Exception:
            abort(503, description="Could not start scheduling consent. Check OAuth settings and your OS credential store.")
        store.save_oauth_request(pending, session["browser"], intent="calendar_write", user_id=g.user["id"])
        app.logger.info("request=%s stage=scheduling_consent status=redirect", g.request_id)
        return redirect(pending["url"])

    @app.post("/auth/google")
    def google_login():
        try:
            pending = authorization_request(google_config(), app.config["GOOGLE_REDIRECT_URI"])
        except Exception:
            app.logger.warning("request=%s stage=oauth_start status=failed", g.request_id)
            abort(503, description="Google login is not configured correctly. Follow the README setup steps.")
        store.save_oauth_request(pending, session["browser"])
        app.logger.info("request=%s stage=oauth_start status=redirect", g.request_id)
        return redirect(pending["url"])

    @app.get("/oauth/callback")
    def google_callback():
        state = request.args.get("state", "")
        try:
            pending = store.consume_oauth_request(state, session["browser"])
        except ValueError:
            abort(400, description="Login expired or could not be verified. Start again.")
        if request.args.get("error") or not request.args.get("code"):
            app.logger.info("request=%s stage=oauth_callback status=declined", g.request_id)
            abort(400, description="Google sign-in was not completed. You can try again.")
        if pending["intent"] in {"calendar", "calendar_write"}:
            require_user()
            if pending["user_id"] != g.user["id"]:
                abort(403, description="The signed-in account changed. Start Calendar connection again.")
            try:
                identity, credentials = exchange_calendar(google_config(), app.config["GOOGLE_REDIRECT_URI"],
                                                           pending, request.args["code"])
            except Exception:
                app.logger.warning("request=%s stage=calendar_verification status=failed", g.request_id)
                abort(400, description="Calendar consent could not be verified. Grant availability access and try connecting again.")
            if identity["google_sub"] != store.google_subject(g.user["id"]):
                app.logger.warning("request=%s stage=calendar_verification status=account_mismatch", g.request_id)
                abort(403, description="Choose the same Google account you used to sign in. Calendar was not connected.")
            try:
                save_credentials(g.user["id"], credentials)
            except Exception:
                app.logger.warning("request=%s stage=calendar_token_store status=failed", g.request_id)
                abort(503, description="Calendar tokens could not be saved securely. Unlock or configure your OS credential store and reconnect.")
            granted = credentials.granted_scopes if credentials.granted_scopes is not None else credentials.scopes
            if isinstance(granted, str):
                granted = granted.split()
            store.set_calendar_connected(g.user["id"], True, can_write=WRITE_SCOPE in (granted or []))
            app.logger.info("request=%s stage=calendar_connection status=completed", g.request_id)
            return redirect(url_for("index"))
        try:
            identity = exchange_identity(google_config(), app.config["GOOGLE_REDIRECT_URI"],
                                         pending, request.args["code"])
        except Exception:
            # Provider exceptions may contain tokens, URLs, or account details.
            app.logger.warning("request=%s stage=identity_verification status=failed", g.request_id)
            abort(400, description="Google sign-in could not be verified. Start again or check your OAuth configuration.")
        store.revoke_login(session.get("login"))
        login = store.create_login(identity)
        session.clear()
        session["login"] = login
        session.permanent = True
        app.logger.info("request=%s stage=google_login status=completed", g.request_id)
        return redirect(url_for("index"))

    @app.post("/calendar/disconnect")
    def disconnect_calendar():
        require_user()
        try:
            disconnect(g.user["id"])
        except Exception:
            app.logger.warning("request=%s stage=calendar_disconnect status=failed", g.request_id)
            abort(503, description="Could not remove saved tokens. Unlock your OS credential store and try again.")
        store.set_calendar_connected(g.user["id"], False)
        app.logger.info("request=%s stage=calendar_disconnect status=completed", g.request_id)
        return redirect(url_for("index"))

    @app.post("/calendar/availability")
    def check_availability():
        require_user()
        if not store.calendar_connected(g.user["id"]):
            abort(400, description="Connect Google Calendar before checking availability.")
        try:
            first = date.fromisoformat(request.form.get("date_from", ""))
            last = date.fromisoformat(request.form.get("date_to", ""))
            zone_name = request.form.get("timezone", "")
            zone = ZoneInfo(zone_name)
            if first < datetime.now(zone).date() or last < first or (last - first).days > 14:
                raise ValueError
        except (ValueError, ZoneInfoNotFoundError):
            abort(400, description="Choose a valid timezone and a current or future date range of at most 15 days.")
        meeting = {"date_from": first.isoformat(), "date_to": last.isoformat(),
                   "timezone": zone_name, "attendees": []}
        try:
            result = app.extensions["calendar"].availability(g.user["id"], meeting)
            # Only selected start/end values reach the page, never provider response bodies.
            periods = [{"start": datetime.fromisoformat(item["start"].replace("Z", "+00:00")).astimezone(zone).strftime("%a %d %b, %H:%M"),
                        "end": datetime.fromisoformat(item["end"].replace("Z", "+00:00")).astimezone(zone).strftime("%a %d %b, %H:%M")}
                       for item in result["busy"]]
        except CalendarError as error:
            app.logger.warning("request=%s stage=availability status=failed category=%s", g.request_id, error.code)
            abort(502, description=str(error))
        except Exception:
            app.logger.warning("request=%s stage=availability status=failed", g.request_id)
            abort(502, description="Availability could not be checked. Enable Google Calendar API for your project, or reconnect Calendar if access expired.")
        app.logger.info("request=%s stage=availability status=completed intervals=%d", g.request_id, len(periods))
        return home(availability={"periods": periods, "timezone": zone_name,
                                  "date_from": first.isoformat(), "date_to": last.isoformat()})

    @app.post("/logout")
    def logout():
        store.revoke_login(session.get("login"))
        session.clear()
        app.logger.info("request=%s stage=logout status=completed", g.request_id)
        return redirect(url_for("index"))

    @app.get("/api/me")
    def me():
        if not g.user:
            return jsonify(error="Sign in with Google first."), 401
        return jsonify(user=g.user)

    @app.errorhandler(HTTPException)
    def safe_http_error(error):
        if isinstance(error, SecurityError):
            return "Invalid request host.", 400, {"Content-Type": "text/plain"}
        return home(error=error.description), error.code

    app.register_blueprint(meetings)

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    application = create_app()
    application.logger.info("stage=startup status=ready url=http://127.0.0.1:5000")
    application.run(host="127.0.0.1", port=5000, debug=False)
