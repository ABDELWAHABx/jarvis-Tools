"""Desktop control center UI surfaced from the system tray."""
from __future__ import annotations

import threading
import webbrowser
from datetime import datetime
from typing import Callable, Dict, List, Optional

import httpx

from app.runtime.documentation import get_service_details, render_documentation, render_request_overview
from app.runtime.log_buffer import log_buffer_handler

try:  # pragma: no cover - GUI imports are optional in headless CI
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover - gracefully degrade when Tk is missing
    tk = None  # type: ignore
    ttk = None  # type: ignore


class ControlCenterUI:
    """Encapsulate the Tkinter-based desktop UI."""

    COLORS = {
        "bg": "#0f172a",
        "panel": "#1e293b",
        "card": "#111827",
        "text": "#e2e8f0",
        "muted": "#94a3b8",
        "accent": "#38bdf8",
        "accent_hover": "#0ea5e9",
        "success": "#34d399",
        "warning": "#fbbf24",
        "error": "#f87171",
    }

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._base_url = f"http://{host}:{port}"
        self._thread: Optional[threading.Thread] = None
        self._root: Optional[tk.Tk] = None if tk else None
        self._cards_canvas: Optional[tk.Canvas] = None
        self._cards_frame: Optional[ttk.Frame] = None
        self._mini_text: Optional[tk.Text] = None
        self._log_text: Optional[tk.Text] = None
        self._health_label: Optional[tk.Label] = None
        self._health_time_label: Optional[tk.Label] = None
        self._health_status: Optional[str] = None
        self._copy_feedback_var: Optional[tk.StringVar] = None
        self._log_callback: Optional[Callable[[str], None]] = None
        self._doc_window: Optional[tk.Toplevel] = None
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

        root = tk.Tk()
        self._root = root
        root.title("Tools API Control Center")
        root.geometry("1000x720")
        root.configure(bg=self.COLORS["bg"])
        root.minsize(860, 640)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        style = ttk.Style()
        try:  # Some environments may not expose the clam theme
            style.theme_use("clam")
        except Exception:
            pass

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
        style.configure("Card.TFrame", background=colors["card"], relief="flat")
        style.configure("ServiceHeading.TLabel", background=colors["panel"], foreground=colors["text"], font=("Segoe UI", 14, "bold"))
        style.configure("CardTitle.TLabel", background=colors["card"], foreground=colors["accent"], font=("Segoe UI", 12, "bold"))
        style.configure("CardBody.TLabel", background=colors["card"], foreground=colors["text"], font=("Segoe UI", 10))
        style.configure("Header.TLabel", background=colors["bg"], foreground=colors["text"], font=("Segoe UI", 18, "bold"))
        style.configure("Subheader.TLabel", background=colors["bg"], foreground=colors["muted"], font=("Segoe UI", 10))
        style.configure("PanelLabel.TLabel", background=colors["panel"], foreground=colors["muted"], font=("Segoe UI", 10, "bold"))
        style.configure("Accent.TButton", background=colors["accent"], foreground=colors["bg"], padding=8)
        style.map(
            "Accent.TButton",
            background=[("active", colors["accent_hover"]), ("disabled", colors["panel"])],
            foreground=[("disabled", colors["muted"])],
        )
        style.configure("Secondary.TButton", background=colors["panel"], foreground=colors["text"], padding=8)
        style.map(
            "Secondary.TButton",
            background=[("active", colors["card"])],
            foreground=[("disabled", colors["muted"])],
        )
        style.configure("TNotebook", background=colors["panel"], borderwidth=0)
        style.configure("TNotebook.Tab", background=colors["panel"], foreground=colors["muted"], padding=(12, 6))
        style.map(
            "TNotebook.Tab",
            background=[("selected", colors["card"])],
            foreground=[("selected", colors["text"])],
        )

    def _build_layout(self, root: "tk.Tk") -> None:
        colors = self.COLORS
        container = ttk.Frame(root, style="Main.TFrame", padding=(24, 24, 24, 18))
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container, style="Main.TFrame")
        header.pack(fill="x")

        ttk.Label(header, text="Tools API Control Center", style="Header.TLabel").pack(anchor="w")
        ttk.Label(header, text=f"Base URL: {self._base_url}", style="Subheader.TLabel").pack(anchor="w", pady=(4, 0))

        health_row = ttk.Frame(header, style="Main.TFrame")
        health_row.pack(fill="x", pady=(12, 0))

        self._health_status = "Checking health..."
        self._health_label = tk.Label(health_row, text=self._health_status, bg=colors["bg"], fg=colors["muted"], font=("Segoe UI", 10))
        self._health_label.pack(side="left")

        self._health_time_label = tk.Label(health_row, text="", bg=colors["bg"], fg=colors["muted"], font=("Segoe UI", 10))
        self._health_time_label.pack(side="left", padx=(12, 0))

        ttk.Button(health_row, text="Refresh health", style="Accent.TButton", command=self._refresh_health).pack(side="right")

        button_row = ttk.Frame(container, style="Main.TFrame")
        button_row.pack(fill="x", pady=(20, 8))

        ttk.Button(button_row, text="Open API docs", style="Accent.TButton", command=self._open_docs).pack(side="left")
        ttk.Button(button_row, text="View endpoint catalog", style="Secondary.TButton", command=self._show_full_documentation).pack(side="left", padx=(12, 0))
        ttk.Button(button_row, text="Copy base URL", style="Secondary.TButton", command=self._copy_base_url).pack(side="left", padx=(12, 0))

        self._copy_feedback_var = tk.StringVar(value="")
        tk.Label(button_row, textvariable=self._copy_feedback_var, bg=colors["bg"], fg=colors["muted"], font=("Segoe UI", 9, "italic")).pack(side="left", padx=(12, 0))

        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True, pady=(8, 0))

        overview_tab = ttk.Frame(notebook, style="Panel.TFrame")
        logs_tab = ttk.Frame(notebook, style="Panel.TFrame")
        notebook.add(overview_tab, text="Overview")
        notebook.add(logs_tab, text="Logs")

        # Overview tab -------------------------------------------------
        cards_container = ttk.Frame(overview_tab, style="Panel.TFrame")
        cards_container.pack(fill="both", expand=True, padx=18, pady=(18, 12))

        canvas = tk.Canvas(cards_container, bg=colors["panel"], highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(cards_container, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)

        inner_frame = ttk.Frame(canvas, style="Panel.TFrame")
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
        canvas.bind("<Button-4>", lambda event: self._scroll_canvas(-1))  # Linux scroll up
        canvas.bind("<Button-5>", lambda event: self._scroll_canvas(1))   # Linux scroll down

        self._cards_canvas = canvas
        self._cards_frame = inner_frame

        mini_section = ttk.Frame(overview_tab, style="Panel.TFrame")
        mini_section.pack(fill="both", expand=False, padx=18, pady=(0, 18))
        ttk.Label(mini_section, text="Mini docs (same summary shown in the terminal)", style="PanelLabel.TLabel").pack(anchor="w", pady=(0, 6))

        self._mini_text = tk.Text(
            mini_section,
            height=10,
            wrap="word",
            bg=colors["card"],
            fg=colors["text"],
            insertbackground=colors["text"],
            relief="flat",
            bd=0,
            font=("Segoe UI", 10),
        )
        self._mini_text.pack(fill="both", expand=True)
        self._mini_text.configure(state="disabled")

        # Logs tab -----------------------------------------------------
        logs_header = ttk.Frame(logs_tab, style="Panel.TFrame")
        logs_header.pack(fill="x", padx=18, pady=(18, 0))
        ttk.Label(logs_header, text="Live server logs", style="PanelLabel.TLabel").pack(side="left")
        ttk.Button(logs_header, text="Clear", style="Secondary.TButton", command=self._clear_logs).pack(side="right")

        logs_area = ttk.Frame(logs_tab, style="Panel.TFrame")
        logs_area.pack(fill="both", expand=True, padx=18, pady=(12, 18))

        self._log_text = tk.Text(
            logs_area,
            wrap="none",
            bg=colors["card"],
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
            ttk.Label(
                self._cards_frame,
                text=service.get("name", "Service"),
                style="ServiceHeading.TLabel",
                anchor="w",
            ).pack(fill="x", pady=(0, 4))

            summary = service.get("summary")
            if summary:
                ttk.Label(
                    self._cards_frame,
                    text=summary,
                    style="CardBody.TLabel",
                    wraplength=760,
                    justify="left",
                ).pack(fill="x", pady=(0, 8))

            for endpoint in service.get("endpoints", []):
                card = ttk.Frame(self._cards_frame, style="Card.TFrame", padding=16)
                card.pack(fill="x", expand=True, pady=8)

                ttk.Label(card, text=endpoint["headline"], style="CardTitle.TLabel").pack(anchor="w")

                tagline = endpoint.get("tagline")
                if tagline:
                    ttk.Label(
                        card,
                        text=tagline,
                        style="CardBody.TLabel",
                        wraplength=720,
                        justify="left",
                    ).pack(anchor="w", pady=(4, 8))

                detail_lines = [f"Call with: {endpoint['method']} {endpoint['path']}"]
                content_type = endpoint.get("request", {}).get("content_type")
                if content_type:
                    detail_lines[-1] += f" ({content_type})"

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

                ttk.Label(
                    card,
                    text="\n".join(detail_lines),
                    style="CardBody.TLabel",
                    justify="left",
                    wraplength=760,
                ).pack(anchor="w")

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
        if self._root is None or self._copy_feedback_var is None:
            return
        try:
            self._root.clipboard_clear()
            self._root.clipboard_append(self._base_url)
            self._copy_feedback_var.set("Copied!")
            self._root.after(2000, lambda: self._copy_feedback_var.set(""))
        except Exception:
            self._copy_feedback_var.set("Clipboard unavailable")
            self._root.after(2500, lambda: self._copy_feedback_var.set(""))

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
        self._root = None
        self._thread = None
        self._cards_canvas = None
        self._cards_frame = None
        self._mini_text = None
        self._log_text = None
        self._doc_window = None
        self._copy_feedback_var = None
        self._health_label = None
        self._health_time_label = None


__all__ = ["ControlCenterUI"]
