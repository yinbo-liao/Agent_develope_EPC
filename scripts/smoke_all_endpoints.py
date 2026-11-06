#!/usr/bin/env python
"""Exercise every operation exposed by the dev server (dev_main.py).

The sweep enumerates the live OpenAPI document, so it covers exactly what the
running application exposes. Reads are derived from the spec; writes are
explicit cases with realistic payloads, followed by cleanup of every row the
sweep created.

Usage:
    python scripts/smoke_all_endpoints.py
    python scripts/smoke_all_endpoints.py --base-url http://127.0.0.1:8080
    python scripts/smoke_all_endpoints.py --json-out %TEMP%\\fpso_smoke.json

Exit code: 0 when there are no FAIL results, 1 otherwise.

Requires a running dev_main server. `httpx` is used from the project venv.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import traceback
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

PROJECT_ID = "demo-project"
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


class Case:
    def __init__(
        self,
        name: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        content: bytes | str | None = None,
        content_type: str | None = None,
        token: str | None = None,
        expect: set[int] | None = None,
        skip: str | None = None,
        note: str = "",
    ):
        self.name = name
        self.method = method.upper()
        self.path = path
        self.params = params or {}
        self.json_body = json_body
        self.content = content
        self.content_type = content_type
        self.token = token
        self.expect = expect
        self.skip = skip
        self.note = note


class Result:
    def __init__(self, case: Case, status: str, code: int | None, ms: float,
                 detail: str = "", data: Any = None):
        self.case = case
        self.status = status
        self.code = code
        self.ms = ms
        self.detail = detail
        self.data = data


def load_openapi(client: httpx.Client) -> dict:
    response = client.get("/openapi.json")
    response.raise_for_status()
    return response.json()


def substitute(template: str, ctx: dict[str, str]) -> str | None:
    out = template
    for key, value in ctx.items():
        out = out.replace("{" + key + "}", value)
    return None if "{" in out else out


def template_to_regex(template: str) -> re.Pattern:
    parts = re.split(r"\{[^}]+\}", template)
    return re.compile("^" + "[^/]+".join(re.escape(part) for part in parts) + "$")


def required_query_defaults(today: date, monday: date) -> dict[str, str]:
    return {
        "week_start": monday.isoformat(),
        "focus_date": today.isoformat(),
        "week_end": today.isoformat(),
        "report_date": today.isoformat(),
        "entity_type": "drawing",
        "entity_id": "drw-1",
        "actual_completion_percent": "50",
        "percent": "50",
        "quantity_received": "1",
        "status": "APPROVED",
    }


class Sweep:
    def __init__(self, base_url: str, db_path: Path | None, admin_user: str,
                 admin_pass: str):
        self.base_url = base_url.rstrip("/")
        self.db_path = db_path
        self.admin_user = admin_user
        self.admin_pass = admin_pass
        self.client = httpx.Client(base_url=self.base_url, timeout=30.0)
        self.openapi: dict = {}
        self.results: list[Result] = []
        self.ctx: dict[str, str] = {"project_id": PROJECT_ID}
        self.run_id = str(int(time.time()))
        self.admin_token = ""
        self.lead_token = ""
        self.viewer_token = ""
        self.lead_refresh = ""
        self.viewer_refresh = ""
        self.today = date.today()
        self.monday = self.today - timedelta(days=self.today.weekday())

    # -- transport ---------------------------------------------------------

    def request(self, case: Case) -> Result:
        if case.skip:
            return Result(case, SKIP, None, 0.0, case.skip)

        headers = {}
        token = case.token if case.token is not None else self.admin_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if case.content_type:
            headers["Content-Type"] = case.content_type
        started = time.perf_counter()
        try:
            response = self.client.request(
                case.method,
                case.path,
                params=case.params,
                json=case.json_body,
                content=case.content,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            return Result(case, FAIL, None, (time.perf_counter() - started) * 1000,
                          f"transport error: {exc}")
        elapsed = (time.perf_counter() - started) * 1000
        return self.judge(case, response, elapsed)

    def judge(self, case: Case, response: httpx.Response, elapsed: float) -> Result:
        code = response.status_code
        data = None
        if code != 204 and response.content and "json" in response.headers.get(
                "content-type", ""):
            try:
                data = response.json()
            except ValueError:
                return Result(case, FAIL, code, elapsed, "invalid JSON body")
        if code >= 500:
            return Result(case, FAIL, code, elapsed, f"5xx: {response.text[:400]}", data)
        expected = case.expect or set(range(200, 300))
        if code not in expected:
            return Result(case, FAIL, code, elapsed,
                          f"expected {sorted(expected)}: {response.text[:400]}", data)
        detail = f"expected {code}" if code in (401, 403, 404, 409, 422) else ""
        return Result(case, PASS, code, elapsed, detail, data)

    def record(self, case: Case, status: str, code: int | None = None,
               detail: str = "", data: Any = None) -> Result:
        result = Result(case, status, code, 0.0, detail, data)
        self.results.append(result)
        return result

    def add(self, case: Case) -> Result:
        result = self.request(case)
        self.results.append(result)
        return result

    def assert_result(self, name: str, result: Result, predicate,
                      description: str = "") -> Result:
        """Assert on a previously executed request's parsed JSON body."""
        ok = result.status == PASS and predicate(result.data)
        return self.record(
            Case(name, result.case.method, result.case.path),
            PASS if ok else FAIL, result.code,
            "" if ok else description, result.data,
        )

    def check(self, name: str, path: str, predicate, *, params: dict | None = None,
              description: str = "") -> Result:
        """Read-after-write assertion against a JSON GET response."""
        case = Case(name, "GET", path, params=params, expect={200})
        try:
            response = self.client.get(
                path, params=params,
                headers={"Authorization": f"Bearer {self.admin_token}"},
            )
        except httpx.HTTPError as exc:
            return self.record(case, FAIL, None, f"transport error: {exc}")
        if response.status_code != 200:
            return self.record(case, FAIL, response.status_code,
                               f"expected 200: {response.text[:300]}")
        try:
            data = response.json()
        except ValueError:
            return self.record(case, FAIL, response.status_code, "invalid JSON body")
        try:
            ok = bool(predicate(data))
        except Exception as exc:
            return self.record(case, FAIL, response.status_code,
                               f"assertion raised: {exc}")
        detail = "" if ok else f"not persisted{': ' + description if description else ''}"
        return self.record(case, PASS if ok else FAIL, response.status_code, detail,
                           data)

    # -- fixtures ----------------------------------------------------------

    def db_query(self, sql: str, params: tuple = ()) -> list[tuple]:
        if not self.db_path or not self.db_path.exists():
            return []
        try:
            uri = f"file:{self.db_path.as_posix()}?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=2.0) as conn:
                return list(conn.execute(sql, params))
        except sqlite3.Error:
            return []

    def login(self, username: str, password: str) -> dict:
        response = self.client.post("/api/auth/login",
                                    json={"username": username, "password": password})
        response.raise_for_status()
        return response.json()

    def register(self, username: str, role: str) -> None:
        response = self.client.post(
            "/api/auth/register",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={
                "username": username,
                "email": f"{username}@smoke.local",
                "password": "smoke-pass-1234",
                "full_name": f"Smoke {role}",
                "role": role,
            },
        )
        response.raise_for_status()

    # -- execution ---------------------------------------------------------

    def run(self) -> int:
        try:
            self.openapi = load_openapi(self.client)
        except Exception as exc:
            print(f"FATAL: cannot load /openapi.json from {self.base_url}: {exc}")
            return 1

        print(f"OpenAPI: {len(self.openapi.get('paths', {}))} paths from {self.base_url}")

        try:
            self.setup_auth()
        except Exception as exc:
            print(f"FATAL: authentication setup failed: {exc}")
            traceback.print_exc()
            return 1

        self.health_and_metrics()
        self.read_cases()
        self.write_cases()

        gaps = self.coverage_gaps()
        self.report(gaps)
        failed = [r for r in self.results if r.status == FAIL]
        return 1 if failed else 0

    def setup_auth(self) -> None:
        admin = self.login(self.admin_user, self.admin_pass)
        self.admin_token = admin["access_token"]
        self.viewer_name = f"smoke-viewer-{self.run_id}"
        self.lead_name = f"smoke-lead-{self.run_id}"

        self.add(Case("admin login returns token pair", "POST", "/api/auth/login",
                      json_body={"username": self.admin_user, "password": self.admin_pass},
                      token="", expect={200}))
        self.add(Case("bad password rejected", "POST", "/api/auth/login",
                      json_body={"username": self.admin_user, "password": "wrong-password"},
                      token="", expect={401}))
        self.add(Case("login validates missing fields", "POST", "/api/auth/login",
                      json_body={}, token="", expect={422}))

        self.register(self.lead_name, "trade_lead")
        self.register(self.viewer_name, "viewer")
        self.add(Case("register rejects duplicate username", "POST", "/api/auth/register",
                      json_body={"username": self.lead_name,
                                 "email": f"{self.lead_name}2@x.local",
                                 "password": "smoke-pass-1234", "role": "viewer"},
                      expect={409}))

        lead = self.login(self.lead_name, "smoke-pass-1234")
        viewer = self.login(self.viewer_name, "smoke-pass-1234")
        self.lead_token = lead["access_token"]
        self.lead_refresh = lead["refresh_token"]
        self.viewer_token = viewer["access_token"]
        self.viewer_refresh = viewer["refresh_token"]

        self.add(Case("viewer cannot register users", "POST", "/api/auth/register",
                      json_body={"username": f"x-{self.run_id}", "email": "x@x.local",
                                 "password": "smoke-pass-1234", "role": "viewer"},
                      token=self.viewer_token, expect={403}))
        self.add(Case("viewer write rejected with 403", "POST",
                      f"/api/engineering/drawings/{PROJECT_ID}",
                      json_body={"drawing_number": f"DENIED-{self.run_id}",
                                 "discipline_id": 1},
                      token=self.viewer_token, expect={403}))
        self.add(Case("unauthenticated read rejected with 401", "GET",
                      f"/api/engineering/summary/{PROJECT_ID}", token="", expect={401}))

        self.add(Case("trade_lead write allowed", "POST",
                      f"/api/engineering/drawings/{PROJECT_ID}",
                      json_body={"drawing_number": f"SMOKE-LEAD-{self.run_id}",
                                 "discipline_id": 1,
                                 "drawing_title": "Smoke trade-lead drawing"},
                      token=self.lead_token, expect={200}))

        # Refresh rotation (viewer): first refresh succeeds, replay is rejected,
        # logout revokes the rotated token, a further refresh is rejected.
        case = Case("refresh rotates token pair", "POST", "/api/auth/refresh",
                    json_body={"refresh_token": self.viewer_refresh}, token="",
                    expect={200})
        rotated = self.request(case)
        self.results.append(rotated)
        if rotated.status == PASS and isinstance(rotated.data, dict):
            new_refresh = rotated.data.get("refresh_token")
            self.add(Case("replayed refresh token rejected", "POST", "/api/auth/refresh",
                          json_body={"refresh_token": self.viewer_refresh}, token="",
                          expect={401}))
            self.add(Case("logout revokes refresh token", "POST", "/api/auth/logout",
                          json_body={"refresh_token": new_refresh}, token="",
                          expect={204}))
            self.add(Case("refresh after logout rejected", "POST", "/api/auth/refresh",
                          json_body={"refresh_token": new_refresh}, token="",
                          expect={401}))
        else:
            for name in ("replayed refresh token rejected",
                         "logout revokes refresh token",
                         "refresh after logout rejected"):
                self.add(Case(name, "POST", "/api/auth/refresh",
                              skip="refresh rotation failed"))

        self.add(Case("logout-all revokes sessions", "POST", "/api/auth/logout-all",
                      json_body={}, token=self.lead_token, expect={204}))

    def health_and_metrics(self) -> None:
        self.add(Case("health", "GET", "/health", token="", expect={200}))
        self.add(Case("metrics", "GET", "/metrics", token="", expect={200, 404}))

    def read_cases(self) -> None:
        query_defaults = required_query_defaults(self.today, self.monday)
        self.ctx.update({
            "drawing_id": "drw-1",
            "material_id": "mat-1",
            "ndt_id": "ndt-1",
            "focus_id": "focus-1",
            "task_id": "wpt-1",
            "equipment_id": "eq-1",
            "gate_id": "SG-1",
            "system_code": "SYS-M01",
            "procedure_id": "proc-1",
            "purchase_item_id": "pi-1",
        })
        for path in sorted(self.openapi.get("paths", {})):
            operations = self.openapi["paths"][path]
            if "get" not in operations:
                continue
            op = operations["get"]
            resolved = substitute(path, self.ctx)
            if resolved is None:
                self.add(Case(f"GET {path}", "GET", path,
                              skip="no fixture for path parameter"))
                continue
            params: dict[str, str] = {}
            missing: list[str] = []
            for parameter in op.get("parameters", []):
                if parameter.get("in") != "query" or not parameter.get("required"):
                    continue
                name = parameter["name"]
                if name in query_defaults:
                    params[name] = query_defaults[name]
                else:
                    missing.append(name)
            if missing:
                self.add(Case(f"GET {path}", "GET", resolved,
                              skip=f"no fixture for query {missing}"))
                continue
            token = "" if path == "/health" else None
            self.add(Case(f"GET {resolved}", "GET", resolved, params=params,
                          token=token, expect={200}))

    def write_cases(self) -> None:
        rid = self.run_id
        drawing_number = f"SMOKE-CSV-{rid}"
        material_mark = f"SMOKE-PM-{rid}"
        equipment_tag = f"SMOKE-TAG-{rid}"
        po_number = f"SMOKE-PO-{rid}"

        # -- engineering ---------------------------------------------------
        drawing_id = None
        created = self.add(Case("create drawing", "POST",
                                f"/api/engineering/drawings/{PROJECT_ID}",
                                json_body={"drawing_number": f"SMOKE-DWG-{rid}",
                                           "discipline_id": 1,
                                           "drawing_title": "Smoke drawing",
                                           "drawing_type": "GA",
                                           "revision": "A",
                                           "weight_kg": 10.0},
                                expect={200}))
        if isinstance(created.data, dict):
            drawing_id = created.data.get("drawing_id")
        self.assert_result("drawing create returns id", created,
                           lambda d: isinstance(d, dict) and d.get("drawing_id"),
                           "missing drawing_id")
        self.check("created drawing persisted", f"/api/engineering/drawings/{PROJECT_ID}",
                   lambda rows: any(r.get("drawing_number") == f"SMOKE-DWG-{rid}"
                                    for r in rows))

        # Material records: create + PO status control (engineering team only).
        material_id = None
        if drawing_id:
            material = self.add(Case("create material record", "POST",
                                     f"/api/engineering/materials/{PROJECT_ID}",
                                     json_body={"drawing_id": drawing_id,
                                                "material_type": "Pipe",
                                                "material_category": "PIPE",
                                                "piece_mark": f"SMOKE-MAT-{rid}",
                                                "material_length": 6,
                                                "material_weight": 12.5,
                                                "po_status": "Info-AFI"},
                                     expect={200}))
            self.assert_result("material record returns id", material,
                               lambda d: isinstance(d, dict) and d.get("material_id"),
                               "missing material_id")
            if isinstance(material.data, dict):
                material_id = material.data.get("material_id")

            self.check("created material persisted",
                       f"/api/engineering/materials/{PROJECT_ID}",
                       lambda d: any(item.get("piece_mark") == f"SMOKE-MAT-{rid}"
                                     and item.get("total_weight") == 75.0
                                     for item in d.get("items", [])),
                       description="material row missing or total_weight != 75.0")

            self.add(Case("viewer cannot create material", "POST",
                          f"/api/engineering/materials/{PROJECT_ID}",
                          json_body={"drawing_id": drawing_id,
                                     "material_type": "Pipe"},
                          token=self.viewer_token, expect={403}))
            self.add(Case("material create rejects unknown drawing", "POST",
                          f"/api/engineering/materials/{PROJECT_ID}",
                          json_body={"drawing_id": "smoke-missing",
                                     "material_type": "Pipe"},
                          expect={404}))
        else:
            for name in ("create material record", "viewer cannot create material"):
                self.add(Case(name, "POST",
                              f"/api/engineering/materials/{PROJECT_ID}",
                              skip="drawing create failed"))

        if material_id:
            self.add(Case("update material PO status", "PATCH",
                          f"/api/engineering/materials/{PROJECT_ID}/{material_id}/status",
                          json_body={"po_status": "PO-issued"}, expect={200}))
            self.check("material status persisted",
                       f"/api/engineering/materials/{PROJECT_ID}",
                       lambda d: any(item.get("material_id") == material_id
                                     and item.get("po_status") == "PO-issued"
                                     for item in d.get("items", [])),
                       description="po_status != PO-issued")
            self.add(Case("material status rejects unknown value", "PATCH",
                          f"/api/engineering/materials/{PROJECT_ID}/{material_id}/status",
                          json_body={"po_status": "NOT-A-STATUS"}, expect={400}))
            self.add(Case("material status rejects unknown material", "PATCH",
                          f"/api/engineering/materials/{PROJECT_ID}/smoke-missing/status",
                          json_body={"po_status": "PR-Raised"}, expect={404}))
            self.add(Case("viewer cannot update material status", "PATCH",
                          f"/api/engineering/materials/{PROJECT_ID}/{material_id}/status",
                          json_body={"po_status": "PR-Raised"},
                          token=self.viewer_token, expect={403}))
        else:
            for name in ("update material PO status", "material status persisted",
                         "material status rejects unknown value",
                         "material status rejects unknown material",
                         "viewer cannot update material status"):
                self.add(Case(name, "PATCH",
                              f"/api/engineering/materials/{PROJECT_ID}/smoke-missing/status",
                              skip="material create failed"))

        self.add(Case("create mto item", "POST", f"/api/engineering/mto/{PROJECT_ID}",
                      json_body={"discipline_id": 1,
                                 "material_type": f"SMOKE-MTO-{rid}",
                                 "material_spec": "ASTM A36", "quantity": 10,
                                 "unit": "m", "unit_weight_kg": 2.5},
                      expect={200}))
        stored = self.db_query(
            "SELECT COUNT(*) FROM material_takeoff WHERE material_type = ?",
            (f"SMOKE-MTO-{rid}",),
        )
        ok = bool(stored) and stored[0][0] == 1
        self.record(Case("mto item persisted", "POST",
                         f"/api/engineering/mto/{PROJECT_ID}"),
                    PASS if ok else FAIL, None,
                    "" if ok else "mto row not found in dev.db")

        csv_drawings = ("Drawing No,Discipline,Drawing Title,Rev,Issued for Info,"
                        "Issued Date,Issued for Construction,Issued Date\n"
                        f"{drawing_number},STRUCTURAL,Smoke imported drawing,A,Yes,"
                        f"{self.today.isoformat()},No,\n")
        imported = self.add(Case("import drawings CSV", "POST",
                                 f"/api/engineering/import-drawings/{PROJECT_ID}",
                                 content=csv_drawings, content_type="text/csv",
                                 expect={200}))
        self.assert_result("drawings CSV imported", imported,
                           lambda d: isinstance(d, dict) and d.get("imported") == 1,
                           "imported != 1")

        csv_materials = ("Drawing No,Rev,Piece Mark,Material Grade,Thickness,Material Type,"
                         "Size,OD,Material Cat,Unit Wt,Length,Total Wt\n"
                         f"{drawing_number},A,{material_mark},ASTM A36,10mm,Steel Plate,"
                         "2000x8000mm,,STEEL,100,2,200\n")
        imported = self.add(Case("import materials CSV", "POST",
                                 f"/api/engineering/import-materials/{PROJECT_ID}",
                                 content=csv_materials, content_type="text/csv",
                                 expect={200}))
        self.assert_result("materials CSV imported", imported,
                           lambda d: isinstance(d, dict) and d.get("imported") == 1,
                           "imported != 1")

        csv_equipment = ("Drawing No,Rev,Equipment Tag,Equipment Name,Equipment Detail,"
                         "Install Location,Weight,Equipment Type,Certification,FAT Status,"
                         "Test Status,System Code,System Name,Delivery Date,Install Date,"
                         "Remark\n"
                         f"{drawing_number},A,{equipment_tag},Smoke Equipment,Detail,Deck A,"
                         "100,TEST,Cert,PENDING,None,SYS-X,Smoke System,,,\n")
        imported = self.add(Case("import equipment CSV", "POST",
                                 f"/api/engineering/import-equipment/{PROJECT_ID}",
                                 content=csv_equipment, content_type="text/csv",
                                 expect={200}))
        self.assert_result("equipment CSV imported", imported,
                           lambda d: isinstance(d, dict) and d.get("imported") == 1,
                           "imported != 1")

        # Delete the imported material first: deleting the drawing cascades to
        # its materials, so the lookup must happen while both rows still exist.
        rows = self.db_query(
            "SELECT material_id FROM drawing_materials WHERE piece_mark = ?",
            (material_mark,),
        )
        imported_material = rows[0][0] if rows else None
        if imported_material:
            self.add(Case("delete imported material", "DELETE",
                          f"/api/engineering/materials/{PROJECT_ID}/{imported_material}",
                          expect={200}))
            self.check("imported material deleted",
                       f"/api/engineering/materials/{PROJECT_ID}",
                       lambda d: all(item.get("material_id") != imported_material
                                     for item in d.get("items", [])))
        else:
            self.add(Case("delete imported material", "DELETE",
                          f"/api/engineering/materials/{PROJECT_ID}/smoke-missing",
                          skip="imported material not found in dev.db"))

        rows = self.db_query(
            "SELECT drawing_id FROM drawings WHERE drawing_number = ? AND project_id = ?",
            (drawing_number, PROJECT_ID),
        )
        imported_drawing = rows[0][0] if rows else None
        if imported_drawing:
            self.add(Case("delete imported drawing", "DELETE",
                          f"/api/engineering/drawings/{PROJECT_ID}/{imported_drawing}",
                          expect={200}))
        else:
            self.add(Case("delete imported drawing", "DELETE",
                          f"/api/engineering/drawings/{PROJECT_ID}/smoke-missing",
                          skip="imported drawing not found in dev.db"))

        # -- procurement ---------------------------------------------------
        po = self.add(Case("create purchase order", "POST",
                           f"/api/procurement/purchase-order/{PROJECT_ID}",
                           json_body={"po_number": po_number, "vendor_name": "Smoke Vendor",
                                      "order_date": self.today.isoformat(),
                                      "expected_delivery_date":
                                          (self.today + timedelta(days=30)).isoformat(),
                                      "items": [
                                          {"material_type": "PIPE_6inch_SCH40",
                                           "material_spec": "API 5L X52",
                                           "quantity_ordered": 10, "unit": "m",
                                           "unit_price": 50.0},
                                          {"material_type": "Steel Plate",
                                           "material_spec": None,
                                           "quantity_ordered": 5, "unit": "pcs"}]},
                           expect={200}))
        self.assert_result("purchase order returns id", po,
                           lambda d: isinstance(d, dict) and d.get("po_id"),
                           "missing po_id")
        self.check("purchase order persisted",
                   f"/api/procurement/purchase-orders/{PROJECT_ID}",
                   lambda rows: any(r.get("po_number") == po_number for r in rows))

        rows = self.db_query(
            "SELECT purchase_item_id FROM purchase_items WHERE po_id IN "
            "(SELECT po_id FROM procurement_purchase_orders WHERE po_number = ?) "
            "LIMIT 1",
            (po_number,),
        )
        purchase_item = rows[0][0] if rows else None
        if purchase_item:
            self.add(Case("record material receipt", "PATCH",
                          f"/api/procurement/material-receipt/{purchase_item}",
                          params={"quantity_received": "5"}, expect={200}))
            stored = self.db_query(
                "SELECT quantity_received FROM purchase_items WHERE purchase_item_id = ?",
                (purchase_item,),
            )
            ok = bool(stored) and stored[0][0] == 5
            self.record(Case("material receipt persisted", "PATCH",
                             f"/api/procurement/material-receipt/{purchase_item}"),
                        PASS if ok else FAIL, None,
                        "" if ok else "quantity_received != 5")
        else:
            self.add(Case("record material receipt", "PATCH",
                          "/api/procurement/material-receipt/smoke-missing",
                          skip="purchase item not found in dev.db"))
            self.add(Case("material receipt persisted", "PATCH",
                          "/api/procurement/material-receipt/smoke-missing",
                          skip="purchase item not found in dev.db"))

        # -- construction --------------------------------------------------
        self.add(Case("record daily manpower", "POST",
                      "/api/construction/daily-manpower",
                      json_body={"project_id": PROJECT_ID,
                                 "report_date": self.today.isoformat(),
                                 "discipline": "SMOKE", "planned_headcount": 10,
                                 "actual_headcount": 8, "overtime_hours": 1.5},
                      expect={200}))
        self.check("daily manpower persisted",
                   f"/api/construction/daily-manpower/{PROJECT_ID}",
                   lambda rows: any(r.get("discipline") == "SMOKE" for r in rows),
                   params={"report_date": self.today.isoformat()})
        self.add(Case("create resource shortage", "POST",
                      "/api/construction/resource-shortages",
                      json_body={"project_id": PROJECT_ID, "shortage_type": "MATERIAL",
                                 "resource_name": f"SMOKE-RES-{rid}",
                                 "required_quantity": 10, "available_quantity": 4,
                                 "shortfall": 6,
                                 "expected_resolution_date": self.today.isoformat(),
                                 "impact_description": "smoke"},
                      expect={200}))
        self.check("resource shortage persisted",
                   f"/api/construction/resource-shortages/{PROJECT_ID}",
                   lambda rows: any(r.get("resource_name") == f"SMOKE-RES-{rid}"
                                    for r in rows))
        self.add(Case("create weekly planning task", "POST",
                      "/api/construction/weekly-planning",
                      json_body={"project_id": PROJECT_ID,
                                 "week_start": self.monday.isoformat(),
                                 "activity_id": "act-1",
                                 "planned_status": "Smoke plan",
                                 "planned_completion_percent": 60,
                                 "accountability_party": "Smoke"},
                      expect={200}))
        self.check("weekly planning task persisted",
                   f"/api/construction/weekly-planning/{PROJECT_ID}",
                   lambda rows: any(r.get("planned_status") == "Smoke plan"
                                    for r in rows),
                   params={"week_start": self.monday.isoformat()})
        self.add(Case("update weekly planning task", "PATCH",
                      "/api/construction/weekly-planning/wpt-1",
                      params={"actual_completion_percent": "90", "is_completed": "true"},
                      expect={200}))
        self.check("weekly planning update persisted",
                   f"/api/construction/weekly-planning/{PROJECT_ID}",
                   lambda rows: any(r.get("task_id") == "wpt-1"
                                    and r.get("actual_completion_percent") == 90
                                    for r in rows),
                   params={"week_start": self.monday.isoformat()})
        mvr = self.add(Case("update mvr status", "PATCH",
                            "/api/construction/mvr-status/mat-1",
                            json_body={"mvr_status": "Structure-requested",
                                       "confirmed_by": "smoke"},
                            expect={200}))
        self.assert_result("mvr update accepted", mvr,
                           lambda d: isinstance(d, dict) and d.get("status") == "updated",
                           "mvr status not updated")
        self.check("mvr status persisted",
                   f"/api/construction/materials/{PROJECT_ID}",
                   lambda d: any(item.get("material_id") == "mat-1"
                                 and item.get("mvr_status") == "Structure-requested"
                                 for item in d.get("materials", [])))

        # -- inspection ----------------------------------------------------
        self.add(Case("create ndt request", "POST", "/api/inspection/ndt-request",
                      json_body={"project_id": PROJECT_ID, "activity_id": "act-1",
                                 "ndt_method": "RT", "weld_joint_id": f"SMOKE-W-{rid}",
                                 "requested_date": self.today.isoformat(),
                                 "acceptance_criteria": "ASME IX",
                                 "technician_name": "Smoke Tech"},
                      expect={200}))
        self.check("ndt request persisted",
                   f"/api/inspection/ndt-requests/{PROJECT_ID}",
                   lambda rows: any(r.get("weld_joint_id") == f"SMOKE-W-{rid}"
                                    for r in rows))
        self.add(Case("update ndt progress", "PATCH",
                      "/api/inspection/ndt-progress/ndt-1",
                      params={"percent": "50", "result": "PASS"}, expect={200}))
        self.check("ndt progress persisted",
                   f"/api/inspection/ndt-requests/{PROJECT_ID}",
                   lambda rows: any(r.get("ndt_id") == "ndt-1"
                                    and r.get("percent_complete") == 50
                                    for r in rows))
        self.add(Case("upsert ndt daily log", "POST", "/api/inspection/ndt-daily-log",
                      json_body={"project_id": PROJECT_ID,
                                 "log_date": self.today.isoformat(),
                                 "discipline_name": "SMOKE", "ndt_method": "RT",
                                 "rfi_total_length_mm": 1000,
                                 "ndt_complete_length_mm": 500,
                                 "daily_length_done_mm": 100, "team_deployed": 2,
                                 "previous_status": "On track",
                                 "remarks": "smoke", "updated_by": "smoke"},
                      expect={200}))
        self.check("ndt daily log persisted",
                   f"/api/inspection/ndt-daily-log/{PROJECT_ID}",
                   lambda rows: any(r.get("discipline_name") == "SMOKE" for r in rows),
                   params={"log_date": self.today.isoformat()})
        focus_point = f"SMOKE-FOCUS-{rid}"
        self.add(Case("create daily focus", "POST", "/api/inspection/daily-focus",
                      json_body={"project_id": PROJECT_ID,
                                 "focus_date": self.today.isoformat(),
                                 "discipline": "SMOKE", "focus_point": focus_point,
                                 "priority": "HIGH"},
                      expect={200}))
        self.check("daily focus persisted",
                   f"/api/inspection/daily-focus/{PROJECT_ID}",
                   lambda rows: any(r.get("focus_point") == focus_point for r in rows),
                   params={"focus_date": self.today.isoformat()})
        rows = self.db_query(
            "SELECT focus_id FROM daily_inspection_focus WHERE focus_point = ?",
            (focus_point,),
        )
        if rows:
            self.add(Case("complete daily focus", "PATCH",
                          f"/api/inspection/daily-focus/{rows[0][0]}",
                          params={"achievement_notes": "smoke"}, expect={200}))
        else:
            self.add(Case("complete daily focus", "PATCH",
                          "/api/inspection/daily-focus/smoke-missing",
                          skip="focus row not found in dev.db"))

        # -- equipment -----------------------------------------------------
        self.add(Case("create equipment", "POST", f"/api/equipment/{PROJECT_ID}",
                      json_body={"category_id": 1, "tag_number": equipment_tag,
                                 "equipment_name": "Smoke Equipment",
                                 "manufacturer": "Smoke", "model": "S-1",
                                 "specification_doc": "DOC-1"},
                      expect={200}))
        self.check("equipment persisted", f"/api/equipment/{PROJECT_ID}",
                   lambda d: any(item.get("tag_number") == equipment_tag
                                 for item in d.get("items", [])))
        rows = self.db_query(
            "SELECT equipment_id FROM equipment_list WHERE tag_number = ?",
            (equipment_tag,),
        )
        if rows:
            equipment_id = rows[0][0]
            self.add(Case("update equipment spec status", "PATCH",
                          f"/api/equipment/{equipment_id}/spec-status",
                          params={"status": "APPROVED"}, expect={200}))
            self.check("equipment spec status persisted",
                       f"/api/equipment/{PROJECT_ID}",
                       lambda d: any(item.get("equipment_id") == equipment_id
                                     and item.get("spec_status") == "APPROVED"
                                     for item in d.get("items", [])))
        else:
            self.add(Case("update equipment spec status", "PATCH",
                          "/api/equipment/smoke-missing/spec-status",
                          skip="equipment row not found in dev.db"))

        # -- AI / planning / stage gate -----------------------------------
        chat = self.add(Case("ai chat", "POST", f"/api/ai/chat/{PROJECT_ID}",
                             json_body={"query": "KPI summary"}, expect={200}))
        self.assert_result("ai chat returns a response", chat,
                           lambda d: isinstance(d, dict) and d.get("response"),
                           "empty response")

        analyses = {
            "schedule risk": ("schedule_risk", {"analysis_type": "schedule_risk"},
                              lambda d: isinstance(d, dict) and "risk_level" in d,
                              "missing risk_level"),
            "conflict detection": ("conflict_detection",
                                   {"analysis_type": "conflict_detection"},
                                   lambda d: isinstance(d, dict)
                                   and "conflicts_found" in d,
                                   "missing conflicts_found"),
            "gate assessment": ("gate_assessment",
                                {"analysis_type": "gate_assessment",
                                 "gate_id": "SG-1"},
                                lambda d: isinstance(d, dict)
                                and ("ai_readiness_score" in d or "error" in d),
                                "missing ai_readiness_score"),
            "weekly report": ("weekly_report",
                              {"analysis_type": "weekly_report",
                               "week_end": self.today.isoformat()},
                              lambda d: isinstance(d, dict) and d.get("report"),
                              "missing report"),
        }
        for label, (_kind, body, predicate, why) in analyses.items():
            result = self.add(Case(f"ai analyze {label}", "POST",
                                   f"/api/ai/analyze/{PROJECT_ID}",
                                   json_body=body, expect={200}))
            self.assert_result(f"ai analyze {label} shape", result, predicate, why)

        self.add(Case("ai analyze rejects missing gate_id", "POST",
                      f"/api/ai/analyze/{PROJECT_ID}",
                      json_body={"analysis_type": "gate_assessment"},
                      expect={400}))
        self.add(Case("ai analyze rejects unknown type", "POST",
                      f"/api/ai/analyze/{PROJECT_ID}",
                      json_body={"analysis_type": "not_a_real_analysis"},
                      expect={400}))

        self.add(Case("generate planning periods", "POST",
                      f"/api/planning/generate/{PROJECT_ID}", expect={200}))
        assessed = self.add(Case("assess stage gate", "POST",
                                 f"/api/stagegate/assess/{PROJECT_ID}/SG-1",
                                 expect={200}))
        self.assert_result("stage gate assessment returned", assessed,
                           lambda d: isinstance(d, dict)
                           and "ai_readiness_score" in d,
                           "missing ai_readiness_score")

        # -- cleanup -------------------------------------------------------
        if drawing_id:
            self.add(Case("delete created drawing", "DELETE",
                          f"/api/engineering/drawings/{PROJECT_ID}/{drawing_id}",
                          expect={200}))
            self.check("created drawing deleted",
                       f"/api/engineering/drawings/{PROJECT_ID}",
                       lambda rows: all(r.get("drawing_number") != f"SMOKE-DWG-{rid}"
                                        for r in rows))
        rows = self.db_query(
            "SELECT drawing_id FROM drawings WHERE drawing_number = ? AND project_id = ?",
            (f"SMOKE-LEAD-{rid}", PROJECT_ID),
        )
        if rows:
            self.add(Case("delete trade_lead drawing", "DELETE",
                          f"/api/engineering/drawings/{PROJECT_ID}/{rows[0][0]}",
                          expect={200}))
        else:
            self.add(Case("delete trade_lead drawing", "DELETE",
                          f"/api/engineering/drawings/{PROJECT_ID}/smoke-missing",
                          skip="trade-lead drawing not found in dev.db"))

    # -- coverage ----------------------------------------------------------

    def coverage_gaps(self) -> list[str]:
        patterns = {
            template: template_to_regex(template)
            for template in self.openapi.get("paths", {})
        }
        covered: set[tuple[str, str]] = set()
        for result in self.results:
            if result.status == SKIP:
                continue
            for template, pattern in patterns.items():
                methods = {m.upper() for m in self.openapi["paths"][template]
                           if m.lower() in {"get", "post", "put", "patch", "delete"}}
                if result.case.method in methods and pattern.match(result.case.path):
                    covered.add((result.case.method, template))
                    break
        gaps = []
        for path, operations in self.openapi.get("paths", {}).items():
            for method in operations:
                method = method.upper()
                if method in {"GET", "POST", "PUT", "PATCH", "DELETE"} \
                        and (method, path) not in covered:
                    gaps.append(f"{method} {path}")
        return gaps

    def report(self, gaps: list[str]) -> None:
        width = max((len(r.case.name) for r in self.results), default=10)
        print()
        for result in self.results:
            code = "-" if result.code is None else str(result.code)
            line = (f"{result.status:4} {code:>3} {result.ms:7.1f}ms  "
                    f"{result.case.name:<{width}}")
            if result.detail:
                line += f"  [{result.detail}]"
            print(line)
        counts = {status: sum(1 for r in self.results if r.status == status)
                  for status in (PASS, FAIL, SKIP)}
        print()
        print(f"TOTAL {len(self.results)} | PASS {counts[PASS]} | "
              f"FAIL {counts[FAIL]} | SKIP {counts[SKIP]}")
        for gap in gaps:
            print(f"COVERAGE GAP: {gap}")
        if gaps:
            print(f"COVERAGE GAPS: {len(gaps)}")
        skipped = [r for r in self.results if r.status == SKIP]
        if skipped:
            print("SKIPS:")
            for result in skipped:
                print(f"  - {result.case.name}: {result.detail}")

    def write_report(self, path: Path) -> None:
        payload = {
            "base_url": self.base_url,
            "run_id": self.run_id,
            "counts": {status: sum(1 for r in self.results if r.status == status)
                       for status in (PASS, FAIL, SKIP)},
            "results": [
                {
                    "name": r.case.name,
                    "method": r.case.method,
                    "path": r.case.path,
                    "status": r.status,
                    "code": r.code,
                    "ms": round(r.ms, 1),
                    "detail": r.detail,
                }
                for r in self.results
            ],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Report written to {path}")


def find_db_path(explicit: str | None) -> Path | None:
    if explicit:
        path = Path(explicit)
        return path if path.exists() else None
    repo_root = Path(__file__).resolve().parent.parent
    for candidate in (repo_root / "backend" / "dev.db", Path("dev.db")):
        if candidate.exists():
            return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Full endpoint sweep for dev_main")
    parser.add_argument("--base-url", default=os.getenv("FPSO_SMOKE_BASE_URL",
                                                        "http://127.0.0.1:8080"))
    parser.add_argument("--db", default=None, help="Path to dev.db (for fixture ids)")
    parser.add_argument("--json-out", default=str(Path(os.getenv("TEMP", ".")) /
                                                  "fpso_smoke_report.json"))
    parser.add_argument("--admin-user", default=os.getenv("FPSO_DEV_ADMIN_USERNAME",
                                                          "admin"))
    parser.add_argument("--admin-password",
                        default=os.getenv("FPSO_DEV_ADMIN_PASSWORD",
                                          "dev-admin-password"))
    args = parser.parse_args()

    sweep = Sweep(args.base_url, find_db_path(args.db), args.admin_user,
                  args.admin_password)
    code = sweep.run()
    sweep.write_report(Path(args.json_out))
    return code


if __name__ == "__main__":
    sys.exit(main())
