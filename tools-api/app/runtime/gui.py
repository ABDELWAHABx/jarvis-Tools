"""Desktop control center UI surfaced from the system tray."""
from __future__ import annotations

import json
import threading
import webbrowser
from datetime import datetime
from typing import Callable, Dict, List, Optional

import httpx

from app.runtime.documentation import get_service_details, render_documentation, render_request_overview
from app.runtime.log_buffer import log_buffer_handler

try:  # pragma: no cover - GUI imports are optional in headless CI
    import tkinter as tk
    from tkinter import ttk as _ttk
except Exception:  # pragma: no cover - gracefully degrade when Tk is missing
    tk = None  # type: ignore
    _ttk = None  # type: ignore

try:  # pragma: no cover - optional modern theming
    import ttkbootstrap as ttkb
    from ttkbootstrap import Window
    from ttkbootstrap.scrolled import ScrolledFrame
except Exception:  # pragma: no cover - fall back to stock Tk widgets
    ttkb = None  # type: ignore
    Window = None  # type: ignore
    ScrolledFrame = None  # type: ignore

if ttkb is not None:
    ttk = ttkb.ttk  # type: ignore[assignment]
else:
    ttk = _ttk


class ControlCenterUI:
    """Encapsulate the Tkinter-based desktop UI."""

    COLORS = {
        "bg": "#030712",
        "panel": "#0f172a",
        "hero": "#111c34",
        "card": "#15223b",
        "card_border": "#1e2b4f",
        "mini_bg": "#111827",
        "log_bg": "#0b1220",
        "text": "#f8fafc",
        "muted": "#94a3b8",
        "accent": "#38bdf8",
        "accent_hover": "#0ea5e9",
        "success": "#34d399",
        "warning": "#fbbf24",
        "error": "#f87171",
        "badge": "#2563eb",
        "badge_text": "#e2e8f0",
        "toast_bg": "#1e293b",
        "toast_success": "#22c55e",
        "toast_warning": "#f59e0b",
        "toast_error": "#ef4444",
    }

    METHOD_COLORS = {
        "GET": "#10b981",
        "POST": "#2563eb",
        "PUT": "#f59e0b",
        "PATCH": "#6366f1",
        "DELETE": "#ef4444",
    }

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._base_url = f"http://{host}:{port}"
        self._thread: Optional[threading.Thread] = None
        self._root: Optional[tk.Tk] = None if tk else None
        self._cards_canvas: Optional[tk.Canvas] = None
        self._cards_frame: Optional[ttk.Frame] = None
        self._cards_scroller: Optional[ScrolledFrame] = None
        self._mini_text: Optional[tk.Text] = None
        self._log_text: Optional[tk.Text] = None
        self._health_label: Optional[tk.Label] = None
        self._health_time_label: Optional[tk.Label] = None
        self._health_status: Optional[str] = None
        self._toast_var: Optional[tk.StringVar] = None
        self._toast_label: Optional[ttk.Label] = None
        self._toast_container: Optional[ttk.Frame] = None
        self._toast_after: Optional[str] = None
        self._log_callback: Optional[Callable[[str], None]] = None
        self._doc_window: Optional[tk.Toplevel] = None
        self._use_bootstrap = ttkb is not None and Window is not None and ttk is not None and tk is not None
        self._supported = tk is not None and ttk is not None

    # ------------------------------------------------------------------
    def is_supported(self) -> bool:
        return self._supported

    def show(self) -> None:
        """Display the UI, creating the window if necessary."""

        if not self._supported:
            print("Desktop UI not available: Tkinter is missing or unsupported in this environment.")
            return

        if self._root is not None and bool(self._root.winfo_exists()):
            self._focus_window()
            return

        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(target=self._run_mainloop, name="tools-ui", daemon=True)
        self._thread.start()

    def close(self) -> None:
        if self._root is None:
            return
        try:
            self._root.after(0, self._root.destroy)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _run_mainloop(self) -> None:
        if tk is None or ttk is None:
            return

        if self._use_bootstrap and Window is not None:
            root = Window(themename="darkly")  # type: ignore[call-arg]
            style = getattr(root, "style", ttk.Style())  # type: ignore[assignment]
        else:
            root = tk.Tk()
            style = ttk.Style()
            try:  # Some environments may not expose the clam theme
                style.theme_use("clam")
            except Exception:
                pass

        self._root = root
        if tk is not None:
            try:
                self._toast_var = tk.StringVar(master=root, value="")
            except Exception:
                self._toast_var = None
        root.title("Tools API Control Center")
        root.geometry("1100x760")
        try:
            root.configure(bg=self.COLORS["bg"])
        except Exception:
            pass
        root.minsize(900, 680)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._configure_styles(style)
        self._build_layout(root)
        self._refresh_health()
        self._populate_service_cards()
        self._populate_mini_docs()
        self._start_log_stream()

        try:
            root.mainloop()
        finally:
            self._teardown()

    def _configure_styles(self, style: "ttk.Style") -> None:
        colors = self.COLORS
        style.configure("Main.TFrame", background=colors["bg"])
        style.configure("Panel.TFrame", background=colors["panel"])
        style.configure("Hero.TFrame", background=colors["hero"])
        style.configure("ServiceHeading.TLabel", background=colors["panel"], foreground=colors["text"], font=("Segoe UI", 15, "bold"))
        style.configure("HeroTitle.TLabel", background=colors["hero"], foreground=colors["text"], font=("Segoe UI", 20, "bold"))
        style.configure("HeroSub.TLabel", background=colors["hero"], foreground=colors["muted"], font=("Segoe UI", 11))
        style.configure("HeroLabel.TLabel", background=colors["hero"], foreground=colors["muted"], font=("Segoe UI", 10, "bold"))
        style.configure("ToastInfo.TLabel", background=colors["toast_bg"], foreground=colors["muted"], font=("Segoe UI", 10))
        style.configure("ToastSuccess.TLabel", background=colors["toast_bg"], foreground=colors["toast_success"], font=("Segoe UI", 10, "bold"))
        style.configure("ToastWarning.TLabel", background=colors["toast_bg"], foreground=colors["toast_warning"], font=("Segoe UI", 10, "bold"))
        style.configure("ToastError.TLabel", background=colors["toast_bg"], foreground=colors["toast_error"], font=("Segoe UI", 10, "bold"))
        style.configure("CardContainer.TFrame", background=colors["panel"])
        style.configure("Card.TFrame", background=colors["card"], relief="ridge", borderwidth=1)
        style.configure("CardTitle.TLabel", background=colors["card"], foreground=colors["accent"], font=("Segoe UI", 13, "bold"))
        style.configure("CardBody.TLabel", background=colors["card"], foreground=colors["text"], font=("Segoe UI", 10))
        style.configure("Method.TLabel", background=colors["card"], foreground=colors["muted"], font=("Segoe UI", 10, "bold"))
        style.configure("Path.TLabel", background=colors["card"], foreground=colors["text"], font=("Segoe UI", 10))
        style.configure("Header.TLabel", background=colors["bg"], foreground=colors["text"], font=("Segoe UI", 18, "bold"))
        style.configure("Subheader.TLabel", background=colors["bg"], foreground=colors["muted"], font=("Segoe UI", 10))
        style.configure("PanelLabel.TLabel", background=colors["panel"], foreground=colors["muted"], font=("Segoe UI", 10, "bold"))
        style.configure("Accent.TButton", background=colors["accent"], foreground=colors["bg"], padding=9)
        style.map(
            "Accent.TButton",
            background=[("active", colors["accent_hover"]), ("disabled", colors["panel"])],
            foreground=[("disabled", colors["muted"])],
        )
        style.configure("Secondary.TButton", background=colors["panel"], foreground=colors["text"], padding=9)
        style.map(
            "Secondary.TButton",
            background=[("active", colors["card"])],
            foreground=[("disabled", colors["muted"])],
        )
        style.configure("CardAction.TButton", background=colors["panel"], foreground=colors["text"], padding=7)
        style.configure("TNotebook", background=colors["panel"], borderwidth=0)
        style.configure("TNotebook.Tab", background=colors["panel"], foreground=colors["muted"], padding=(14, 8))
        style.map(
            "TNotebook.Tab",
            background=[("selected", colors["card"])],
            foreground=[("selected", colors["text"])],
        )

    def _build_layout(self, root: "tk.Tk") -> None:
        colors = self.COLORS
        container = ttk.Frame(root, style="Main.TFrame", padding=(28, 28, 28, 20))
        container.pack(fill="both", expand=True)

        hero = ttk.Frame(container, style="Hero.TFrame", padding=(28, 28, 28, 22))
        hero.pack(fill="x", pady=(0, 20))

        ttk.Label(hero, text="Tools API Control Center", style="HeroTitle.TLabel").pack(anchor="w")
        ttk.Label(hero, text=f"Base URL: {self._base_url}", style="HeroSub.TLabel").pack(anchor="w", pady=(6, 0))

        health_row = ttk.Frame(hero, style="Hero.TFrame")
        health_row.pack(fill="x", pady=(18, 0))

        self._health_status = "Checking health..."
        self._health_label = tk.Label(
            health_row,
            text=self._health_status,
            bg=colors["hero"],
            fg=colors["muted"],
            font=("Segoe UI", 11, "bold"),
        )
        self._health_label.pack(side="left")

        self._health_time_label = tk.Label(
            health_row,
            text="",
            bg=colors["hero"],
            fg=colors["muted"],
            font=("Segoe UI", 10),
        )
        self._health_time_label.pack(side="left", padx=(12, 0))

        self._create_button(health_row, "Refresh health", self._refresh_health, primary=True).pack(side="right")

        action_row = ttk.Frame(hero, style="Hero.TFrame")
        action_row.pack(fill="x", pady=(18, 0))

        self._create_button(action_row, "Open API docs", self._open_docs, primary=True).pack(side="left")
        self._create_button(action_row, "View endpoint catalog", self._show_full_documentation).pack(side="left", padx=(12, 0))
        self._create_button(action_row, "Copy base URL", self._copy_base_url).pack(side="left", padx=(12, 0))

        if self._toast_var is not None:
            self._toast_container = ttk.Frame(hero, style="Hero.TFrame")
            self._toast_label = ttk.Label(
                self._toast_container,
                textvariable=self._toast_var,
                style="ToastInfo.TLabel",
                padding=(18, 10),
                anchor="w",
            )
            self._toast_label.pack(fill="x")
            self._toast_container.pack(fill="x", pady=(18, 0))
            self._toast_container.pack_forget()

        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True)

        overview_tab = ttk.Frame(notebook, style="Panel.TFrame")
        logs_tab = ttk.Frame(notebook, style="Panel.TFrame")
        notebook.add(overview_tab, text="Overview")
        notebook.add(logs_tab, text="Logs")

        overview_body = ttk.Frame(overview_tab, style="Panel.TFrame")
        overview_body.pack(fill="both", expand=True)

        cards_section = ttk.Frame(overview_body, style="Panel.TFrame")
        cards_section.pack(fill="both", expand=True, padx=20, pady=(20, 14))

        if self._use_bootstrap and ScrolledFrame is not None:
            scroller = ScrolledFrame(cards_section, autohide=True)
            scroller.pack(fill="both", expand=True)
            self._cards_scroller = scroller
            cards_parent = ttk.Frame(scroller.scrollable_frame, style="CardContainer.TFrame")
            cards_parent.pack(fill="both", expand=True)
            self._cards_frame = cards_parent
            self._cards_canvas = None
        else:
            canvas = tk.Canvas(cards_section, bg=colors["panel"], highlightthickness=0)
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar = ttk.Scrollbar(cards_section, orient="vertical", command=canvas.yview)
            scrollbar.pack(side="right", fill="y")
            canvas.configure(yscrollcommand=scrollbar.set)

            inner_frame = ttk.Frame(canvas, style="CardContainer.TFrame")
            window_id = canvas.create_window((0, 0), window=inner_frame, anchor="nw")
            inner_frame.bind(
                "<Configure>",
                lambda event: canvas.configure(scrollregion=canvas.bbox("all")),
            )
            canvas.bind(
                "<Configure>",
                lambda event: canvas.itemconfigure(window_id, width=event.width),
            )
            canvas.bind("<MouseWheel>", self._on_mousewheel)
            canvas.bind("<Button-4>", lambda event: self._scroll_canvas(-1))
            canvas.bind("<Button-5>", lambda event: self._scroll_canvas(1))

            self._cards_canvas = canvas
            self._cards_frame = inner_frame
            self._cards_scroller = None

        mini_section = ttk.Frame(overview_body, style="Panel.TFrame")
        mini_section.pack(fill="both", expand=False, padx=20, pady=(0, 20))
        ttk.Label(mini_section, text="Mini docs (same summary shown in the terminal)", style="PanelLabel.TLabel").pack(anchor="w", pady=(0, 8))

        self._mini_text = tk.Text(
            mini_section,
            height=12,
            wrap="word",
            bg=colors["mini_bg"],
            fg=colors["text"],
            insertbackground=colors["text"],
            relief="flat",
            bd=0,
            font=("Segoe UI", 10),
        )
        self._mini_text.pack(fill="both", expand=True)
        self._mini_text.configure(state="disabled")

        logs_wrapper = ttk.Frame(logs_tab, style="Panel.TFrame")
        logs_wrapper.pack(fill="both", expand=True, padx=20, pady=20)

        logs_header = ttk.Frame(logs_wrapper, style="Panel.TFrame")
        logs_header.pack(fill="x")
        ttk.Label(logs_header, text="Live server logs", style="PanelLabel.TLabel").pack(side="left")
        self._create_button(logs_header, "Clear", self._clear_logs).pack(side="right")

        logs_area = ttk.Frame(logs_wrapper, style="Panel.TFrame")
        logs_area.pack(fill="both", expand=True, pady=(14, 0))

        self._log_text = tk.Text(
            logs_area,
            wrap="none",
            bg=colors["log_bg"],
            fg=colors["text"],
            insertbackground=colors["text"],
            relief="flat",
            bd=0,
            font=("Cascadia Mono", 10),
        )
        self._log_text.pack(side="left", fill="both", expand=True)
        log_scroll = ttk.Scrollbar(logs_area, orient="vertical", command=self._log_text.yview)
        log_scroll.pack(side="right", fill="y")
        self._log_text.configure(yscrollcommand=log_scroll.set, state="disabled")

    # ------------------------------------------------------------------
    def _create_button(self, parent: "tk.Widget", text: str, command: Callable[[], None], *, primary: bool = False, subtle: bool = False) -> "ttk.Button":
        if ttk is None:
            raise RuntimeError("Tkinter ttk is unavailable")

        kwargs: Dict[str, object] = {"text": text, "command": command}
        if self._use_bootstrap:
            if subtle:
                kwargs["bootstyle"] = "INFO-OUTLINE"
            elif primary:
                kwargs["bootstyle"] = "PRIMARY"
            else:
                kwargs["bootstyle"] = "SECONDARY"
        else:
            if subtle:
                kwargs["style"] = "CardAction.TButton"
            elif primary:
                kwargs["style"] = "Accent.TButton"
            else:
                kwargs["style"] = "Secondary.TButton"
        return ttk.Button(parent, **kwargs)  # type: ignore[arg-type]

    def _show_toast(self, message: str, level: str = "info") -> None:
        if self._toast_var is None or self._toast_label is None or self._toast_container is None or self._root is None:
            return

        style_map = {
            "info": "ToastInfo.TLabel",
            "success": "ToastSuccess.TLabel",
            "warning": "ToastWarning.TLabel",
            "error": "ToastError.TLabel",
        }
        style_name = style_map.get(level.lower(), "ToastInfo.TLabel")
        try:
            self._toast_label.configure(style=style_name)
        except Exception:
            pass

        self._toast_var.set(message)
        self._toast_container.pack(fill="x", pady=(18, 0))

        if self._toast_after and self._root is not None:
            try:
                self._root.after_cancel(self._toast_after)
            except Exception:
                pass
        self._toast_after = self._root.after(4000, self._hide_toast)

    def _hide_toast(self) -> None:
        if self._toast_container is not None:
            self._toast_container.pack_forget()
        if self._toast_var is not None:
            self._toast_var.set("")
        self._toast_after = None

    def _copy_to_clipboard(self, text: str, success_message: str, *, level: str = "success") -> None:
        if self._root is None:
            return
        try:
            self._root.clipboard_clear()
            self._root.clipboard_append(text)
            self._show_toast(success_message, level=level)
        except Exception:
            self._show_toast("Clipboard unavailable", level="error")

    def _method_bootstyle(self, method: str) -> str:
        method_upper = method.upper()
        mapping = {
            "GET": "SUCCESS",
            "POST": "PRIMARY",
            "PUT": "WARNING",
            "PATCH": "INFO",
            "DELETE": "DANGER",
        }
        return mapping.get(method_upper, "SECONDARY")

    def _create_method_badge(self, parent: "tk.Widget", method: str):  # pragma: no cover - UI helper
        method_upper = method.upper()
        if self._use_bootstrap:
            bootstyle = f"{self._method_bootstyle(method_upper)}-INVERSE"
            return ttk.Label(parent, text=method_upper, bootstyle=bootstyle, padding=(12, 4))  # type: ignore[arg-type]

        color = self.METHOD_COLORS.get(method_upper, self.COLORS["badge"])
        return tk.Label(
            parent,
            text=method_upper,
            bg=color,
            fg=self.COLORS["badge_text"],
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=2,
        )

    def _copy_curl_command(self, endpoint: Dict[str, Any]) -> None:
        curl = self._build_curl_command(endpoint)
        if not curl:
            self._show_toast("Unable to build cURL for this endpoint.", level="warning")
            return
        method = endpoint.get("method", "GET").upper()
        path = endpoint.get("path", "/")
        self._copy_to_clipboard(curl, f"Copied cURL for {method} {path}")

    def _build_curl_command(self, endpoint: Dict[str, Any]) -> str:
        method = str(endpoint.get("method", "GET")).upper()
        path = str(endpoint.get("path", "/"))
        url = f"{self._base_url}{path}"

        components: List[str] = [f"curl -X {method} \"{url}\""]
        req = endpoint.get("request", {}) if isinstance(endpoint.get("request"), dict) else {}
        content_type = req.get("content_type")
        if content_type:
            components.append(f"  -H \"Content-Type: {content_type}\"")

        payload: Optional[Dict[str, object]] = None
        example = req.get("example")
        if isinstance(example, dict):
            payload = example
        else:
            fields = req.get("fields")
            if isinstance(fields, dict) and method not in {"GET", "DELETE"}:
                payload = {name: f"<{name}>" for name in fields.keys()}

        if payload and method not in {"GET", "DELETE"}:
            json_payload = json.dumps(payload, indent=2)
            components.append(f"  -d '{json_payload}'")

        return " \\\n".join(components)

    def _on_mousewheel(self, event: "tk.Event") -> None:  # pragma: no cover - UI interaction
        if not self._cards_canvas:
            return
        delta = 0
        if hasattr(event, "delta") and event.delta:
            delta = int(-event.delta / 120)
        elif getattr(event, "num", None) in (4, 5):
            delta = -1 if event.num == 4 else 1
        if delta:
            self._cards_canvas.yview_scroll(delta, "units")

    def _scroll_canvas(self, delta: int) -> None:  # pragma: no cover - UI interaction helper
        if self._cards_canvas:
            self._cards_canvas.yview_scroll(delta, "units")

    def _focus_window(self) -> None:
        if self._root is None:
            return
        try:
            self._root.deiconify()
            self._root.lift()
            self._root.focus_force()
        except Exception:
            pass

    def _populate_service_cards(self) -> None:
        if self._cards_frame is None:
            return

        for child in self._cards_frame.winfo_children():
            child.destroy()

        services, error = get_service_details()
        if error:
            ttk.Label(
                self._cards_frame,
                text=error,
                style="CardBody.TLabel",
                wraplength=720,
                justify="left",
            ).pack(fill="x", pady=12)
            return

        for service in services:
            section = ttk.Frame(self._cards_frame, style="CardContainer.TFrame")
            section.pack(fill="x", expand=True, pady=(0, 16))

            ttk.Label(
                section,
                text=service.get("name", "Service"),
                style="ServiceHeading.TLabel",
                anchor="w",
            ).pack(fill="x")

            summary = service.get("summary")
            if summary:
                ttk.Label(
                    section,
                    text=summary,
                    style="CardBody.TLabel",
                    wraplength=780,
                    justify="left",
                ).pack(fill="x", pady=(4, 10))

            for endpoint in service.get("endpoints", []):
                card = ttk.Frame(section, style="Card.TFrame", padding=20)
                card.pack(fill="x", expand=True, pady=12)

                ttk.Label(card, text=endpoint["headline"], style="CardTitle.TLabel").pack(anchor="w")

                meta_row = ttk.Frame(card, style="Card.TFrame")
                meta_row.pack(fill="x", pady=(6, 10))
                badge = self._create_method_badge(meta_row, endpoint.get("method", "GET"))
                if badge:
                    badge.pack(side="left")
                ttk.Label(meta_row, text=endpoint.get("path", "/"), style="Path.TLabel").pack(side="left", padx=(12, 0))
                content_type = endpoint.get("request", {}).get("content_type")
                if content_type:
                    ttk.Label(meta_row, text=content_type, style="Method.TLabel").pack(side="left", padx=(16, 0))

                tagline = endpoint.get("tagline")
                if tagline:
                    ttk.Label(
                        card,
                        text=tagline,
                        style="CardBody.TLabel",
                        wraplength=760,
                        justify="left",
                    ).pack(anchor="w", pady=(0, 8))

                detail_lines: List[str] = []

                request_fields = self._format_fields(endpoint.get("request", {}).get("fields"))
                if request_fields:
                    detail_lines.append("Send:")
                    detail_lines.extend([f"  • {field}" for field in request_fields])
                else:
                    detail_lines.append("Send: No request body documented.")

                response_fields = self._format_fields(endpoint.get("response", {}).get("fields"))
                if response_fields:
                    detail_lines.append("Receive:")
                    detail_lines.extend([f"  • {field}" for field in response_fields])
                else:
                    detail_lines.append("Receive: No structured response documented.")

                for note in endpoint.get("notes", []):
                    detail_lines.append(f"Note: {note}")

                ttk.Label(
                    card,
                    text="\n".join(detail_lines),
                    style="CardBody.TLabel",
                    justify="left",
                    wraplength=760,
                ).pack(anchor="w")

                action_row = ttk.Frame(card, style="Card.TFrame")
                action_row.pack(fill="x", pady=(16, 0))
                self._create_button(action_row, "Copy cURL", lambda ep=endpoint: self._copy_curl_command(ep), primary=True).pack(side="left")
                ttk.Label(
                    action_row,
                    text="Command includes the base URL and example payload when available.",
                    style="CardBody.TLabel",
                    wraplength=520,
                    justify="left",
                ).pack(side="left", padx=(16, 0))

    def _populate_mini_docs(self) -> None:
        if not self._mini_text:
            return
        text = render_request_overview(self._host, self._port).strip("\n")
        self._mini_text.configure(state="normal")
        self._mini_text.delete("1.0", tk.END)
        self._mini_text.insert("1.0", text)
        self._mini_text.configure(state="disabled")

    def _start_log_stream(self) -> None:
        if self._log_text is None:
            return

        for line in log_buffer_handler.snapshot():
            self._append_log(line)

        def push(line: str) -> None:
            self._schedule(lambda: self._append_log(line))

        self._log_callback = push
        log_buffer_handler.subscribe(push)

    def _append_log(self, line: str) -> None:
        if self._log_text is None:
            return
        self._log_text.configure(state="normal")
        self._log_text.insert(tk.END, line + "\n")
        self._log_text.see(tk.END)
        self._log_text.configure(state="disabled")

    def _clear_logs(self) -> None:
        if self._log_text is None:
            return
        log_buffer_handler.clear()
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", tk.END)
        self._log_text.configure(state="disabled")

    def _refresh_health(self) -> None:
        if not self._supported:
            return

        def worker() -> None:
            url = f"{self._base_url}/health"
            status_text = "Checking health..."
            color = self.COLORS["muted"]
            try:
                response = httpx.get(url, timeout=3.0)
                if response.status_code == 200:
                    payload = response.json()
                    status_value = str(payload.get("status", "unknown")).lower()
                    if status_value == "ok":
                        color = self.COLORS["success"]
                        status_text = "Healthy — status OK"
                    else:
                        color = self.COLORS["warning"]
                        status_text = f"Status: {status_value}"
                    details = f"{payload.get('service', 'Tools API')} {payload.get('version', '')}".strip()
                    if details:
                        status_text += f" ({details})"
                else:
                    color = self.COLORS["error"]
                    status_text = f"HTTP {response.status_code}"
            except Exception as exc:
                color = self.COLORS["error"]
                status_text = f"Unavailable ({exc.__class__.__name__})"

            checked_at = datetime.now().strftime("%H:%M:%S")
            self._schedule(lambda: self._update_health_display(status_text, color, checked_at))

        threading.Thread(target=worker, name="health-check", daemon=True).start()

    def _update_health_display(self, message: str, color: str, timestamp: str) -> None:
        if self._health_label is None or self._health_time_label is None:
            return
        self._health_label.configure(text=message, fg=color)
        self._health_time_label.configure(text=f"Checked at {timestamp}")

    def _open_docs(self) -> None:
        webbrowser.open(f"{self._base_url}/docs")

    def _show_full_documentation(self) -> None:
        if self._root is None or tk is None:
            return
        if self._doc_window is not None and bool(self._doc_window.winfo_exists()):
            self._doc_window.lift()
            self._doc_window.focus_force()
            return

        doc_window = tk.Toplevel(self._root)
        doc_window.title("Tools API endpoint catalog")
        doc_window.configure(bg=self.COLORS["panel"])
        doc_window.geometry("720x640")

        text_widget = tk.Text(
            doc_window,
            wrap="word",
            bg=self.COLORS["card"],
            fg=self.COLORS["text"],
            insertbackground=self.COLORS["text"],
            relief="flat",
            bd=0,
            font=("Segoe UI", 10),
        )
        text_widget.pack(fill="both", expand=True, padx=18, pady=18)
        text_widget.insert("1.0", render_documentation())
        text_widget.configure(state="disabled")

        scrollbar = ttk.Scrollbar(doc_window, orient="vertical", command=text_widget.yview)
        scrollbar.place(relx=1.0, rely=0.0, relheight=1.0, anchor="ne")
        text_widget.configure(yscrollcommand=scrollbar.set)

        def on_close() -> None:
            if self._doc_window is not None:
                self._doc_window = None
            doc_window.destroy()

        doc_window.protocol("WM_DELETE_WINDOW", on_close)
        self._doc_window = doc_window

    def _copy_base_url(self) -> None:
        if self._root is None:
            return
        self._copy_to_clipboard(self._base_url, "Copied base URL to clipboard.")

    def _schedule(self, callback: Callable[[], None]) -> None:
        if self._root is None:
            return
        try:
            self._root.after(0, callback)
        except Exception:
            pass

    def _format_fields(self, fields: Optional[Dict[str, str]]) -> List[str]:
        if not isinstance(fields, dict):
            return []
        entries = []
        for name, description in fields.items():
            text = str(description).strip()
            if not text.endswith(('.', '!', '?')):
                text += '.'
            entries.append(f"{name}: {text}")
        return entries

    def _on_close(self) -> None:
        if self._root is None:
            return
        self._root.destroy()

    def _teardown(self) -> None:
        if self._log_callback is not None:
            log_buffer_handler.unsubscribe(self._log_callback)
            self._log_callback = None
        if self._root is not None and self._toast_after:
            try:
                self._root.after_cancel(self._toast_after)
            except Exception:
                pass
        self._toast_after = None
        if self._toast_var is not None:
            self._toast_var.set("")
        self._toast_var = None
        self._toast_label = None
        self._toast_container = None
        self._root = None
        self._thread = None
        self._cards_canvas = None
        self._cards_frame = None
        self._cards_scroller = None
        self._mini_text = None
        self._log_text = None
        self._doc_window = None
        self._health_label = None
        self._health_time_label = None


__all__ = ["ControlCenterUI"]
