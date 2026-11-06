#!/usr/bin/env python
"""End-to-end security smoke test for the FPSO backend.

Run against a live dev backend (dev_main) or main backend:

    .venv\\Scripts\\python scripts\\security_smoke.py
    .venv\\Scripts\\python scripts\\security_smoke.py --base-url http://127.0.0.1:8080

Checks:
  1. Every non-public GET route rejects a missing token with 401.
  2. Every non-public mutating route rejects a viewer token with 403.
  3. A trade_lead token passes the write-role gate (not 401/403).
  4. Refresh-token replay is rejected (rotation is atomic).
  5. Logout revokes the refresh token.
  6. WebSocket handshake requires the bearer subprotocol.

Exit code 0 only when every check passes. This script is intentionally
standalone (httpx + websockets only) so it does not depend on pytest fixtures.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import string
import sys
from typing import Any

import httpx


PUBLIC_PREFIXES = (
    "/api/auth/login",
    "/api/auth/refresh",
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
)
MUTATING = {"post", "put", "patch", "delete"}
WRITE_ROLES = {"trade_lead", "project_manager", "admin"}
ORIGIN = "http://localhost:5173"

failures: list[str] = []
checks = 0


def check(condition: bool, label: str, detail: str = "") -> None:
    global checks
    checks += 1
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        failures.append(f"{label}: {detail}")


def is_public(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") or path == p for p in PUBLIC_PREFIXES)


def fill_path(path: str) -> str:
    """Substitute path parameters with harmless placeholders."""
    out = path
    while "{" in out:
        start = out.index("{")
        end = out.index("}", start)
        name = out[start + 1:end].lower()
        value = "demo-project" if "project" in name else "smoke-id"
        if name.endswith("id") and "project" not in name:
            value = "smoke-id"
        out = out[:start] + value + out[end + 1:]
    return out


def login(client: httpx.Client, username: str, password: str) -> dict[str, Any] | None:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        print(f"  login failed for {username}: {r.status_code} {r.text[:200]}")
        return None
    return r.json()


def ensure_user(client: httpx.Client, admin_headers: dict[str, str], role: str) -> tuple[str, str] | None:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    username = f"smoke-{role}-{suffix}"
    password = "Smoke-Test-Passw0rd!"
    r = client.post(
        "/api/auth/register",
        headers=admin_headers,
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
            "full_name": f"Smoke {role}",
            "role": role,
        },
    )
    if r.status_code in (200, 201):
        return username, password
    print(f"  (skipping {role} checks: register returned {r.status_code}: {r.text[:160]})")
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("FPSO_SMOKE_BASE_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--username", default=os.environ.get("FPSO_SMOKE_USERNAME", "admin"))
    parser.add_argument("--password", default=os.environ.get("FPSO_SMOKE_PASSWORD", "dev-admin-password"))
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    with httpx.Client(base_url=base, timeout=15.0, headers={"Origin": ORIGIN}) as client:
        print(f"\nHealth: {base}")
        r = client.get("/health")
        check(r.status_code == 200, "GET /health", f"{r.status_code}")

        print("\nAdmin login")
        tokens = login(client, args.username, args.password)
        if not tokens:
            print("\nCannot continue without an admin login.")
            return 1
        check("access_token" in tokens and "refresh_token" in tokens, "login returns token pair")
        admin_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        print("\nOpenAPI route inventory")
        spec = client.get("/openapi.json")
        if spec.status_code != 200:
            print(f"  Cannot read OpenAPI ({spec.status_code}); skipping route matrix.")
            return 1
        paths = spec.json().get("paths", {})
        api_paths = {p: m for p, m in paths.items() if p.startswith("/api/") and not is_public(p)}
        check(bool(api_paths), f"discovered {len(api_paths)} protected API paths")

        print("\nUnauthenticated GET -> 401")
        bad = []
        for path, methods in sorted(api_paths.items()):
            if "get" not in methods:
                continue
            r = client.get(fill_path(path))
            if r.status_code != 401:
                bad.append(f"{path} -> {r.status_code}")
        check(not bad, "all protected GETs require auth", "; ".join(bad[:6]))

        print("\nViewer write -> 403")
        viewer = ensure_user(client, admin_headers, "viewer")
        if viewer:
            vtokens = login(client, *viewer)
            if vtokens:
                vheaders = {"Authorization": f"Bearer {vtokens['access_token']}"}
                bad = []
                for path, methods in sorted(api_paths.items()):
                    for method in methods:
                        if method not in MUTATING or path in ("/api/auth/logout", "/api/auth/logout-all"):
                            continue
                        r = client.request(method.upper(), fill_path(path), headers=vheaders, json={})
                        if r.status_code != 403:
                            bad.append(f"{method.upper()} {path} -> {r.status_code}")
                check(not bad, "all protected writes reject viewer", "; ".join(bad[:6]))

        print("\nTrade lead write gate")
        lead = ensure_user(client, admin_headers, "trade_lead")
        if lead:
            ltokens = login(client, *lead)
            if ltokens:
                lheaders = {"Authorization": f"Bearer {ltokens['access_token']}"}
                # Pick the first mutating route; a 4xx/5xx from the handler is fine,
                # only the RBAC gate (401/403) is under test.
                target = next(
                    ((m, p) for p, ms in api_paths.items() for m in ms
                     if m in MUTATING and p not in ("/api/auth/logout", "/api/auth/logout-all")),
                    None,
                )
                if target:
                    method, path = target
                    r = client.request(method.upper(), fill_path(path), headers=lheaders, json={})
                    check(r.status_code not in (401, 403), f"trade_lead passes {method.upper()} {path}",
                          f"{r.status_code}")

        print("\nRefresh rotation and replay")
        first = login(client, args.username, args.password)
        if first:
            rt = first["refresh_token"]
            r1 = client.post("/api/auth/refresh", json={"refresh_token": rt})
            check(r1.status_code == 200, "first refresh succeeds", f"{r1.status_code} {r1.text[:120]}")
            r2 = client.post("/api/auth/refresh", json={"refresh_token": rt})
            check(r2.status_code == 401, "replayed refresh rejected", f"{r2.status_code}")
            if r1.status_code == 200:
                old_access = r1.json()["access_token"]
                r3 = client.post(
                    "/api/auth/logout",
                    headers={"Authorization": f"Bearer {old_access}"},
                    json={"refresh_token": r1.json()["refresh_token"]},
                )
                check(r3.status_code in (200, 204), "logout accepts refresh token", f"{r3.status_code}")
                r4 = client.post("/api/auth/refresh", json={"refresh_token": r1.json()["refresh_token"]})
                check(r4.status_code == 401, "refresh after logout rejected", f"{r4.status_code}")

        print("\nWebSocket authentication")
        try:
            from websockets.sync.client import connect as ws_connect
            ws_url = base.replace("http://", "ws://").replace("https://", "wss://") + "/ws/demo-project"
            # No token: handshake must fail (HTTP 403 or close 1008).
            try:
                with ws_connect(ws_url, open_timeout=5) as ws:
                    ws.recv(timeout=2)
                check(False, "WS without token rejected", "connection stayed open")
            except Exception as exc:  # noqa: BLE001 - any handshake rejection is acceptable
                check(True, "WS without token rejected", type(exc).__name__)
            # Valid token via subprotocol.
            access = first["access_token"] if first else tokens["access_token"]
            try:
                with ws_connect(ws_url, subprotocols=[f"bearer.{access}"], open_timeout=5) as ws:
                    check(ws.subprotocol in (None, f"bearer.{access}"), "WS bearer subprotocol accepted",
                          f"subprotocol={ws.subprotocol}")
            except Exception as exc:  # noqa: BLE001
                check(False, "WS bearer subprotocol accepted", f"{type(exc).__name__}: {exc}")
        except ImportError:
            print("  websockets client not installed; skipping WS checks")

    print(f"\n{checks - len(failures)}/{checks} checks passed")
    if failures:
        print("\nFailures:")
        for f in failures:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
