"""Air Quality Monitor — Flet desktop UI (login, dashboard, devices, alerts, settings)."""

import asyncio
import math
import os
from pathlib import Path

import flet as ft
import requests
from requests.exceptions import ConnectionError as RequestsConnectionError

from config import API_BASE_URL, PAGE_SIZE

API_START_HINT = (
    "Start the API first:\n"
    "  cd air_quality_project\n"
    "  py -m uvicorn api:app --reload --port 8000"
)


def main(page: ft.Page):
    page.title = "Air Quality Monitor"
    page.padding = 0
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = ft.Colors.SURFACE

    session: dict = {
        "token": None,
        "role": None,
        "username": None,
        "tab": 0,
        "dashboard_refresh": True,
    }

    _active_snack: list[ft.SnackBar | None] = [None]

    def headers() -> dict:
        h = {}
        if session["token"]:
            h["Authorization"] = f"Bearer {session['token']}"
        return h

    def is_admin() -> bool:
        return session["role"] == "admin"

    def show_snack(message: str, success: bool = True) -> None:
        if _active_snack[0] is not None:
            try:
                page.overlay.remove(_active_snack[0])
            except ValueError:
                pass
        snack = ft.SnackBar(
            content=ft.Text(message, color=ft.Colors.WHITE),
            bgcolor=ft.Colors.GREEN if success else ft.Colors.RED,
            duration=2500,
            open=True,
        )
        page.overlay.append(snack)
        _active_snack[0] = snack
        page.update()

    def check_api() -> tuple[bool, str]:
        try:
            resp = requests.get(f"{API_BASE_URL}/health", timeout=3)
            resp.raise_for_status()
            return True, ""
        except RequestsConnectionError:
            return False, f"Cannot connect to {API_BASE_URL}.\n\n{API_START_HINT}"
        except Exception as ex:  # noqa: BLE001
            return False, f"API error: {ex}\n\n{API_START_HINT}"

    def parse_paginated(payload) -> tuple[list, int]:
        if isinstance(payload, list):
            return payload, len(payload)
        if isinstance(payload, dict) and "items" in payload:
            return payload["items"], int(payload.get("total", len(payload["items"])))
        raise ValueError("Unexpected API response format")

    _PM25_SAFE = 12.0
    _PM25_MOD = 35.4

    def _bar_color(pm25: float) -> str:
        if pm25 <= _PM25_SAFE:
            return ft.Colors.GREEN_400
        if pm25 <= _PM25_MOD:
            return ft.Colors.AMBER_400
        return ft.Colors.RED_400

    def build_bar_chart(points: list) -> ft.Control:
        if not points:
            return ft.Text("No readings in the last 24 hours", color=ft.Colors.ON_SURFACE_VARIANT)
        subset = points[-40:]
        max_pm = max(p["pm25"] for p in subset) or 1
        bars = [
            ft.Container(
                width=10,
                height=max(4, int(80 * p["pm25"] / max_pm)),
                bgcolor=_bar_color(p["pm25"]),
                tooltip=f"PM2.5: {p['pm25']}  CO₂: {p['co2']}",
                border_radius=ft.BorderRadius.only(top_left=2, top_right=2),
            )
            for p in subset
        ]
        legend = ft.Row(
            [
                ft.Container(width=10, height=10, bgcolor=ft.Colors.GREEN_400, border_radius=2),
                ft.Text("Good", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Container(width=10, height=10, bgcolor=ft.Colors.AMBER_400, border_radius=2),
                ft.Text("Moderate", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Container(width=10, height=10, bgcolor=ft.Colors.RED_400, border_radius=2),
                ft.Text("High", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
            ],
            spacing=6,
        )
        return ft.Column(
            [
                ft.Text("PM2.5 trend — last 24 h", weight=ft.FontWeight.BOLD),
                ft.Row(
                    bars,
                    spacing=3,
                    scroll=ft.ScrollMode.AUTO,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                ),
                legend,
            ],
            spacing=8,
        )

    # ── Login ──────────────────────────────────────────────────────────
    login_user = ft.TextField(label="Username", autofocus=True)
    login_pass = ft.TextField(label="Password", password=True, can_reveal_password=True)

    def do_login(e=None) -> None:
        if not (login_user.value or "").strip():
            show_snack("Username is required", success=False)
            return
        if not (login_pass.value or "").strip():
            show_snack("Password is required", success=False)
            return
        try:
            resp = requests.post(
                f"{API_BASE_URL}/auth/login",
                json={
                    "username": login_user.value.strip(),
                    "password": login_pass.value,
                },
                timeout=5,
            )
        except RequestsConnectionError:
            show_snack("Cannot reach API — start uvicorn first", success=False)
            return
        if resp.status_code != 200:
            detail = resp.json().get("detail", resp.text) if resp.content else resp.text
            show_snack(str(detail), success=False)
            return
        data = resp.json()
        session["token"] = data["token"]
        session["role"] = data["role"]
        session["username"] = data["username"]
        show_snack(f"Welcome, {data['username']} ({data['role']})")
        show_main_shell()

    def show_login_view() -> None:
        page.controls.clear()
        page.appbar = None
        page.navigation_bar = None
        page.bottom_appbar = None
        page.add(login_view)
        page.update()

    login_view = ft.Container(
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.AIR, size=52, color=ft.Colors.BLUE_300),
                    ft.Text("Air Quality Monitor", size=26, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        "Sign in to continue",
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        size=13,
                    ),
                    ft.Container(height=24),
                    login_user,
                    ft.Container(height=16),
                    login_pass,
                    ft.Container(height=28),
                    ft.FilledButton(
                        "Sign In",
                        icon=ft.Icons.LOGIN,
                        on_click=do_login,
                        width=200,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
                width=340,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.Padding.all(48),
            border_radius=20,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            width=460,
            height=460,
            alignment=ft.Alignment.CENTER,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
    )

    # ── Dashboard ──────────────────────────────────────────────────────
    card_devices = ft.Text("—", size=28, weight=ft.FontWeight.BOLD)
    card_pm25 = ft.Text("—", size=28, weight=ft.FontWeight.BOLD)
    card_co2 = ft.Text("—", size=28, weight=ft.FontWeight.BOLD)
    card_alerts = ft.Text("—", size=28, weight=ft.FontWeight.BOLD)
    chart_area = ft.Container()
    readings_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("ID")),
            ft.DataColumn(ft.Text("Device")),
            ft.DataColumn(ft.Text("PM2.5")),
            ft.DataColumn(ft.Text("CO2")),
            ft.DataColumn(ft.Text("Time")),
        ],
        rows=[],
    )

    def load_dashboard() -> None:
        try:
            s = requests.get(
                f"{API_BASE_URL}/dashboard/summary", headers=headers(), timeout=5
            )
            s.raise_for_status()
            summary = s.json()
            card_devices.value = str(summary["active_devices"])
            card_pm25.value = str(summary["avg_pm25"])
            card_co2.value = str(summary["avg_co2"])
            card_alerts.value = str(summary["alert_count"])

            c = requests.get(
                f"{API_BASE_URL}/dashboard/chart", headers=headers(), timeout=5
            )
            c.raise_for_status()
            chart_area.content = build_bar_chart(c.json().get("points", []))

            r = requests.get(
                f"{API_BASE_URL}/readings",
                headers=headers(),
                params={"limit": 8, "offset": 0},
                timeout=5,
            )
            r.raise_for_status()
            items, _ = parse_paginated(r.json())
            readings_table.rows = [
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(x["reading_id"]))),
                        ft.DataCell(ft.Text(x["device_id"])),
                        ft.DataCell(ft.Text(str(x["pm25"]))),
                        ft.DataCell(ft.Text(str(x["co2"]))),
                        ft.DataCell(ft.Text(x["timestamp"] or "")),
                    ]
                )
                for x in items
            ]
        except Exception as ex:  # noqa: BLE001
            show_snack(f"Dashboard error: {ex}", success=False)
        page.update()

    def summary_card(title: str, value_ctrl: ft.Text, color, icon) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, size=14, color=ft.Colors.WHITE70),
                            ft.Text(title, size=12, color=ft.Colors.WHITE70),
                        ],
                        spacing=4,
                    ),
                    value_ctrl,
                ],
                spacing=6,
            ),
            padding=16,
            bgcolor=color,
            border_radius=12,
            expand=True,
        )

    dashboard_left = ft.Column(
        [
            ft.Row(
                [
                    summary_card("Active devices", card_devices, ft.Colors.BLUE_800, ft.Icons.SENSORS),
                    summary_card("Avg PM2.5", card_pm25, ft.Colors.GREEN_800, ft.Icons.AIR),
                    summary_card("Avg CO₂", card_co2, ft.Colors.ORANGE_800, ft.Icons.CLOUD),
                    summary_card("Open alerts", card_alerts, ft.Colors.RED_800, ft.Icons.WARNING_AMBER),
                ],
                spacing=10,
            ),
            ft.Container(height=12),
            chart_area,
            ft.Container(height=18),
            ft.Text("Recent readings", weight=ft.FontWeight.BOLD),
            ft.Column([readings_table], scroll=ft.ScrollMode.AUTO, expand=True),
        ],
        expand=True,
        spacing=12,
    )

    dashboard_view = dashboard_left

    async def dashboard_refresh_loop() -> None:
        while session["dashboard_refresh"] and session["token"]:
            await asyncio.sleep(5)
            if session["tab"] == 0 and session["token"]:
                load_dashboard()

    # ── Devices (paginated CRUD) ───────────────────────────────────────
    current_page = [1]
    total_pages = [1]
    search_field = ft.TextField(
        label="Search devices",
        prefix_icon=ft.Icons.SEARCH,
        expand=True,
        content_padding=ft.Padding.symmetric(horizontal=16, vertical=18),
    )
    sort_dropdown = ft.Dropdown(
        label="Sort by",
        width=150,
        value="device_id",
        options=[
            ft.dropdown.Option(key="id", text="ID"),
            ft.dropdown.Option(key="device_id", text="Device ID"),
            ft.dropdown.Option(key="model", text="Model"),
            ft.dropdown.Option(key="status", text="Status"),
            ft.dropdown.Option(key="room_name", text="Room"),
        ],
    )
    order_dropdown = ft.Dropdown(
        label="Order",
        width=130,
        value="asc",
        options=[
            ft.dropdown.Option(key="asc", text="Ascending"),
            ft.dropdown.Option(key="desc", text="Descending"),
        ],
    )
    counter_text = ft.Text("")
    pager_row = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=4)
    devices_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("ID")),
            ft.DataColumn(ft.Text("Device ID")),
            ft.DataColumn(ft.Text("Model")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Text("Room")),
            ft.DataColumn(ft.Text("Actions")),
        ],
        rows=[],
    )

    def go_to_page(n: int) -> None:
        current_page[0] = max(1, min(n, total_pages[0]))
        load_devices_table()

    def rebuild_pager() -> None:
        tp, cp = total_pages[0], current_page[0]
        controls: list[ft.Control] = [
            ft.IconButton(
                icon=ft.Icons.CHEVRON_LEFT,
                disabled=cp <= 1,
                on_click=lambda e: go_to_page(cp - 1),
            )
        ]
        for n in range(1, min(tp, 8) + 1):
            controls.append(
                ft.TextButton(
                    str(n),
                    on_click=lambda e, num=n: go_to_page(num),
                )
            )
        controls.append(
            ft.IconButton(
                icon=ft.Icons.CHEVRON_RIGHT,
                disabled=cp >= tp,
                on_click=lambda e: go_to_page(cp + 1),
            )
        )
        pager_row.controls = controls

    def load_devices_table(e=None) -> None:
        sort_by = sort_dropdown.value or "device_id"
        order = order_dropdown.value or "asc"
        offset = (current_page[0] - 1) * PAGE_SIZE
        try:
            resp = requests.get(
                f"{API_BASE_URL}/devices",
                headers=headers(),
                params={
                    "limit": PAGE_SIZE,
                    "offset": offset,
                    "search": (search_field.value or "").strip(),
                    "sort_by": sort_by,
                    "order": order,
                },
                timeout=5,
            )
            resp.raise_for_status()
            items, total = parse_paginated(resp.json())
            total_pages[0] = max(1, math.ceil(total / PAGE_SIZE))

            _status_color = {
                "online": ft.Colors.GREEN_400,
                "offline": ft.Colors.RED_400,
                "maintenance": ft.Colors.ORANGE_400,
            }
            rows = []
            for d in items:
                actions = []
                if is_admin():
                    actions = [
                        ft.IconButton(
                            icon=ft.Icons.EDIT,
                            icon_size=18,
                            on_click=make_edit(d),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE,
                            icon_color=ft.Colors.RED_400,
                            icon_size=18,
                            on_click=make_delete(d["id"]),
                        ),
                    ]
                status = d["status"]
                rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(str(d["id"]))),
                            ft.DataCell(ft.Text(d["device_id"], weight=ft.FontWeight.W_500)),
                            ft.DataCell(ft.Text(d["model"])),
                            ft.DataCell(
                                ft.Container(
                                    content=ft.Text(
                                        status,
                                        size=12,
                                        color=_status_color.get(status, ft.Colors.ON_SURFACE),
                                        weight=ft.FontWeight.W_500,
                                    ),
                                    padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                                    border_radius=20,
                                    bgcolor=ft.Colors.with_opacity(
                                        0.15, _status_color.get(status, ft.Colors.ON_SURFACE)
                                    ),
                                )
                            ),
                            ft.DataCell(
                                ft.Text(d.get("room_name") or str(d["room_id"]))
                            ),
                            ft.DataCell(ft.Row(actions, spacing=0)),
                        ]
                    )
                )
            devices_table.rows.clear()
            devices_table.rows.extend(rows)
            start = offset + 1 if total else 0
            end = min(offset + len(items), total)
            counter_text.value = f"Showing {start}–{end} of {total} devices"
            rebuild_pager()
        except Exception as ex:  # noqa: BLE001
            show_snack(f"Devices error: {ex}", success=False)
        page.update()

    def on_device_search(e) -> None:
        current_page[0] = 1
        load_devices_table()

    search_field.on_change = on_device_search
    sort_dropdown.on_select = on_device_search
    order_dropdown.on_select = on_device_search

    f_device_id = ft.TextField(label="Device ID")
    f_model = ft.TextField(label="Model")
    f_status = ft.Dropdown(
        label="Status",
        options=[
            ft.dropdown.Option(key="online", text="online"),
            ft.dropdown.Option(key="offline", text="offline"),
            ft.dropdown.Option(key="maintenance", text="maintenance"),
        ],
    )
    f_room = ft.TextField(label="Room ID (1-5)")

    def build_device_payload(did, model, status, room):
        if not (did or "").strip():
            return None, "Device ID required"
        if not (model or "").strip():
            return None, "Model required"
        if not status:
            return None, "Status required"
        try:
            rid = int(room)
        except (TypeError, ValueError):
            return None, "Room ID must be a number"
        return {
            "device_id": did.strip(),
            "model": model.strip(),
            "status": status,
            "room_id": rid,
        }, None

    def make_edit(device):
        def handler(e):
            ed_id = ft.TextField(label="Device ID", value=device["device_id"])
            ed_model = ft.TextField(label="Model", value=device["model"])
            ed_status = ft.Dropdown(
                label="Status",
                value=device["status"],
                options=f_status.options,
            )
            ed_room = ft.TextField(label="Room ID", value=str(device["room_id"]))

            def close_dlg(e=None):
                dlg.open = False
                page.update()

            def save(e):
                payload, err = build_device_payload(
                    ed_id.value, ed_model.value, ed_status.value, ed_room.value
                )
                if err:
                    show_snack(err, success=False)
                    return
                resp = requests.put(
                    f"{API_BASE_URL}/devices/{device['id']}",
                    json=payload,
                    headers=headers(),
                    timeout=5,
                )
                if resp.status_code == 200:
                    close_dlg()
                    show_snack("Device updated")
                    load_devices_table()
                else:
                    show_snack(str(resp.json().get("detail", resp.text)), success=False)

            dlg = ft.AlertDialog(
                title=ft.Text("Edit Device"),
                content=ft.Column([ed_id, ed_model, ed_status, ed_room], tight=True),
                actions=[
                    ft.TextButton("Cancel", on_click=close_dlg),
                    ft.TextButton("Save", on_click=save),
                ],
            )
            page.show_dialog(dlg)

        return handler

    def make_delete(device_id):
        def handler(e):
            def close_dlg(e=None):
                dlg.open = False
                page.update()

            def confirm(e):
                resp = requests.delete(
                    f"{API_BASE_URL}/devices/{device_id}",
                    headers=headers(),
                    timeout=5,
                )
                close_dlg()
                if resp.status_code == 200:
                    show_snack("Device deleted")
                    load_devices_table()
                else:
                    show_snack(str(resp.json().get("detail", resp.text)), success=False)

            dlg = ft.AlertDialog(
                title=ft.Text("Delete device?"),
                content=ft.Text("This cannot be undone."),
                actions=[
                    ft.TextButton("Cancel", on_click=close_dlg),
                    ft.TextButton("Delete", on_click=confirm),
                ],
            )
            page.show_dialog(dlg)

        return handler

    def submit_new_device(e) -> None:
        payload, err = build_device_payload(
            f_device_id.value, f_model.value, f_status.value, f_room.value
        )
        if err:
            show_snack(err, success=False)
            return
        resp = requests.post(
            f"{API_BASE_URL}/devices", json=payload, headers=headers(), timeout=5
        )
        if resp.status_code in (200, 201):
            show_snack("Device added")
            f_device_id.value = f_model.value = f_room.value = ""
            f_status.value = None
            load_devices_table()
        else:
            show_snack(str(resp.json().get("detail", resp.text)), success=False)

    add_device_form = ft.Column(
        [
            ft.Divider(color=ft.Colors.BLUE_800),
            ft.Row(
                [
                    ft.Icon(ft.Icons.ADD_BOX, color=ft.Colors.BLUE_400),
                    ft.Text("Add device", size=15, weight=ft.FontWeight.BOLD),
                ],
                spacing=8,
            ),
            f_device_id,
            f_model,
            f_status,
            f_room,
            ft.FilledButton(
                "Add device",
                icon=ft.Icons.ADD,
                on_click=submit_new_device,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_700,
                    color=ft.Colors.WHITE,
                    text_style=ft.TextStyle(weight=ft.FontWeight.BOLD),
                ),
                width=220,
            ),
        ],
        spacing=10,
        visible=False,
    )

    devices_view = ft.Column(
        [
            ft.Row(
                [
                    ft.Icon(ft.Icons.DEVICES, color=ft.Colors.BLUE_400),
                    ft.Text("Devices", size=16, weight=ft.FontWeight.BOLD),
                ],
                spacing=8,
            ),
            ft.Container(height=14),
            search_field,
            ft.Container(height=16),
            ft.Row([sort_dropdown, order_dropdown], spacing=12),
            ft.Container(height=14),
            counter_text,
            ft.Container(height=10),
            ft.Container(
                content=ft.Column(
                    [ft.Row([devices_table], scroll=ft.ScrollMode.AUTO)],
                    scroll=ft.ScrollMode.AUTO,
                ),
                height=320,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                border_radius=8,
                padding=6,
            ),
            ft.Container(height=10),
            pager_row,
            add_device_form,
        ],
        scroll=ft.ScrollMode.AUTO,
        spacing=0,
    )

    # ── Alerts ─────────────────────────────────────────────────────────
    alert_filter = ft.Dropdown(
        label="Filter",
        width=180,
        value="all",
        options=[
            ft.dropdown.Option(key="all", text="All"),
            ft.dropdown.Option(key="0", text="Unacknowledged"),
            ft.dropdown.Option(key="1", text="Acknowledged"),
        ],
    )
    alerts_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("ID")),
            ft.DataColumn(ft.Text("Device")),
            ft.DataColumn(ft.Text("Type")),
            ft.DataColumn(ft.Text("Value")),
            ft.DataColumn(ft.Text("Threshold")),
            ft.DataColumn(ft.Text("Time")),
            ft.DataColumn(ft.Text("")),
        ],
        rows=[],
    )

    def load_alerts(e=None) -> None:
        params: dict = {"limit": 50, "offset": 0}
        if alert_filter.value != "all":
            params["acknowledged"] = alert_filter.value
        try:
            resp = requests.get(
                f"{API_BASE_URL}/alerts",
                headers=headers(),
                params=params,
                timeout=5,
            )
            resp.raise_for_status()
            items, _ = parse_paginated(resp.json())

            def ack_click(aid):
                def h(e):
                    r = requests.put(
                        f"{API_BASE_URL}/alerts/{aid}/acknowledge",
                        headers=headers(),
                        timeout=5,
                    )
                    if r.status_code == 200:
                        show_snack("Alert acknowledged")
                        load_alerts()
                    else:
                        show_snack("Acknowledge failed", success=False)

                return h

            rows = []
            for a in items:
                ack_btn = ft.IconButton(
                    icon=ft.Icons.CHECK_CIRCLE,
                    tooltip="Acknowledge",
                    disabled=bool(a["acknowledged"]),
                    on_click=ack_click(a["alert_id"]),
                )
                rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(str(a["alert_id"]))),
                            ft.DataCell(ft.Text(a["device_id"])),
                            ft.DataCell(ft.Text(a["alert_type"])),
                            ft.DataCell(ft.Text(str(a["value"]))),
                            ft.DataCell(ft.Text(str(a["threshold"]))),
                            ft.DataCell(ft.Text(a["timestamp"] or "")),
                            ft.DataCell(ack_btn),
                        ]
                    )
                )
            alerts_table.rows.clear()
            alerts_table.rows.extend(rows)
        except Exception as ex:  # noqa: BLE001
            show_snack(f"Alerts error: {ex}", success=False)
        page.update()

    alert_filter.on_select = load_alerts

    alerts_view = ft.Column(
        [
            ft.Row(
                [
                    ft.Icon(ft.Icons.WARNING_AMBER, color=ft.Colors.ORANGE_400),
                    ft.Text("Alerts", size=16, weight=ft.FontWeight.BOLD),
                ],
                spacing=8,
            ),
            ft.Container(height=14),
            alert_filter,
            ft.Container(height=14),
            ft.Container(
                content=ft.Column(
                    [ft.Row([alerts_table], scroll=ft.ScrollMode.AUTO)],
                    scroll=ft.ScrollMode.AUTO,
                ),
                height=400,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                border_radius=8,
                padding=6,
            ),
        ],
        scroll=ft.ScrollMode.AUTO,
        spacing=0,
    )

    # ── Settings (admin) ───────────────────────────────────────────────
    settings_device_dd = ft.Dropdown(label="Device", width=300, options=[])
    settings_pm25 = ft.TextField(label="PM2.5 threshold", value="35")
    settings_co2 = ft.TextField(label="CO₂ threshold", value="1000")

    def load_settings_devices() -> None:
        try:
            resp = requests.get(
                f"{API_BASE_URL}/devices",
                headers=headers(),
                params={"limit": 100, "offset": 0},
                timeout=5,
            )
            resp.raise_for_status()
            items, _ = parse_paginated(resp.json())
            settings_device_dd.options = [
                ft.dropdown.Option(
                    key=str(d["id"]),
                    text=f"{d['device_id']} ({d['model']})",
                )
                for d in items
            ]
            if items:
                settings_device_dd.value = str(items[0]["id"])
                settings_pm25.value = str(items[0].get("pm25_threshold", 35))
                settings_co2.value = str(items[0].get("co2_threshold", 1000))
        except Exception as ex:  # noqa: BLE001
            show_snack(f"Settings load error: {ex}", success=False)

    def on_settings_device_pick(e) -> None:
        did = settings_device_dd.value
        if not did:
            return
        try:
            resp = requests.get(
                f"{API_BASE_URL}/devices/{did}",
                headers=headers(),
                timeout=5,
            )
            resp.raise_for_status()
            d = resp.json()
            settings_pm25.value = str(d.get("pm25_threshold", 35))
            settings_co2.value = str(d.get("co2_threshold", 1000))
            page.update()
        except Exception:  # noqa: BLE001
            pass

    settings_device_dd.on_select = on_settings_device_pick

    def save_thresholds(e) -> None:
        did = settings_device_dd.value
        if not did:
            show_snack("Select a device", success=False)
            return
        try:
            pm = float(settings_pm25.value)
            co = float(settings_co2.value)
        except ValueError:
            show_snack("Thresholds must be numbers", success=False)
            return
        resp = requests.put(
            f"{API_BASE_URL}/devices/{did}/thresholds",
            json={"pm25_threshold": pm, "co2_threshold": co},
            headers=headers(),
            timeout=5,
        )
        if resp.status_code == 200:
            show_snack("Thresholds saved")
        else:
            show_snack(str(resp.json().get("detail", resp.text)), success=False)

    def export_csv(e) -> None:
        try:
            resp = requests.get(
                f"{API_BASE_URL}/export/readings",
                headers=headers(),
                timeout=30,
            )
            resp.raise_for_status()
            out = Path.home() / "Downloads" / "readings_export.csv"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(resp.content)
            show_snack(f"Saved to {out}")
        except Exception as ex:  # noqa: BLE001
            show_snack(f"Export failed: {ex}", success=False)

    settings_view = ft.Column(
        [
            ft.Row(
                [
                    ft.Icon(ft.Icons.SETTINGS, color=ft.Colors.TEAL_400),
                    ft.Text("Settings", size=16, weight=ft.FontWeight.BOLD),
                ],
                spacing=8,
            ),
            ft.Container(height=10),
            ft.Text("Threshold configuration", size=15, weight=ft.FontWeight.W_500),
            ft.Container(height=6),
            settings_device_dd,
            ft.Container(height=8),
            settings_pm25,
            ft.Container(height=8),
            settings_co2,
            ft.Container(height=14),
            ft.FilledButton(
                "Save thresholds",
                icon=ft.Icons.SAVE,
                on_click=save_thresholds,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.TEAL_700,
                    color=ft.Colors.WHITE,
                    text_style=ft.TextStyle(weight=ft.FontWeight.BOLD),
                ),
                width=220,
            ),
            ft.Container(height=10),
            ft.Divider(),
            ft.Container(height=10),
            ft.Text("Export data", size=15, weight=ft.FontWeight.W_500),
            ft.Container(height=6),
            ft.FilledButton(
                "Export readings CSV",
                icon=ft.Icons.DOWNLOAD,
                on_click=export_csv,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_GREY_700,
                    color=ft.Colors.WHITE,
                    text_style=ft.TextStyle(weight=ft.FontWeight.BOLD),
                ),
                width=240,
            ),
        ],
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    # ── Bottom sheet: quick add reading ────────────────────────────────
    bs_device = ft.Dropdown(label="Device", options=[])
    bs_pm25 = ft.TextField(label="PM2.5")
    bs_co2 = ft.TextField(label="CO₂")

    def open_reading_sheet(e=None) -> None:
        try:
            resp = requests.get(
                f"{API_BASE_URL}/devices",
                headers=headers(),
                params={"limit": 20, "offset": 0},
                timeout=5,
            )
            resp.raise_for_status()
            items, _ = parse_paginated(resp.json())
            bs_device.options = [
                ft.dropdown.Option(key=d["device_id"], text=d["device_id"])
                for d in items
            ]
            if items:
                bs_device.value = items[0]["device_id"]
        except Exception as ex:  # noqa: BLE001
            show_snack(f"Cannot load devices: {ex}", success=False)
            return

        def submit_reading(e):
            try:
                pm = float(bs_pm25.value)
                co = float(bs_co2.value)
            except (TypeError, ValueError):
                show_snack("PM2.5 and CO₂ must be numbers", success=False)
                return
            if not bs_device.value:
                show_snack("Select a device", success=False)
                return
            r = requests.post(
                f"{API_BASE_URL}/readings",
                json={"device_id": bs_device.value, "pm25": pm, "co2": co},
                headers=headers(),
                timeout=5,
            )
            page.pop_dialog()
            page.update()
            if r.status_code == 201:
                show_snack("Reading added")
                if session["tab"] == 0:
                    load_dashboard()
                if session["tab"] == 2:
                    load_alerts()
            else:
                show_snack(str(r.json().get("detail", r.text)), success=False)

        sheet = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Text("Quick add reading", size=18, weight=ft.FontWeight.BOLD),
                        bs_device,
                        bs_pm25,
                        bs_co2,
                        ft.FilledButton(
                            "Submit reading",
                            icon=ft.Icons.ADD_CHART,
                            on_click=submit_reading,
                            width=320,
                        ),
                    ],
                    spacing=10,
                    padding=20,
                ),
                width=400,
            ),
            open=True,
        )
        page.show_dialog(sheet)

    # ── Shell: AppBar, MenuBar, nav, body ──────────────────────────────
    body = ft.Container(
        padding=ft.Padding.only(left=24, top=16, right=16, bottom=16),
        expand=True,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
    )

    TITLES = ["Dashboard", "Devices", "Alerts", "Settings"]
    VIEWS = [dashboard_view, devices_view, alerts_view, settings_view]

    def refresh_current_tab() -> None:
        if session["tab"] == 0:
            load_dashboard()
        elif session["tab"] == 1:
            load_devices_table()
        elif session["tab"] == 2:
            load_alerts()
        elif session["tab"] == 3:
            load_settings_devices()

    def do_logout(e=None) -> None:
        session["dashboard_refresh"] = False
        try:
            requests.post(
                f"{API_BASE_URL}/auth/logout", headers=headers(), timeout=3
            )
        except Exception:  # noqa: BLE001
            pass
        session["token"] = session["role"] = session["username"] = None
        login_user.value = ""
        login_pass.value = ""
        show_login_view()

    def build_menubar() -> ft.MenuBar:
        file_items = [
            ft.MenuItemButton(
                content=ft.Text("Export readings CSV"),
                on_click=export_csv,
            ),
        ]
        view_items = [
            ft.MenuItemButton(
                content=ft.Text("Refresh"),
                on_click=lambda e: refresh_current_tab(),
            ),
        ]
        menus = [
            ft.SubmenuButton(content=ft.Text("File"), controls=file_items),
            ft.SubmenuButton(content=ft.Text("View"), controls=view_items),
        ]
        return ft.MenuBar(controls=menus)

    def on_nav_change(e) -> None:
        idx = e.control.selected_index
        session["tab"] = idx
        if is_admin():
            body.content = VIEWS[idx]
        else:
            body.content = VIEWS[idx if idx < 3 else 0]
        if idx == 0 or (not is_admin() and idx == 0):
            load_dashboard()
        elif idx == 1:
            load_devices_table()
            add_device_form.visible = is_admin()
        elif idx == 2:
            load_alerts()
        elif idx == 3 and is_admin():
            load_settings_devices()
        page.appbar.title = ft.Text(TITLES[idx if is_admin() else min(idx, 2)])
        page.update()

    def show_main_shell() -> None:
        page.controls.clear()
        add_device_form.visible = is_admin()

        destinations = [
            ft.NavigationBarDestination(icon=ft.Icons.DASHBOARD, label="Dashboard"),
            ft.NavigationBarDestination(icon=ft.Icons.DEVICES, label="Devices"),
            ft.NavigationBarDestination(icon=ft.Icons.WARNING, label="Alerts"),
        ]
        if is_admin():
            destinations.append(
                ft.NavigationBarDestination(icon=ft.Icons.SETTINGS, label="Settings")
            )

        page.appbar = ft.AppBar(
            leading=ft.Icon(ft.Icons.AIR, color=ft.Colors.BLUE_300),
            leading_width=44,
            title=ft.Text("Dashboard"),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            actions=[
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.PERSON, size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                            ft.Text(
                                f"{session['username']}  ·  {session['role']}",
                                size=12,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=4,
                    ),
                    padding=ft.Padding.only(right=4),
                ),
                ft.IconButton(
                    icon=ft.Icons.LOGOUT,
                    tooltip="Logout",
                    on_click=do_logout,
                ),
            ],
        )
        page.navigation_bar = ft.NavigationBar(
            destinations=destinations,
            on_change=on_nav_change,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            indicator_color=ft.Colors.BLUE_800,
            label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
        )
        page.bottom_appbar = ft.BottomAppBar(
            bgcolor=ft.Colors.INDIGO_900,
            content=ft.Row(
                [
                    ft.IconButton(
                        icon=ft.Icons.REFRESH,
                        icon_color=ft.Colors.INDIGO_100,
                        tooltip="Refresh",
                        on_click=lambda e: refresh_current_tab(),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.ADD_CHART,
                        icon_color=ft.Colors.INDIGO_100,
                        tooltip="Add reading",
                        on_click=open_reading_sheet,
                    ),
                ],
                alignment=ft.MainAxisAlignment.END,
            ),
        )
        body.content = dashboard_view
        session["tab"] = 0
        page.add(ft.Column([build_menubar(), body], expand=True))
        load_dashboard()
        session["dashboard_refresh"] = True
        page.run_task(dashboard_refresh_loop)

    # Start at login
    ok, _ = check_api()
    page.add(login_view)
    if not ok:
        show_snack("API not running — start uvicorn, then sign in", success=False)


if __name__ == "__main__":
    ft.run(main)
