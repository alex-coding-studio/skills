import json
import os
from pathlib import Path
import socket
import stat
import struct
import subprocess
import time
import uuid


def desktop_is_idle(thread):
    endpoint = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "ipc" / "ipc.sock"
    info = endpoint.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError("Desktop IPC endpoint is not an owned socket")
    deadline = time.monotonic() + 8
    client_id = None
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(8)
        connection.connect(str(endpoint))

        def send(value):
            data = json.dumps(value).encode("utf-8")
            connection.settimeout(max(0.001, deadline - time.monotonic()))
            connection.sendall(struct.pack("<I", len(data)) + data)

        def read_exact(length):
            parts = []
            while length:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Desktop state timed out")
                connection.settimeout(remaining)
                part = connection.recv(min(length, 65536))
                if not part:
                    raise RuntimeError("Desktop IPC disconnected")
                parts.append(part)
                length -= len(part)
            return b"".join(parts)

        def receive():
            length = struct.unpack("<I", read_exact(4))[0]
            if not 0 < length <= 64 * 1024 * 1024:
                raise RuntimeError("Desktop state frame exceeds the supported bound")
            return json.loads(read_exact(length))

        request_id = str(uuid.uuid4())
        send({"type": "request", "requestId": request_id, "method": "initialize",
              "params": {"clientType": "cli"}, "version": 0})
        try:
            while time.monotonic() < deadline:
                message = receive()
                if message.get("type") == "client-discovery-request":
                    send({"type": "client-discovery-response", "requestId": message["requestId"],
                          "response": {"canHandle": False}})
                if message.get("type") == "response" and message.get("requestId") == request_id:
                    if message.get("resultType") != "success":
                        raise RuntimeError("Desktop IPC initialization failed")
                    client_id = message["result"]["clientId"]
                    send({"type": "broadcast", "method": "thread-stream-following-changed",
                          "sourceClientId": client_id, "version": 1,
                          "params": {"hostId": "local", "conversationId": thread, "following": True}})
                if message.get("method") != "thread-stream-state-changed" or message.get("version") != 11:
                    continue
                params = message.get("params", {})
                change = params.get("change", {})
                if params.get("hostId") != "local" or params.get("conversationId") != thread or change.get("type") != "snapshot":
                    continue
                state = change.get("conversationState", {})
                status = state.get("threadRuntimeStatus", {}).get("type")
                if status not in ("idle", "active", "notLoaded", "systemError"):
                    raise RuntimeError("Desktop runtime status is unavailable")
                return status == "idle"
            raise TimeoutError("Desktop state timed out")
        finally:
            if client_id is not None:
                try:
                    send({"type": "broadcast", "method": "thread-stream-following-changed",
                          "sourceClientId": client_id, "version": 1,
                          "params": {"hostId": "local", "conversationId": thread, "following": False}})
                except (OSError, TimeoutError):
                    pass


def queue_message(executable, thread, message):
    subprocess.run([executable, "queue", "--thread", thread, "--message", message], capture_output=True, text=True, timeout=45, check=True)
