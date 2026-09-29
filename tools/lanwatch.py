#!/usr/bin/env python3
"""Listen for Azeno LAN discovery broadcasts (Vidos X doorbell ring test).

The Vidos app broadcasts ``ASZENO.SEARCH.V4.1`` to UDP 5000 when its connect
flow wakes (observed 2026-10-02: 4 packets @1 Hz, apparently push-triggered
while the app was NOT opened by the user), and the door station answers with
``ASZENO.SEARCH.V4`` on UDP 5001 15-85 ms later.

Run this, then ring the bell and note the time. A scan burst within ~2 s of
each ring (and silence otherwise) = we have the LAN ring signal.
"""

from __future__ import annotations

import select
import socket
import sys
import time

MAGIC = b"ASZENO"


def open_socket(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", port))
    return sock


def main() -> int:
    ports = [int(p) for p in sys.argv[1:]] or [5000, 5001]
    socks: list[tuple[int, socket.socket]] = []
    for port in ports:
        try:
            socks.append((port, open_socket(port)))
        except OSError as exc:
            print(f"[!] cannot bind UDP {port}: {exc}")
    if not socks:
        return 1
    print(f"[lanwatch] listening on UDP {', '.join(map(str, ports))}")
    print("[lanwatch] ring the bell and note the wall-clock time; Ctrl+C stops")
    while True:
        readable, _, _ = select.select([s for _, s in socks], [], [])
        stamp = time.strftime("%H:%M:%S")
        for sock in readable:
            data, addr = sock.recvfrom(2048)
            port = next(p for p, s in socks if s is sock)
            tag = "SCAN" if data.startswith(MAGIC) and port == 5000 else (
                "REPLY" if data.startswith(MAGIC) else "OTHER"
            )
            preview = data[:16].decode("ascii", "replace")
            print(
                f"[{stamp}] {tag} :{port} <- {addr[0]}:{addr[1]} "
                f"len={len(data)} head={preview!r}"
            )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[lanwatch] stopped")
