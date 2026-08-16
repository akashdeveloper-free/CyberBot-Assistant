"""Small HTTP health server for Render and uptime checks."""

from __future__ import annotations

from threading import Thread

from flask import Flask, jsonify
from werkzeug.serving import BaseWSGIServer, make_server


def create_health_app() -> Flask:
    """Create the health-only Flask application."""

    app = Flask(__name__)

    @app.get("/")
    def root() -> str:
        return "NovaBot is running"

    @app.get("/health")
    def health() -> tuple[object, int]:
        return jsonify({"status": "ok", "service": "NovaBot"}), 200

    return app


class HealthServer:
    """Run the health endpoint in a stoppable background thread."""

    def __init__(self, port: int) -> None:
        self.port = port
        self._server: BaseWSGIServer | None = None
        self._thread: Thread | None = None

    def start(self) -> None:
        """Bind on all interfaces and start serving requests."""

        if self._thread is not None:
            raise RuntimeError("The health server has already been started.")

        self._server = make_server(
            host="0.0.0.0",
            port=self.port,
            app=create_health_app(),
            threaded=True,
        )
        self._thread = Thread(
            target=self._server.serve_forever,
            name="cyberbot-health",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the HTTP server and wait briefly for its thread."""

        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None

        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=5)