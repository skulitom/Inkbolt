"""A minimal MCP stdio client for measuring a local server.

Library use: s = Session([exe, args...]); s.initialize(); s.request("tools/list"); s.call(name, args); s.close()
Every reply keeps its raw line, so byte counts are wire bytes (UTF-8 JSON-RPC line including the newline).
CLI use: python -I mcp_session.py <out-raw.json> <exe> [args...]  -> writes the raw tools/list reply line.
"""
import json
import subprocess
import sys
import time


class Session:
    def __init__(self, cmd, env=None):
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env=env)
        self.next_id = 1

    def _send(self, msg):
        self.proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def request(self, method, params=None, timeout=600):
        rid = self.next_id
        self.next_id += 1
        t0 = time.perf_counter()
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError(f"server closed stdout while waiting for {method}")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") == rid:
                return msg, line, round((time.perf_counter() - t0) * 1000, 1)
        raise RuntimeError(f"timeout waiting for {method}")

    def initialize(self):
        msg, line, ms = self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                    "clientInfo": {"name": "compare-probe", "version": "1"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return msg, line, ms

    def call(self, name, arguments, timeout=600):
        return self.request("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=30)
        except Exception:
            self.proc.kill()
        return self.proc.stderr.read().decode("utf-8", "replace")


if __name__ == "__main__":
    out, cmd = sys.argv[1], sys.argv[2:]
    s = Session(cmd)
    s.initialize()
    msg, line, ms = s.request("tools/list")
    s.close()
    with open(out, "wb") as f:
        f.write(line)
    tools = msg["result"]["tools"]
    print(json.dumps({"tools": len(tools), "wire_bytes": len(line), "ms": ms}))
