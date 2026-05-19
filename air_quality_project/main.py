import flet as ft
import requests

from config import API_BASE_URL


def main(page: ft.Page):
    page.title = "Air Quality Monitor"
    page.padding = 0

    # ------------------------------------------------------------------ #
    # Snackbar helper (green = success, red = error)                      #
    # ------------------------------------------------------------------ #
    def show_snack(message: str, success: bool = True) -> None:
        page.show_dialog(
            ft.SnackBar(
                content=ft.Text(message, color=ft.Colors.WHITE),
                bgcolor=ft.Colors.GREEN if success else ft.Colors.RED,
            )
        )

    # ------------------------------------------------------------------ #
    # View 1: Records (DataTable + Refresh)                               #
    # ------------------------------------------------------------------ #
    status_text = ft.Text("")
    search_field = ft.TextField(
        label="Search",
        hint_text="Search by device, model, status, or room",
        prefix_icon=ft.Icons.SEARCH,
        expand=True,
    )
    table = ft.DataTable(
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

    def load_records(e=None) -> None:
        try:
            resp = requests.get(
                f"{API_BASE_URL}/devices",
                params={"search": (search_field.value or "").strip()},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            table.rows = [
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(d["id"]))),
                        ft.DataCell(ft.Text(d["device_id"])),
                        ft.DataCell(ft.Text(d["model"])),
                        ft.DataCell(ft.Text(d["status"])),
                        ft.DataCell(
                            ft.Text(d.get("room_name") or str(d["room_id"]))
                        ),
                        ft.DataCell(
                            ft.Row(
                                [
                                    ft.IconButton(
                                        icon=ft.Icons.EDIT,
                                        tooltip="Edit",
                                        on_click=make_edit(d),
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.DELETE,
                                        tooltip="Delete",
                                        icon_color=ft.Colors.RED,
                                        on_click=make_delete(d["id"]),
                                    ),
                                ],
                                spacing=0,
                            )
                        ),
                    ]
                )
                for d in data
            ]
            status_text.value = f"{len(data)} device(s) loaded"
        except Exception as ex:  # noqa: BLE001 - surface any failure to the UI
            table.rows = []
            status_text.value = "Could not reach the API"
            show_snack(f"Error loading records: {ex}", success=False)
        page.update()

    search_field.on_change = load_records

    records_view = ft.Column(
        [
            ft.Row(
                [
                    ft.Text("Device Records", size=22, weight=ft.FontWeight.BOLD),
                    ft.Button(
                        "Refresh", icon=ft.Icons.REFRESH, on_click=load_records
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            search_field,
            status_text,
            ft.Column([table], scroll=ft.ScrollMode.AUTO, expand=True),
        ],
        expand=True,
    )

    # ------------------------------------------------------------------ #
    # View 2: Add New (form + Submit + validation)                        #
    # ------------------------------------------------------------------ #
    f_device_id = ft.TextField(label="Device ID")
    f_model = ft.TextField(label="Model")
    f_status = ft.Dropdown(
        label="Status",
        options=[
            ft.dropdown.Option("online"),
            ft.dropdown.Option("offline"),
            ft.dropdown.Option("maintenance"),
        ],
    )
    f_room = ft.TextField(label="Room ID (1-5)")

    def build_payload(device_id_value, model_value, status_value, room_value):
        """Validate device form values and return a payload or an error."""
        if not (device_id_value or "").strip():
            return None, "Device ID is required"
        if not (model_value or "").strip():
            return None, "Model is required"
        if not status_value:
            return None, "Status is required"
        if not (room_value or "").strip():
            return None, "Room ID is required"
        try:
            room_id = int(room_value)
        except ValueError:
            return None, "Room ID must be a whole number"

        return {
            "device_id": device_id_value.strip(),
            "model": model_value.strip(),
            "status": status_value,
            "room_id": room_id,
        }, None

    def clear_form() -> None:
        f_device_id.value = ""
        f_model.value = ""
        f_status.value = None
        f_room.value = ""

    def submit(e) -> None:
        # ---- Frontend validation (before sending POST) ----
        payload, error = build_payload(
            f_device_id.value, f_model.value, f_status.value, f_room.value
        )
        if error:
            show_snack(error, success=False)
            return

        try:
            resp = requests.post(
                f"{API_BASE_URL}/devices", json=payload, timeout=5
            )
        except Exception as ex:  # noqa: BLE001
            show_snack(f"Request failed: {ex}", success=False)
            return

        if resp.status_code in (200, 201):
            show_snack("Device added successfully")
            clear_form()
            # Navigate back to Records and refresh the table.
            nav.selected_index = 0
            set_view(0)
            load_records()
        else:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:  # noqa: BLE001
                detail = resp.text
            show_snack(f"Error: {detail}", success=False)
            page.update()

    def make_edit(device):
        def edit_device(e) -> None:
            edit_device_id = ft.TextField(label="Device ID", value=device["device_id"])
            edit_model = ft.TextField(label="Model", value=device["model"])
            edit_status = ft.Dropdown(
                label="Status",
                value=device["status"],
                options=[
                    ft.dropdown.Option("online"),
                    ft.dropdown.Option("offline"),
                    ft.dropdown.Option("maintenance"),
                ],
            )
            edit_room = ft.TextField(label="Room ID", value=str(device["room_id"]))

            def close_dialog(e=None) -> None:
                dialog.open = False
                dialog.update()

            def save_changes(e) -> None:
                payload, error = build_payload(
                    edit_device_id.value,
                    edit_model.value,
                    edit_status.value,
                    edit_room.value,
                )
                if error:
                    show_snack(error, success=False)
                    return

                try:
                    resp = requests.put(
                        f"{API_BASE_URL}/devices/{device['id']}",
                        json=payload,
                        timeout=5,
                    )
                except Exception as ex:  # noqa: BLE001
                    show_snack(f"Request failed: {ex}", success=False)
                    return

                if resp.status_code == 200:
                    close_dialog()
                    show_snack("Device updated successfully")
                    load_records()
                else:
                    try:
                        detail = resp.json().get("detail", resp.text)
                    except Exception:  # noqa: BLE001
                        detail = resp.text
                    show_snack(f"Error: {detail}", success=False)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Edit Device"),
                content=ft.Column(
                    [edit_device_id, edit_model, edit_status, edit_room],
                    tight=True,
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=close_dialog),
                    ft.TextButton("Save", on_click=save_changes),
                ],
            )
            page.show_dialog(dialog)

        return edit_device

    def make_delete(device_id):
        def delete_device(e) -> None:
            def close_dialog(e=None) -> None:
                dialog.open = False
                dialog.update()

            def confirm_delete(e) -> None:
                try:
                    resp = requests.delete(
                        f"{API_BASE_URL}/devices/{device_id}", timeout=5
                    )
                except Exception as ex:  # noqa: BLE001
                    show_snack(f"Request failed: {ex}", success=False)
                    return

                close_dialog()
                if resp.status_code == 200:
                    show_snack("Device deleted successfully")
                    load_records()
                else:
                    try:
                        detail = resp.json().get("detail", resp.text)
                    except Exception:  # noqa: BLE001
                        detail = resp.text
                    show_snack(f"Error: {detail}", success=False)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Delete Device"),
                content=ft.Text("Are you sure you want to delete this device?"),
                actions=[
                    ft.TextButton("Cancel", on_click=close_dialog),
                    ft.TextButton("Delete", on_click=confirm_delete),
                ],
            )
            page.show_dialog(dialog)

        return delete_device

    add_view = ft.Column(
        [
            ft.Text("Add New Device", size=22, weight=ft.FontWeight.BOLD),
            f_device_id,
            f_model,
            f_status,
            f_room,
            ft.Button("Submit", icon=ft.Icons.SAVE, on_click=submit),
        ],
        spacing=15,
        expand=True,
    )

    # ------------------------------------------------------------------ #
    # Navigation between the two views                                    #
    # ------------------------------------------------------------------ #
    body = ft.Container(content=records_view, padding=20, expand=True)

    def set_view(index: int) -> None:
        body.content = records_view if index == 0 else add_view
        page.update()

    def on_nav_change(e) -> None:
        index = e.control.selected_index
        set_view(index)
        if index == 0:
            load_records()

    nav = ft.NavigationBar(
        selected_index=0,
        destinations=[
            ft.NavigationBarDestination(
                icon=ft.Icons.LIST_ALT, label="Records"
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.ADD_CIRCLE, label="Add New"
            ),
        ],
        on_change=on_nav_change,
    )

    page.navigation_bar = nav
    page.add(body)
    load_records()


if __name__ == "__main__":
    ft.run(main)
