"""
DeepSeek Token Monitor — 反向代理服务器

将请求转发到上游代理 (127.0.0.1:15721)，
并从响应中提取 token 用量。

因为 Claude Code 是通过 15721 代理发送 Anthropic 格式请求到 DeepSeek 的，
所以监控器需要作为中间层：Client → :7890 → :15721 → api.deepseek.com
"""

from __future__ import annotations

import json
import http.server
import threading
from typing import Any, TYPE_CHECKING

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if TYPE_CHECKING:
    from token_tracker import TokenTracker


# ── 请求处理器 ──────────────────────────────────────────────


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    """将请求转发到上游代理并提取 token 用量."""

    tracker: "TokenTracker" = None  # type: ignore[assignment]
    upstream_url: str = "http://127.0.0.1:15721"  # 你的 Anthropic→DeepSeek 代理
    timeout: int = 300

    def log_message(self, format: str, *args: Any) -> None:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[proxy {ts}] {format % args}")

    # ── HTTP 方法 ──────────────────────────────────────────

    def do_GET(self) -> None:
        self._proxy("GET")

    def do_POST(self) -> None:
        self._proxy("POST")

    def do_PUT(self) -> None:
        self._proxy("PUT")

    def do_DELETE(self) -> None:
        self._proxy("DELETE")

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ── 核心代理逻辑 ──────────────────────────────────────

    def _proxy(self, method: str) -> None:
        target = f"{self.upstream_url}{self.path}"

        cl = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(cl) if cl > 0 else b""

        fwd = {}
        skip = {"host", "content-length", "connection", "transfer-encoding"}
        for k, v in self.headers.items():
            if k.lower() not in skip:
                fwd[k] = v
        fwd.setdefault("Accept-Encoding", "identity")

        try:
            resp = requests.request(
                method=method, url=target, headers=fwd,
                data=body if body else None,
                stream=True, timeout=self.timeout, verify=False,
            )
            ct = resp.headers.get("Content-Type", "")
            if "text/event-stream" in ct or "application/x-ndjson" in ct:
                self._stream(resp)
            else:
                self._nonstream(resp)
        except requests.exceptions.Timeout:
            self._err(504, "Upstream timeout")
        except requests.exceptions.ConnectionError:
            self._err(502, "Cannot connect to upstream proxy at 127.0.0.1:15721")
        except Exception as e:
            print(f"[proxy] Error: {e}")
            self._err(500, str(e))

    # ── 非流式响应 ─────────────────────────────────────────

    def _nonstream(self, resp: requests.Response) -> None:
        body = resp.content
        try:
            data = resp.json()
            self._record(data)
            # Anthropic 格式：内容可能在 content 数组里，但 DeepSeek 的 usage 可能在 message 层级
            # 同时检查多种可能的位置
            if "usage" not in data:
                # 有些代理会把 usage 放在 message 层级
                if isinstance(data, dict):
                    for key in data:
                        if isinstance(data[key], dict) and "usage" in data[key]:
                            self._record(data[key])
        except Exception:
            pass

        self.send_response(resp.status_code)
        self._copy_hdrs(resp)
        self.end_headers()
        self.wfile.write(body)

    # ── 流式响应 ───────────────────────────────────────────

    def _stream(self, resp: requests.Response) -> None:
        self.send_response(200)
        self._copy_hdrs(resp)
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
                        break
        except Exception:
            pass
        self._parse_sse(chunks)

    def _parse_sse(self, chunks: list[bytes]) -> None:
        text = b"".join(chunks).decode("utf-8", errors="replace")
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("data: ") and line != "data: [DONE]":
                try:
                    obj = json.loads(line[6:])
                    self._record(obj)
                except json.JSONDecodeError:
                    pass

    # ── Token 提取 (兼容多种格式) ─────────────────────────

    def _record(self, obj: dict) -> None:
        if self.tracker is None:
            return

        # 尝试多种方式找到 usage
        usage = None

        # 方式1: 直接的 usage 字段 (OpenAI/DeepSeek 格式)
        if "usage" in obj:
            usage = obj["usage"]

        # 方式2: Anthropic Messages API 格式 — usage 在顶层
        elif "input_tokens" in obj and "output_tokens" in obj:
            usage = {
                "prompt_tokens": obj.get("input_tokens", 0),
                "completion_tokens": obj.get("output_tokens", 0),
                "prompt_cache_hit_tokens": obj.get("cache_creation_input_tokens", 0),
                "prompt_cache_miss_tokens": obj.get("cache_read_input_tokens", 0),
            }

        # 方式3: DeepSeek 流式 chunk 格式 (choices[0].delta 内)
        elif "choices" in obj:
            choices = obj.get("choices", [])
            if choices:
                delta = choices[0]
                if "usage" in delta:
                    usage = delta["usage"]
                # 有些代理放 usage 在 choices[0] 层级
                elif "input_tokens" in delta:
                    u = {}
                    for f in ["prompt_tokens", "completion_tokens", "total_tokens",
                               "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"]:
                        if f in delta:
                            u[f] = delta[f]
                    if u:
                        usage = u

        if not usage:
            return

        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        ch = usage.get("prompt_cache_hit_tokens", 0)
        cm = usage.get("prompt_cache_miss_tokens", 0)
        ctd = usage.get("completion_tokens_details", {})
        reasoning = ctd.get("reasoning_tokens", 0) if isinstance(ctd, dict) else 0

        # 如果 Anthropic 字段名被用了
        if prompt == 0 and completion == 0:
            prompt = usage.get("input_tokens", 0)
            completion = usage.get("output_tokens", 0)
            ch = usage.get("cache_read_input_tokens", 0) or usage.get("cache_hit_tokens", 0)
            cm = usage.get("cache_creation_input_tokens", 0) or usage.get("cache_miss_tokens", 0)

        if prompt > 0 or completion > 0:
            print(f"[proxy] 📊 Recorded: {prompt} prompt + {completion} completion = {prompt + completion} tokens")
            self.tracker.add_usage(
                prompt_tokens=prompt,
                completion_tokens=completion,
                cache_hit=ch,
                cache_miss=cm,
                reasoning=reasoning,
            )

    # ── 辅助 ──────────────────────────────────────────────

    def _copy_hdrs(self, resp: requests.Response) -> None:
        skip = {"transfer-encoding", "content-encoding", "connection",
                "keep-alive", "proxy-authenticate", "proxy-authorization",
                "te", "trailer", "upgrade"}
        for k, v in resp.headers.items():
            if k.lower() not in skip:
                self.send_header(k, v)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Max-Age", "86400")

    def _err(self, code: int, msg: str) -> None:
        body = json.dumps({"error": {"message": msg, "type": "proxy_error"}}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)


# ── 服务器 ─────────────────────────────────────────────────


class ProxyServer:
    """管理代理服务器生命周期."""

    def __init__(self, tracker: "TokenTracker", port: int = 7890, host: str = "127.0.0.1"):
        self._host = host
        self._port = port
        self._tracker = tracker
        ProxyHandler.tracker = tracker
        self._server = http.server.HTTPServer((host, port), ProxyHandler)
        self._server.timeout = 1
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
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True, name="proxy")
        self._thread.start()
        print(f"[proxy] 代理已启动: http://{self._host}:{self._port}")
        print(f"[proxy] 上游: {ProxyHandler.upstream_url}")

    def stop(self) -> None:
        self._running = False
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        print("[proxy] 代理已停止")

    def _serve(self) -> None:
        try:
            while self._running:
                self._server.handle_request()
        except Exception as e:
            print(f"[proxy] 服务器错误: {e}")
        finally:
            self._running = False

    def restart(self) -> None:
        self.stop()
        self._server = http.server.HTTPServer((self._host, self._port), ProxyHandler)
        ProxyHandler.tracker = self._tracker
        self.start()
