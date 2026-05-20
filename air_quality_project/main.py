"""Air Quality Monitor - Flet desktop UI (login, dashboard, devices, alerts, settings)."""

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
    page.title = "FreshX — Clean Air, Clear Mind"
    page.padding = 0
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0B1220"
    page.theme = ft.Theme(
        color_scheme=ft.ColorScheme(
            primary="#2DD4BF",
            secondary="#38BDF8",
            surface="#0B1220",
        ),
    )

    C = type("C", (), {})()
    C.BG = "#0B1220"
    C.BG2 = "#121A2B"
    C.NAV = "#111827"
    C.FOOTER = "#0A101C"
    C.CARD = "#1B2538"
    C.ACCENT = "#2DD4BF"
    C.ACCENT2 = "#38BDF8"
    C.TEXT = "#F3F4F6"
    C.TEXT2 = "#9CA3AF"
    C.GREEN = "#22C55E"
    C.WARN = "#F59E0B"
    C.RED = "#EF4444"

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
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.BAR_CHART, size=40, color=ft.Colors.GREY_600),
                        ft.Text("No readings yet", size=14, color=ft.Colors.GREY_500),
                        ft.FilledTonalButton(
                            "Add reading",
                            icon=ft.Icons.ADD_CHART,
                            on_click=open_reading_sheet,
                            style=ft.ButtonStyle(text_style=ft.TextStyle(size=12)),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                bgcolor=C.CARD,
                border_radius=12,
                padding=30,
            )
        subset = points[-40:]
        max_pm = max(p["pm25"] for p in subset) or 1
        max_co2 = max(p["co2"] for p in subset) or 1
        PM_H = 110
        CO2_H = 75

        pm_bars = ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        ft.Container(height=PM_H - max(4, int(p["pm25"] / max_pm * PM_H))),
                        ft.Container(
                            width=7,
                            height=max(4, int(p["pm25"] / max_pm * PM_H)),
                            bgcolor=_bar_color(p["pm25"]),
                            border_radius=ft.BorderRadius(top_left=2, top_right=2, bottom_left=0, bottom_right=0),
                        ),
                    ],
                    spacing=0,
                    height=PM_H,
                )
                for p in subset
            ],
            spacing=2,
            tight=True,
        )

        co2_bars = ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        ft.Container(height=CO2_H - max(3, int(p["co2"] / max_co2 * CO2_H))),
                        ft.Container(
                            width=7,
                            height=max(3, int(p["co2"] / max_co2 * CO2_H)),
                            bgcolor=ft.Colors.with_opacity(0.85, C.ACCENT2),
                            border_radius=ft.BorderRadius(top_left=2, top_right=2, bottom_left=0, bottom_right=0),
                        ),
                    ],
                    spacing=0,
                    height=CO2_H,
                )
                for p in subset
            ],
            spacing=2,
            tight=True,
        )

        legend = ft.Row(
            [
                ft.Container(width=10, height=10, bgcolor=ft.Colors.GREEN_400, border_radius=2),
                ft.Text("Good (<=12)", size=11, color=C.TEXT2),
                ft.Container(width=10, height=10, bgcolor=ft.Colors.AMBER_400, border_radius=2),
                ft.Text("Moderate (<=35)", size=11, color=C.TEXT2),
                ft.Container(width=10, height=10, bgcolor=ft.Colors.RED_400, border_radius=2),
                ft.Text("High (>35)", size=11, color=C.TEXT2),
            ],
            spacing=6,
        )
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("PM2.5 trend - last 24 h", weight=ft.FontWeight.BOLD, color=C.TEXT),
                        ft.Container(expand=True),
                        ft.Text(f"{len(subset)} readings", size=11, color=C.TEXT2),
                    ],
                ),
                ft.Container(
                    content=ft.Column([pm_bars], scroll=ft.ScrollMode.AUTO),
                    height=PM_H + 12,
                    bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.WHITE),
                    border_radius=8,
                    padding=ft.Padding.only(left=4, right=4, top=8, bottom=4),
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                ),
                legend,
                ft.Container(height=4),
                ft.Row(
                    [
                        ft.Text("CO2 trend - last 24 h", weight=ft.FontWeight.BOLD, color=C.TEXT),
                        ft.Container(expand=True),
                        ft.Container(width=10, height=10, bgcolor=C.ACCENT2, border_radius=2),
                        ft.Text("ppm", size=11, color=C.TEXT2),
                    ],
                ),
                ft.Container(
                    content=ft.Column([co2_bars], scroll=ft.ScrollMode.AUTO),
                    height=CO2_H + 12,
                    bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.WHITE),
                    border_radius=8,
                    padding=ft.Padding.only(left=4, right=4, top=8, bottom=4),
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                ),
            ],
            spacing=8,
        )

    # -- Login --
    login_user = ft.TextField(label="Username", autofocus=True)
    login_pass = ft.TextField(label="Password", password=True, can_reveal_password=True)
    remember_me = ft.Checkbox(label="Remember me", value=False)

    async def _get_pref(key: str):
        try:
            return await ft.SharedPreferences().get(key)
        except Exception:  # noqa: BLE001
            return None

    async def _set_pref(key: str, value: str):
        try:
            await ft.SharedPreferences().set(key, value)
        except Exception:  # noqa: BLE001
            pass

    async def _del_pref(key: str):
        try:
            await ft.SharedPreferences().remove(key)
        except Exception:  # noqa: BLE001
            pass

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
            show_snack("Cannot reach API - start uvicorn first", success=False)
            return
        if resp.status_code != 200:
            detail = resp.json().get("detail", resp.text) if resp.content else resp.text
            show_snack(str(detail), success=False)
            return
        data = resp.json()
        session["token"] = data["token"]
        session["role"] = data["role"]
        session["username"] = data["username"]
        if remember_me.value:
            page.run_task(_set_pref, "remembered_user", login_user.value.strip())
        else:
            page.run_task(_del_pref, "remembered_user")
        show_snack(f"Welcome, {data['username']} ({data['role']})")
        show_main_shell()

    login_pass.on_submit = do_login

    def show_login_view() -> None:
        page.controls.clear()
        page.appbar = None
        page.navigation_bar = None
        page.bottom_appbar = None
        page.add(login_view)
        page.run_task(_restore_remembered_user)
        page.update()

    async def _restore_remembered_user():
        val = await _get_pref("remembered_user")
        if val:
            login_user.value = val
            remember_me.value = True
            login_user.update()

    def greeting_time() -> str:
        import datetime
        h = datetime.datetime.now().hour
        if h < 12:
            return "Good morning"
        if h < 18:
            return "Good afternoon"
        return "Good evening"

    login_view = ft.Container(
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        width=56, height=56,
                        border_radius=28,
                        bgcolor=ft.Colors.BLUE_900,
                        content=ft.Icon(ft.Icons.AIR, size=32, color=ft.Colors.BLUE_200),
                    ),
                    ft.Text("FreshX", size=28, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        "Clean Air, Clear Mind",
                        color=C.ACCENT,
                        size=13,
                        weight=ft.FontWeight.W_500,
                    ),
                    ft.Container(height=2),
                    ft.Text(
                        "Sign in to continue",
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        size=12,
                    ),
                    ft.Container(height=20),
                    login_user,
                    ft.Container(height=12),
                    login_pass,
                    ft.Container(height=4),
                    remember_me,
                    ft.Container(height=10),
                    ft.FilledButton(
                        "Sign In",
                        icon=ft.Icons.LOGIN,
                        on_click=do_login,
                        width=200,
                    ),
                    ft.Container(height=12),
                    ft.Row(
                        [
                            ft.TextButton(
                                "Forgot password?",
                                on_click=lambda e: show_snack("Contact admin to reset your password", success=False),
                                style=ft.ButtonStyle(color=ft.Colors.GREY_400, text_style=ft.TextStyle(size=12)),
                            ),
                            ft.Text("|", size=12, color=ft.Colors.GREY_600),
                            ft.TextButton(
                                "Create account",
                                on_click=lambda e: show_snack("Account creation is managed by the administrator", success=False),
                                style=ft.ButtonStyle(color=ft.Colors.GREY_400, text_style=ft.TextStyle(size=12)),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=6,
                    ),
                    ft.Container(height=4),
                    ft.Text("v1.0.0", size=10, color=ft.Colors.GREY_600),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
                width=340,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.Padding.all(40),
            border_radius=20,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            width=460,
            height=520,
            alignment=ft.Alignment(0, 0),
        ),
        alignment=ft.Alignment(0, 0),
        expand=True,
    )

    # -- Dashboard --
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

    dash_greeting = ft.Text(size=20, weight=ft.FontWeight.BOLD, color=C.TEXT)
    dash_last_updated = ft.Text("", size=11, color=C.TEXT2)
    dash_status_dot = ft.Container(width=8, height=8, border_radius=4, bgcolor=C.GREEN)
    card_devices = ft.Text("--", size=28, weight=ft.FontWeight.BOLD, color=C.ACCENT2)
    card_pm25 = ft.Text("--", size=24, weight=ft.FontWeight.BOLD, color=C.GREEN)
    card_co2 = ft.Text("--", size=24, weight=ft.FontWeight.BOLD, color=C.WARN)
    card_alerts = ft.Text("--", size=28, weight=ft.FontWeight.BOLD, color=C.RED)
    chart_area = ft.Container()
    readings_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("ID", color=C.TEXT2, weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Device", color=C.TEXT2, weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("PM2.5", color=C.TEXT2, weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("CO2", color=C.TEXT2, weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Time", color=C.TEXT2, weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
        border=ft.Border.all(0, ft.Colors.TRANSPARENT),
        heading_row_color={ft.ControlState.DEFAULT: ft.Colors.with_opacity(0.06, C.ACCENT2)},
        data_row_color={ft.ControlState.DEFAULT: ft.Colors.TRANSPARENT},
        divider_thickness=0.5,
    )

    def load_dashboard() -> None:
        import datetime
        uname = session.get("username", "User")
        dash_greeting.value = f"{greeting_time()}, {uname}!"
        dash_last_updated.value = f"Last updated: {datetime.datetime.now():%H:%M:%S}"
        ok, _ = check_api()
        dash_status_dot.bgcolor = C.GREEN if ok else C.RED
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

            empty = (
                summary["active_devices"] == 0
                and summary["avg_pm25"] == 0
                and summary["avg_co2"] == 0
            )
            if empty:
                dash_empty_hint.content = ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=ft.Colors.GREY_400),
                            ft.Text(
                                "No data yet - run seed.py to populate the database",
                                size=12, color=ft.Colors.GREY_400,
                            ),
                        ],
                        spacing=8, alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    border_radius=8, padding=10,
                )
            dash_empty_hint.visible = empty

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
                        ft.DataCell(ft.Text(str(x["reading_id"]), color=C.TEXT2, size=12)),
                        ft.DataCell(ft.Text(x["device_id"], color=C.TEXT, weight=ft.FontWeight.W_500)),
                        ft.DataCell(ft.Text(str(x["pm25"]), color=C.GREEN)),
                        ft.DataCell(ft.Text(str(x["co2"]), color=C.WARN)),
                        ft.DataCell(ft.Text(x["timestamp"] or "", color=C.TEXT2, size=11)),
                    ]
                )
                for x in items
            ]
        except Exception as ex:  # noqa: BLE001
            show_snack(f"Dashboard error: {ex}", success=False)
        page.update()

    def summary_card(title: str, value_ctrl: ft.Text, icon, accent: str, unit: str = "", bg: str | None = None) -> ft.Container:
        unit_label = ft.Text(unit, size=10, color=accent) if unit else ft.Container(width=0, height=0)
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [ft.Icon(icon, size=14, color=accent), ft.Text(title, size=12, color=C.TEXT2)],
                        spacing=4,
                    ),
                    ft.Row(
                        [value_ctrl, unit_label],
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                    ),
                ],
                spacing=8,
            ),
            padding=16,
            bgcolor=bg if bg else C.CARD,
            border_radius=12,
            border=ft.Border(left=ft.BorderSide(3, accent)),
            expand=True,
        )

    dash_empty_hint = ft.Container(visible=False)
    dashboard_left = ft.Column(
        [
            ft.Row(
                [
                    ft.Column(
                        [dash_greeting, dash_last_updated],
                        spacing=2,
                    ),
                    ft.Container(expand=True),
                    ft.Row(
                        [
                            dash_status_dot,
                            ft.Text("API", size=11, color=C.TEXT2),
                        ],
                        spacing=4,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Container(height=4),
            ft.Container(
                content=ft.Row(
                    [
                        ft.Text("Check Air Quality in Realtime", size=18, weight=ft.FontWeight.BOLD, color=C.ACCENT2),
                        ft.Container(width=8),
                        ft.Container(
                            content=ft.Text("LIVE", size=9, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                            bgcolor=C.RED,
                            border_radius=4,
                        ),
                    ],
                    spacing=0,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                border_radius=8,
                bgcolor=ft.Colors.with_opacity(0.1, C.ACCENT2),
            ),
            ft.Container(height=12),
            ft.Row(
                [
                    summary_card("Active devices", card_devices, ft.Icons.SENSORS, C.ACCENT2, bg=ft.Colors.with_opacity(0.14, C.ACCENT2)),
                    summary_card("Avg PM2.5 (24h)", card_pm25, ft.Icons.AIR, C.GREEN, "ug/m3", bg=ft.Colors.with_opacity(0.14, C.GREEN)),
                    summary_card("Avg CO2 (24h)", card_co2, ft.Icons.CLOUD, C.WARN, "ppm", bg=ft.Colors.with_opacity(0.14, C.WARN)),
                    summary_card("Open alerts", card_alerts, ft.Icons.WARNING_AMBER, C.RED, bg=ft.Colors.with_opacity(0.14, C.RED)),
                ],
                spacing=10,
            ),
            dash_empty_hint,
            ft.Container(height=12),
            chart_area,
            ft.Container(height=18),
            ft.Row(
                [
                    ft.Text("Recent readings", weight=ft.FontWeight.BOLD, color=C.TEXT),
                    ft.Container(expand=True),
                    ft.FilledTonalButton(
                        "Export CSV",
                        icon=ft.Icons.DOWNLOAD,
                        on_click=export_csv,
                        style=ft.ButtonStyle(
                            bgcolor=C.ACCENT,
                            color="#000000",
                            text_style=ft.TextStyle(weight=ft.FontWeight.BOLD, size=12),
                        ),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Container(
                content=ft.Row([readings_table], scroll=ft.ScrollMode.AUTO),
                border=ft.Border.all(1, ft.Colors.with_opacity(0.15, C.ACCENT2)),
                border_radius=8,
                padding=4,
                bgcolor=ft.Colors.with_opacity(0.03, C.ACCENT2),
            ),
            ft.Container(height=8),
        ],
        scroll=ft.ScrollMode.AUTO,
        spacing=12,
    )

    dashboard_view = dashboard_left

    async def dashboard_refresh_loop() -> None:
        while session["dashboard_refresh"] and session["token"]:
            await asyncio.sleep(5)
            if session["tab"] == 0 and session["token"]:
                await asyncio.to_thread(load_dashboard)

    # -- Devices --
    current_page = [1]
    total_pages = [1]
    search_hovered = [False]
    search_field = ft.TextField(
        label="Search devices",
        prefix_icon=ft.Icons.SEARCH,
        expand=True,
        content_padding=ft.Padding.symmetric(horizontal=16, vertical=18),
    )

    def on_search_hover(e) -> None:
        search_hovered[0] = e.data == "true"
        update_search_border()

    search_container = ft.Container(
        content=ft.Row(
            [
                search_field,
                ft.IconButton(
                    icon=ft.Icons.TUNE,
                    tooltip="Filter options",
                    icon_color=ft.Colors.GREY_400,
                    on_click=lambda e: show_snack("Filter options coming soon"),
                ),
                ft.IconButton(
                    icon=ft.Icons.REFRESH,
                    tooltip="Refresh",
                    icon_color=ft.Colors.GREY_400,
                    on_click=lambda e: load_devices_table(),
                ),
            ],
            spacing=4,
        ),
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=8,
        padding=ft.Padding.only(left=4, right=4, top=2, bottom=2),
        bgcolor=ft.Colors.SURFACE,
        animate=ft.Animation(200, ft.AnimationCurve.EASE_IN_OUT),
        on_hover=on_search_hover,
    )

    def update_search_border() -> None:
        if search_hovered[0]:
            search_container.border = ft.Border.all(2, ft.Colors.BLUE_400)
            search_container.bgcolor = ft.Colors.SURFACE_CONTAINER
        else:
            search_container.border = ft.Border.all(1, ft.Colors.OUTLINE_VARIANT)
            search_container.bgcolor = ft.Colors.SURFACE
        search_container.update()

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
            ft.DataColumn(ft.Row([ft.Icon(ft.Icons.TAG, size=14, color=ft.Colors.GREY_500), ft.Text("ID")], spacing=4)),
            ft.DataColumn(ft.Row([ft.Icon(ft.Icons.DEVICES, size=14, color=ft.Colors.GREY_500), ft.Text("Device ID")], spacing=4)),
            ft.DataColumn(ft.Row([ft.Icon(ft.Icons.MEMORY, size=14, color=ft.Colors.GREY_500), ft.Text("Model")], spacing=4)),
            ft.DataColumn(ft.Row([ft.Icon(ft.Icons.CIRCLE, size=14, color=ft.Colors.GREY_500), ft.Text("Status")], spacing=4)),
            ft.DataColumn(ft.Row([ft.Icon(ft.Icons.MEETING_ROOM, size=14, color=ft.Colors.GREY_500), ft.Text("Room")], spacing=4)),
            ft.DataColumn(ft.Row([ft.Icon(ft.Icons.BUILD, size=14, color=ft.Colors.GREY_500), ft.Text("Actions")], spacing=4)),
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
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.BLUE_800 if n == cp else None,
                        color=ft.Colors.WHITE if n == cp else None,
                        shape=ft.RoundedRectangleBorder(radius=6),
                    ),
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
            devices_summary_text.value = f"Total: {total} device{'s' if total != 1 else ''}"

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
                            ft.DataCell(ft.Text(d.get("room_name") or str(d["room_id"]))),
                            ft.DataCell(ft.Row(actions, spacing=0)),
                        ]
                    )
                )
            devices_table.rows.clear()
            devices_table.rows.extend(rows)
            start = offset + 1 if total else 0
            end = min(offset + len(items), total)
            if total == 0:
                counter_text.value = ""
                if not items:
                    devices_table.rows.clear()
                    devices_table.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text("")),
                                ft.DataCell(
                                    ft.Column(
                                        [
                                            ft.Icon(ft.Icons.DEVICES, size=32, color=ft.Colors.GREY_600),
                                            ft.Text("No devices yet", size=14, color=ft.Colors.GREY_500),
                                            ft.Text("Add one using the form below", size=11, color=ft.Colors.GREY_600),
                                        ],
                                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                        spacing=4,
                                    )
                                ),
                                ft.DataCell(ft.Text("")),
                                ft.DataCell(ft.Text("")),
                                ft.DataCell(ft.Text("")),
                                ft.DataCell(ft.Text("")),
                            ]
                        )
                    )
            else:
                counter_text.value = f"Showing {start}-{end} of {total} devices"
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
    f_room = ft.TextField(label="Room ID")

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
            ed_id = ft.TextField(
                label="Device ID",
                value=device["device_id"],
                read_only=True,
                hint_text="Device ID cannot be changed",
                bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.GREY_500),
            )
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

    devices_summary_text = ft.Text("", size=12, color=C.TEXT2)
    devices_view = ft.Column(
        [
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.DEVICES, color=C.ACCENT2),
                                ft.Text("Devices", size=16, weight=ft.FontWeight.BOLD, color=C.TEXT),
                                ft.Container(expand=True),
                                devices_summary_text,
                            ],
                            spacing=8,
                        ),
                        ft.Container(height=14),
                        search_container,
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
                            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, C.TEXT2)),
                            border_radius=8,
                            padding=6,
                            bgcolor=C.CARD,
                        ),
                        ft.Container(height=10),
                        pager_row,
                        ft.Container(
                            content=add_device_form,
                            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, C.ACCENT2)),
                            border_radius=8,
                            padding=12,
                            bgcolor=C.CARD,
                        ),
                    ],
                    spacing=0,
                ),
                padding=16,
                border=ft.Border.all(1, ft.Colors.with_opacity(0.2, C.TEXT2)),
                border_radius=12,
                bgcolor=C.BG2,
            ),
        ],
        scroll=ft.ScrollMode.AUTO,
        spacing=0,
    )

    # -- Alerts --
    alert_filter = ft.Dropdown(
        label="Filter",
        width=180,
        value="all",
        options=[
            ft.dropdown.Option(key="all", text="All"),
            ft.dropdown.Option(key="0", text="Unacknowledged"),
            ft.dropdown.Option(key="1", text="Remediated"),
        ],
    )
    alerts_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Row([ft.Icon(ft.Icons.TAG, size=14, color=ft.Colors.GREY_500), ft.Text("ID")], spacing=4)),
            ft.DataColumn(ft.Row([ft.Icon(ft.Icons.DEVICES, size=14, color=ft.Colors.GREY_500), ft.Text("Device")], spacing=4)),
            ft.DataColumn(ft.Row([ft.Icon(ft.Icons.CATEGORY, size=14, color=ft.Colors.GREY_500), ft.Text("Type")], spacing=4)),
            ft.DataColumn(ft.Row([ft.Icon(ft.Icons.SPEED, size=14, color=ft.Colors.GREY_500), ft.Text("Value")], spacing=4)),
            ft.DataColumn(ft.Row([ft.Icon(ft.Icons.STRAIGHTEN, size=14, color=ft.Colors.GREY_500), ft.Text("Threshold")], spacing=4)),
            ft.DataColumn(ft.Row([ft.Icon(ft.Icons.SCHEDULE, size=14, color=ft.Colors.GREY_500), ft.Text("Time")], spacing=4)),
            ft.DataColumn(ft.Text("Action")),
        ],
        rows=[],
    )

    def _alert_row_color(value: float, threshold: float, acknowledged: bool) -> dict:
        if acknowledged:
            return {ft.ControlState.DEFAULT: ft.Colors.with_opacity(0.12, ft.Colors.GREEN_400)}
        if threshold <= 0:
            return {}
        ratio = value / threshold
        if ratio >= 1.5:
            return {ft.ControlState.DEFAULT: ft.Colors.with_opacity(0.50, ft.Colors.RED_400)}
        if ratio >= 1.2:
            return {ft.ControlState.DEFAULT: ft.Colors.with_opacity(0.45, ft.Colors.ORANGE_400)}
        return {ft.ControlState.DEFAULT: ft.Colors.with_opacity(0.30, ft.Colors.YELLOW_600)}

    def _severity_badge(value: float, threshold: float) -> ft.Container:
        if threshold <= 0:
            return ft.Container()
        ratio = value / threshold
        if ratio >= 1.5:
            label, color = "HIGH", C.RED
        elif ratio >= 1.2:
            label, color = "MED", "#EA580C"
        else:
            label, color = "LOW", "#CA8A04"
        return ft.Container(
            content=ft.Text(label, size=9, weight=ft.FontWeight.BOLD, color=color),
            padding=ft.Padding.symmetric(horizontal=5, vertical=2),
            border_radius=4,
            border=ft.Border.all(1, color),
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
            total_alerts = len(items)
            n_remediated = sum(1 for x in items if x.get("acknowledged"))
            n_open = total_alerts - n_remediated
            if alert_filter.value == "all":
                alerts_summary_text.value = f"Total: {total_alerts}  |  Open: {n_open}  |  Remediated: {n_remediated}"
            elif alert_filter.value == "0":
                alerts_summary_text.value = f"Open: {total_alerts}"
            else:
                alerts_summary_text.value = f"Remediated: {total_alerts}"

            def ack_click(aid):
                def h(e):
                    r = requests.put(
                        f"{API_BASE_URL}/alerts/{aid}/acknowledge",
                        headers=headers(),
                        timeout=5,
                    )
                    if r.status_code == 200:
                        show_snack("Alert remediated")
                        load_alerts()
                    else:
                        show_snack("Remediate failed", success=False)
                return h

            rows = []
            for a in items:
                is_acked = bool(a["acknowledged"])
                val = float(a["value"])
                thr = float(a["threshold"])

                if is_acked:
                    action_cell = ft.Row(
                        [
                            ft.Icon(ft.Icons.CHECK_CIRCLE, color=C.GREEN, size=16),
                            ft.Text("Remediated", size=12, color=C.GREEN),
                        ],
                        spacing=4,
                        tight=True,
                    )
                else:
                    action_cell = ft.FilledTonalButton(
                        "Remediate",
                        icon=ft.Icons.HEALING,
                        on_click=ack_click(a["alert_id"]),
                        style=ft.ButtonStyle(
                            bgcolor={
                                ft.ControlState.DEFAULT: ft.Colors.GREEN_800,
                                ft.ControlState.HOVERED: ft.Colors.GREEN_600,
                            },
                            color=ft.Colors.WHITE,
                            text_style=ft.TextStyle(weight=ft.FontWeight.BOLD),
                        ),
                    )

                rows.append(
                    ft.DataRow(
                        color=_alert_row_color(val, thr, is_acked),
                        cells=[
                            ft.DataCell(ft.Text(str(a["alert_id"]))),
                            ft.DataCell(ft.Text(a["device_id"], weight=ft.FontWeight.W_500)),
                            ft.DataCell(
                                ft.Row(
                                    [_severity_badge(val, thr), ft.Text(a["alert_type"].upper(), size=12)],
                                    spacing=6, tight=True,
                                )
                            ),
                            ft.DataCell(ft.Text(str(val))),
                            ft.DataCell(ft.Text(str(thr))),
                            ft.DataCell(ft.Text(a["timestamp"] or "", size=12)),
                            ft.DataCell(action_cell),
                        ]
                    )
                )

            if not items:
                alerts_table.rows.clear()
                alerts_table.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text("")),
                            ft.DataCell(
                                ft.Column(
                                    [
                                        ft.Container(
                                            width=40, height=40,
                                            border_radius=20,
                                            bgcolor=ft.Colors.GREEN_900,
                                            content=ft.Icon(ft.Icons.CHECK, size=24, color=ft.Colors.GREEN_200),
                                        ),
                                        ft.Text("All clear", size=14, color=ft.Colors.GREEN_300),
                                        ft.Text("No alerts to show", size=11, color=ft.Colors.GREY_500),
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=4,
                                )
                            ),
                            ft.DataCell(ft.Text("")),
                            ft.DataCell(ft.Text("")),
                            ft.DataCell(ft.Text("")),
                            ft.DataCell(ft.Text("")),
                            ft.DataCell(ft.Text("")),
                        ]
                    )
                )
            else:
                alerts_table.rows.clear()
                alerts_table.rows.extend(rows)
        except Exception as ex:  # noqa: BLE001
            show_snack(f"Alerts error: {ex}", success=False)
        page.update()

    alert_filter.on_select = load_alerts

    alerts_summary_text = ft.Text("", size=12, color=C.RED)
    alerts_view = ft.Column(
        [
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.WARNING_AMBER, color=C.RED, size=24),
                                ft.Text("Alerts", size=22, weight=ft.FontWeight.BOLD, color=C.TEXT),
                                ft.Container(expand=True),
                                alerts_summary_text,
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Container(height=14),
                        ft.Row(
                            [
                                ft.Row([ft.Container(width=12, height=12, bgcolor=C.RED, border_radius=3),
                                        ft.Text("HIGH (>=1.5x)", size=12, color=C.TEXT2)], spacing=5),
                                ft.Row([ft.Container(width=12, height=12, bgcolor="#EA580C", border_radius=3),
                                        ft.Text("MED (>=1.2x)", size=12, color=C.TEXT2)], spacing=5),
                                ft.Row([ft.Container(width=12, height=12, bgcolor="#CA8A04", border_radius=3),
                                        ft.Text("LOW (>threshold)", size=12, color=C.TEXT2)], spacing=5),
                                ft.Row([ft.Container(width=12, height=12, bgcolor=C.GREEN, border_radius=3),
                                        ft.Text("Remediated", size=12, color=C.TEXT2)], spacing=5),
                            ],
                            spacing=20,
                        ),
                        ft.Container(height=16),
                        alert_filter,
                        ft.Container(height=14),
                        ft.Container(
                            content=ft.Column(
                                [ft.Row([alerts_table], scroll=ft.ScrollMode.AUTO)],
                                scroll=ft.ScrollMode.AUTO,
                            ),
                            height=420,
                            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, C.RED)),
                            border_radius=8,
                            padding=8,
                            bgcolor=C.CARD,
                        ),
                    ],
                    spacing=0,
                ),
                padding=20,
                border=ft.Border.all(1, ft.Colors.with_opacity(0.2, C.RED)),
                border_radius=12,
                bgcolor=C.BG2,
            ),
        ],
        scroll=ft.ScrollMode.AUTO,
        spacing=0,
    )

    # -- Settings (admin) --
    settings_device_dd = ft.Dropdown(label="Device", width=300, options=[])
    settings_pm25 = ft.TextField(label="PM2.5 threshold", value="35")
    settings_co2 = ft.TextField(label="CO2 threshold", value="1000")

    sys_info_api = ft.Text("Checking...", size=12)
    sys_info_db = ft.Text("--", size=12)

    def load_settings_devices() -> None:
        ok, _ = check_api()
        sys_info_api.value = "Online" if ok else "Offline"
        try:
            resp = requests.get(f"{API_BASE_URL}/health", headers=headers(), timeout=5)
            if resp.status_code == 200:
                h = resp.json()
                db = h.get("database_size", h.get("db_size", "--"))
                sys_info_db.value = str(db)
        except Exception:  # noqa: BLE001
            pass
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
        page.update()

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

    settings_view = ft.Column(
        [
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.SETTINGS, color=C.ACCENT2),
                                ft.Text("Settings", size=16, weight=ft.FontWeight.BOLD, color=C.TEXT),
                            ],
                            spacing=8,
                        ),
                        ft.Container(height=14),
                        ft.Text("Threshold configuration", size=15, weight=ft.FontWeight.W_500, color=C.TEXT),
                        ft.Container(height=14),
                        settings_device_dd,
                        ft.Container(height=16),
                        settings_pm25,
                        ft.Container(height=16),
                        settings_co2,
                        ft.Container(height=20),
                        ft.FilledButton(
                            "Save thresholds",
                            icon=ft.Icons.SAVE,
                            on_click=save_thresholds,
                            style=ft.ButtonStyle(
                                bgcolor=C.ACCENT,
                                color="#000000",
                                text_style=ft.TextStyle(weight=ft.FontWeight.BOLD),
                            ),
                            width=220,
                        ),
                        ft.Container(height=20),
                        ft.Divider(color=ft.Colors.with_opacity(0.2, C.TEXT2)),
                        ft.Container(height=14),
                        ft.Text("System info", size=15, weight=ft.FontWeight.W_500, color=C.TEXT),
                        ft.Container(height=10),
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Row([ft.Text("API status:", size=12, color=C.TEXT2), sys_info_api]),
                                    ft.Row([ft.Text("Database size:", size=12, color=C.TEXT2), sys_info_db]),
                                    ft.Row([ft.Text("Application version:", size=12, color=C.TEXT2),
                                            ft.Text("1.0.0", size=12)]),
                                    ft.Row([ft.Text("Flet version:", size=12, color=C.TEXT2),
                                            ft.Text(ft.__version__, size=12)]),
                                ],
                                spacing=10,
                            ),
                            padding=14,
                            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, C.TEXT2)),
                            border_radius=8,
                            bgcolor=C.CARD,
                        ),
                    ],
                    spacing=0,
                ),
                padding=16,
                border=ft.Border.all(1, ft.Colors.with_opacity(0.2, C.TEXT2)),
                border_radius=12,
                bgcolor=C.BG2,
            ),
        ],
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    # -- Bottom sheet: quick add reading --
    bs_device = ft.Dropdown(label="Device", options=[])
    bs_pm25 = ft.TextField(label="PM2.5")
    bs_co2 = ft.TextField(label="CO2")

    def open_reading_sheet(e=None) -> None:
        bs_pm25.value = ""
        bs_co2.value = ""
        try:
            resp = requests.get(
                f"{API_BASE_URL}/devices",
                headers=headers(),
                params={"limit": 100, "offset": 0},
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
                show_snack("PM2.5 and CO2 must be numbers", success=False)
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
                content=ft.Column(
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
                ),
                padding=20,
                width=400,
            ),
            open=True,
        )
        page.show_dialog(sheet)

    # -- Shell --
    body = ft.Container(
        padding=ft.Padding.only(left=32, top=16, right=24, bottom=16),
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

    _nav_ref: list[ft.Container | None] = [None]
    _nav_items_data: list = []

    def build_nav():
        sel = session["tab"]
        items = []
        for nd in _nav_items_data:
            active = nd["idx"] == sel
            items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(
                                    nd["icon"],
                                    size=18,
                                    color="#0B1220" if active else C.TEXT2,
                                ),
                                width=34,
                                height=34,
                                border_radius=ft.BorderRadius.all(8),
                                bgcolor=C.ACCENT if active else ft.Colors.with_opacity(0.08, C.TEXT2),
                                alignment=ft.Alignment(0, 0),
                            ),
                            ft.Container(width=10),
                            ft.Text(
                                nd["label"],
                                size=14,
                                color=C.TEXT if active else C.TEXT2,
                                weight=ft.FontWeight.W_600 if active else ft.FontWeight.NORMAL,
                            ),
                            ft.Container(expand=True),
                            ft.Container(
                                width=4,
                                height=20,
                                border_radius=ft.BorderRadius.all(2),
                                bgcolor=C.ACCENT if active else ft.Colors.TRANSPARENT,
                            ),
                        ],
                        spacing=0,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=10),
                    border_radius=ft.BorderRadius.all(12),
                    margin=ft.Margin.symmetric(horizontal=10, vertical=3),
                    bgcolor=ft.Colors.with_opacity(0.12, C.ACCENT) if active else None,
                    on_click=lambda e, idx=nd["idx"]: on_nav_click(idx),
                    ink=True,
                )
            )
        return ft.Column(items, spacing=0)

    def on_nav_click(idx: int) -> None:
        session["tab"] = idx
        if is_admin():
            body.content = VIEWS[idx]
        else:
            body.content = VIEWS[idx if idx < 3 else 0]
        if idx == 0:
            load_dashboard()
        elif idx == 1:
            load_devices_table()
            add_device_form.visible = is_admin()
        elif idx == 2:
            load_alerts()
        elif idx == 3 and is_admin():
            load_settings_devices()
        nav = _nav_ref[0]
        if nav:
            nav.content.controls[3] = build_nav()
        page.update()

    def show_main_shell() -> None:
        page.controls.clear()
        page.appbar = None
        page.navigation_bar = None
        page.bottom_appbar = None
        add_device_form.visible = is_admin()

        _nav_items_data.clear()
        _nav_items_data.extend([
            {"icon": ft.Icons.DASHBOARD, "label": "Dashboard", "idx": 0},
            {"icon": ft.Icons.DEVICES, "label": "Devices", "idx": 1},
            {"icon": ft.Icons.WARNING_AMBER, "label": "Alerts", "idx": 2},
        ])
        if is_admin():
            _nav_items_data.append({"icon": ft.Icons.SETTINGS, "label": "Settings", "idx": 3})

        role_color = C.ACCENT if is_admin() else C.ACCENT2
        role_label = (session.get("role") or "user").upper()
        username_display = session.get("username") or "User"
        initials = username_display[:2].upper()

        nav_sidebar = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(
                                    content=ft.Icon(ft.Icons.AIR, color="#0B1220", size=22),
                                    width=40,
                                    height=40,
                                    border_radius=ft.BorderRadius.all(10),
                                    bgcolor=C.ACCENT,
                                    alignment=ft.Alignment(0, 0),
                                ),
                                ft.Container(width=10),
                                ft.Column(
                                    [
                                        ft.Text("AirQuality", size=14, weight=ft.FontWeight.BOLD, color=C.TEXT),
                                        ft.Text("Monitor", size=10, color=C.ACCENT, weight=ft.FontWeight.W_500),
                                    ],
                                    spacing=0,
                                ),
                            ],
                            spacing=0,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding.only(left=14, top=20, bottom=16, right=14),
                    ),
                    ft.Container(
                        height=1,
                        bgcolor=ft.Colors.with_opacity(0.15, C.TEXT2),
                        margin=ft.Margin.symmetric(horizontal=10, vertical=0),
                    ),
                    ft.Container(height=10),
                    build_nav(),
                    ft.Container(expand=True),
                    ft.Container(
                        height=1,
                        bgcolor=ft.Colors.with_opacity(0.15, C.TEXT2),
                        margin=ft.Margin.symmetric(horizontal=10, vertical=0),
                    ),
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(
                                    content=ft.Text(initials, size=12, weight=ft.FontWeight.BOLD, color="#0B1220"),
                                    width=32,
                                    height=32,
                                    border_radius=ft.BorderRadius.all(16),
                                    bgcolor=role_color,
                                    alignment=ft.Alignment(0, 0),
                                ),
                                ft.Container(width=8),
                                ft.Column(
                                    [
                                        ft.Text(username_display, size=12, weight=ft.FontWeight.W_600, color=C.TEXT),
                                        ft.Container(
                                            content=ft.Text(role_label, size=9, weight=ft.FontWeight.BOLD, color="#0B1220"),
                                            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                                            border_radius=ft.BorderRadius.all(4),
                                            bgcolor=role_color,
                                        ),
                                    ],
                                    spacing=3,
                                ),
                                ft.Container(expand=True),
                                ft.IconButton(
                                    icon=ft.Icons.LOGOUT,
                                    tooltip="Logout",
                                    icon_color=C.TEXT2,
                                    icon_size=18,
                                    on_click=do_logout,
                                ),
                            ],
                            spacing=0,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding.symmetric(horizontal=10, vertical=12),
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            width=220,
            bgcolor=C.NAV,
        )
        _nav_ref[0] = nav_sidebar

        top_bar = ft.Container(
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.AIR, color=C.ACCENT, size=22),
                            ft.Container(width=10),
                            ft.Column(
                                [
                                    ft.Text("FreshX", size=16, weight=ft.FontWeight.BOLD, color=C.ACCENT),
                                    ft.Text("Clean Air, Clear Mind", size=10, color=C.TEXT2),
                                ],
                                spacing=0,
                            ),
                        ],
                        spacing=0,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(expand=True),
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Icon(ft.Icons.CIRCLE, size=8, color=C.GREEN),
                                        ft.Container(width=4),
                                        ft.Text("Live", size=11, color=C.GREEN, weight=ft.FontWeight.W_600),
                                    ],
                                    spacing=0,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                                border_radius=ft.BorderRadius.all(20),
                                bgcolor=ft.Colors.with_opacity(0.12, C.GREEN),
                            ),
                            ft.Container(width=10),
                            ft.IconButton(
                                icon=ft.Icons.REFRESH_ROUNDED,
                                tooltip="Refresh",
                                icon_color=C.TEXT2,
                                icon_size=18,
                                on_click=lambda e: refresh_current_tab(),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.ADD_CHART_ROUNDED,
                                tooltip="Quick add reading",
                                icon_color=C.ACCENT,
                                icon_size=18,
                                on_click=open_reading_sheet,
                            ),
                        ],
                        spacing=0,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=20, vertical=12),
            bgcolor=C.BG2,
            border=ft.Border(bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.15, C.TEXT2))),
        )

        footer = ft.Container(
            content=ft.Row(
                [
                    ft.Text("2026 Team. All Rights Reserved.", size=11, color=ft.Colors.with_opacity(0.5, C.TEXT2)),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(vertical=10),
            bgcolor=C.FOOTER,
            border=ft.Border(top=ft.BorderSide(1, ft.Colors.with_opacity(0.2, C.TEXT2))),
        )

        body.content = dashboard_view
        session["tab"] = 0
        page.add(
            ft.Row(
                [
                    nav_sidebar,
                    ft.VerticalDivider(width=1, color=ft.Colors.with_opacity(0.2, C.TEXT2)),
                    ft.Column(
                        [top_bar, body, footer],
                        expand=True,
                        spacing=0,
                    ),
                ],
                expand=True,
                spacing=0,
            )
        )
        load_dashboard()
        session["dashboard_refresh"] = True
        page.run_task(dashboard_refresh_loop)

    # Start at login
    ok, _ = check_api()
    page.add(login_view)
    if not ok:
        show_snack("API not running - start uvicorn, then sign in", success=False)


if __name__ == "__main__":
    ft.run(main)
