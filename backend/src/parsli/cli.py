"""Parsli CLI — run sync operations and start the API server from the command line."""

import argparse
import logging
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import uvicorn

_CLI_CALLBACK_PORT = 8765
_CLI_REDIRECT_URI = f"http://localhost:{_CLI_CALLBACK_PORT}/callback"

logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        level=level,
    )


# ── OAuth browser flow ────────────────────────────────────────────────────────

def _run_cli_oauth_flow(oauth, account_id: str) -> bool:
    """Open the browser for Gmail OAuth and handle the callback locally.

    Starts a temporary HTTP server on localhost:{_CLI_CALLBACK_PORT} to receive
    the OAuth redirect, completes the token exchange, and saves the credentials.

    Returns True on success, False on failure or timeout.
    """
    result: dict = {"success": False, "error": ""}
    done = threading.Event()

    class _CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return

            params = parse_qs(parsed.query)
            code = (params.get("code") or [""])[0]
            state = (params.get("state") or [""])[0]

            try:
                email, credentials = oauth.complete_auth_flow(code, state)
                oauth.save_token(account_id, credentials)
                result["success"] = True
                body = (
                    b"<html><body><p>Connected! You can close this tab.</p>"
                    b"<script>window.close();</script></body></html>"
                )
            except Exception as exc:
                result["error"] = str(exc)
                body = f"<html><body><p>Auth error: {exc}</p></body></html>".encode()

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
            done.set()

        def log_message(self, *args) -> None:  # noqa: ANN002
            pass  # suppress noisy default HTTP logging

    server = HTTPServer(("localhost", _CLI_CALLBACK_PORT), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        auth_url, _ = oauth.start_auth_flow(redirect_uri=_CLI_REDIRECT_URI)
        print(f"\nOpening Gmail authorization in your browser…")
        print(f"If the browser does not open, visit:\n  {auth_url}\n")
        webbrowser.open(auth_url)

        if not done.wait(timeout=120):
            print("Timed out waiting for browser authorization (120 s).")
            return False

        if result["success"]:
            print("Authorization successful.\n")
        else:
            print(f"Authorization failed: {result['error']}")
    finally:
        server.shutdown()

    return result["success"]


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_serve(args: argparse.Namespace) -> None:
    from .api.main import create_app
    from .config import AppConfig

    config = AppConfig()
    app = create_app(config)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def cmd_sync(args: argparse.Namespace) -> None:
    from .config import AppConfig
    from .gmail.auth import GmailOAuthManager, TokenMissingError
    from .services.sync_service import SyncService

    config = AppConfig()
    oauth = GmailOAuthManager(
        credentials_path=config.credentials_path,
        tokens_dir=config.tokens_dir,
    )
    svc = SyncService.from_config(config)

    def _do_sync() -> dict:
        if args.mode == "initial":
            return svc.initial_sync(args.account_id)
        return svc.incremental_sync(args.account_id)

    try:
        result = _do_sync()
    except TokenMissingError:
        print(f"No Gmail token found for '{args.account_id}'. Starting authorization…")
        if not _run_cli_oauth_flow(oauth, args.account_id):
            sys.exit(1)
        # Retry once after successful OAuth
        try:
            result = _do_sync()
        except Exception as exc:
            print(f"Sync failed after authorization: {exc}")
            sys.exit(1)
    except ValueError as exc:
        print(f"Sync error: {exc}")
        sys.exit(1)

    print(f"Sync complete: {result}")


def cmd_rebuild(args: argparse.Namespace) -> None:
    from .config import AppConfig
    from .db.session import ensure_schema, make_engine, make_session_factory
    from .services.shipment_resolution_service import ShipmentResolutionService

    config = AppConfig()
    engine = make_engine(config.database.sqlite_path)
    ensure_schema(engine)
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        svc = ShipmentResolutionService(session, config.processing)
        svc.rebuild_all()
        session.commit()
    print("Rebuild complete")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(prog="parsli", description="Parsli parcel tracker")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    serve_p = sub.add_parser("serve", help="Start the FastAPI server")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8000)
    serve_p.set_defaults(func=cmd_serve)

    sync_p = sub.add_parser("sync", help="Run a Gmail sync (prompts for auth if needed)")
    sync_p.add_argument("account_id", help="Account UUID or email address")
    sync_p.add_argument(
        "--mode", choices=["initial", "incremental"], default="incremental"
    )
    sync_p.set_defaults(func=cmd_sync)

    rebuild_p = sub.add_parser("rebuild", help="Rebuild all shipment timelines")
    rebuild_p.set_defaults(func=cmd_rebuild)

    args = parser.parse_args()
    _setup_logging(args.verbose)
    args.func(args)


if __name__ == "__main__":
    main()
