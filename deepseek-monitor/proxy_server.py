"""
DeepSeek Token Monitor — Reverse Proxy Server

Runs a local HTTP server that:
1. Receives HTTP requests intended for api.deepseek.com
2. Forwards them to the real DeepSeek API over HTTPS
3. Extracts usage data from responses
4. Returns the response to the original client unchanged

Supports both streaming (SSE) and non-streaming responses.
"""

from __future__ import annotations

import json
import http.server
import threading
from typing import Any, TYPE_CHECKING

import requests
import urllib3

# Suppress InsecureRequestWarning if we ever need to skip verification
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if TYPE_CHECKING:
    from token_tracker import TokenTracker


# ── Proxy Request Handler ──────────────────────────────────────────


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    """
    HTTP request handler that proxies requests to api.deepseek.com.
    The `tracker` class attribute must be set before starting the server.
    """

    tracker: "TokenTracker" = None  # type: ignore[assignment]
    deepseek_base: str = "https://api.deepseek.com"
    timeout: int = 120

    # ── Logging helpers ────────────────────────────────────────────

    def log_message(self, format: str, *args: Any) -> None:
        """Override to add timestamp prefix."""
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        msg = format % args
        print(f"[proxy {ts}] {msg}")

    # ── HTTP Methods ───────────────────────────────────────────────

    def do_GET(self) -> None:
        self._proxy_request("GET")

    def do_POST(self) -> None:
        self._proxy_request("POST")

    def do_PUT(self) -> None:
        self._proxy_request("PUT")

    def do_DELETE(self) -> None:
        self._proxy_request("DELETE")

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ── Core proxy logic ───────────────────────────────────────────

    def _proxy_request(self, method: str) -> None:
        """Forward the incoming request to DeepSeek API and return response."""
        target_url = f"{self.deepseek_base}{self.path}"

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        # Copy headers, stripping hop-by-hop headers
        forward_headers = {}
        skip_headers = {"host", "content-length", "connection", "transfer-encoding"}
        for key, value in self.headers.items():
            if key.lower() not in skip_headers:
                forward_headers[key] = value

        # Ensure we accept the response properly
        forward_headers.setdefault("Accept-Encoding", "identity")

        try:
            resp = requests.request(
                method=method,
                url=target_url,
                headers=forward_headers,
                data=body if body else None,
                stream=True,
                timeout=self.timeout,
                verify=True,
            )

            content_type = resp.headers.get("Content-Type", "")

            if "text/event-stream" in content_type or "application/x-ndjson" in content_type:
                self._handle_streaming(resp)
            else:
                self._handle_non_streaming(resp)

        except requests.exceptions.Timeout:
            self._send_error(504, "Gateway Timeout — upstream DeepSeek API did not respond")
        except requests.exceptions.ConnectionError:
            self._send_error(502, "Bad Gateway — could not connect to api.deepseek.com")
        except Exception as e:
            print(f"[proxy] Error proxying {method} {self.path}: {e}")
            self._send_error(500, f"Internal Proxy Error: {str(e)}")

    # ── Non-streaming response ─────────────────────────────────────

    def _handle_non_streaming(self, resp: requests.Response) -> None:
        """Handle a standard JSON response."""
        response_body = resp.content

        # Parse usage from JSON response
        try:
            data = resp.json()
            if "usage" in data:
                self._extract_and_record_usage(data["usage"])
        except (json.JSONDecodeError, ValueError):
            pass  # Not JSON, skip usage extraction

        # Forward response to client
        self.send_response(resp.status_code)
        self._copy_response_headers(resp)
        self.end_headers()
        self.wfile.write(response_body)

    # ── Streaming (SSE) response ───────────────────────────────────

    def _handle_streaming(self, resp: requests.Response) -> None:
        """
        Handle Server-Sent Events streaming response.
        Streams chunks to the client in real-time while buffering
        for usage extraction from the final chunk.
        """
        self.send_response(200)
        self._copy_response_headers(resp)
        self.end_headers()

        chunks: list[bytes] = []
        try:
            for chunk in resp.iter_content(chunk_size=None):
                if chunk:
                    chunks.append(chunk)
                    try:
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    except (BrokenPipeError, OSError):
                        # Client disconnected
                        break
        except requests.exceptions.ChunkedEncodingError:
            pass  # Stream interrupted

        # After streaming completes, extract usage from accumulated data
        self._extract_usage_from_stream_chunks(chunks)

    def _extract_usage_from_stream_chunks(self, chunks: list[bytes]) -> None:
        """
        Parse SSE chunks to find and extract usage data.
        Looks for 'data: {...}' lines containing a 'usage' field.
        """
        full_text = b"".join(chunks).decode("utf-8", errors="replace")
        for line in full_text.split("\n"):
            line = line.strip()
            if line.startswith("data: ") and line != "data: [DONE]":
                data_str = line[6:]
                try:
                    obj = json.loads(data_str)
                    if "usage" in obj:
                        self._extract_and_record_usage(obj["usage"])
                except json.JSONDecodeError:
                    pass

    # ── Usage extraction ───────────────────────────────────────────

    def _extract_and_record_usage(self, usage: dict[str, Any]) -> None:
        """Extract token counts from a DeepSeek usage object and record them."""
        if self.tracker is None:
            return

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cache_hit = usage.get("prompt_cache_hit_tokens", 0)
        cache_miss = usage.get("prompt_cache_miss_tokens", 0)

        # DeepSeek may include completion_tokens_details
        ctd = usage.get("completion_tokens_details", {})
        reasoning = ctd.get("reasoning_tokens", 0) if isinstance(ctd, dict) else 0

        self.tracker.add_usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_hit=cache_hit,
            cache_miss=cache_miss,
            reasoning=reasoning,
        )

    # ── Response helpers ───────────────────────────────────────────

    def _copy_response_headers(self, resp: requests.Response) -> None:
        """Copy response headers from upstream, skipping hop-by-hop."""
        skip = {"transfer-encoding", "content-encoding", "connection",
                "keep-alive", "proxy-authenticate", "proxy-authorization",
                "te", "trailer", "upgrade"}
        for key, value in resp.headers.items():
            if key.lower() not in skip:
                self.send_header(key, value)

    def _send_cors_headers(self) -> None:
        """Send permissive CORS headers."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Max-Age", "86400")

    def _send_error(self, code: int, message: str) -> None:
        """Send an error response to the client."""
        body = json.dumps({"error": {"message": message, "type": "proxy_error"}}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)


# ── Proxy Server ───────────────────────────────────────────────────


class ProxyServer:
    """Manages the HTTP proxy server lifecycle."""

    def __init__(self, tracker: "TokenTracker", port: int = 7890, host: str = "127.0.0.1"):
        self._host = host
        self._port = port
        self._tracker = tracker

        # Inject tracker into handler class
        ProxyHandler.tracker = tracker

        self._server = http.server.HTTPServer((host, port), ProxyHandler)
        self._server.timeout = 1  # allow checking is_running periodically
        self._thread: threading.Thread | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def port(self) -> int:
        return self._port

    @property
    def host(self) -> str:
        return self._host

    def start(self) -> None:
        """Start the proxy server in a daemon thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True, name="proxy-server")
        self._thread.start()
        print(f"[proxy] Started reverse proxy on http://{self._host}:{self._port}")
        print(f"[proxy] Point your DeepSeek client to http://{self._host}:{self._port}")

    def stop(self) -> None:
        """Stop the proxy server."""
        self._running = False
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        print("[proxy] Proxy server stopped.")

    def _serve(self) -> None:
        """Internal: serve loop."""
        try:
            while self._running:
                self._server.handle_request()
        except Exception as e:
            print(f"[proxy] Server error: {e}")
        finally:
            self._running = False

    def restart(self) -> None:
        """Restart the proxy server (e.g. after port change)."""
        self.stop()
        # Recreate server with current port
        self._server = http.server.HTTPServer((self._host, self._port), ProxyHandler)
        ProxyHandler.tracker = self._tracker
        self.start()
