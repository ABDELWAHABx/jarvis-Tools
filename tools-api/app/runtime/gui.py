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
    """Encapsulate the Tkinter-based desktop UI with modern aesthetics."""

    # Modern color palette with vibrant accents and depth
    COLORS = {
        "bg": "#0a0e1a",
        "panel": "#111827",
        "hero": "#1a1f35",
        "card": "#1e293b",
        "card_hover": "#273449",
        "card_border": "#334155",
        "mini_bg": "#0f1419",
        "log_bg": "#050810",
        "text": "#f1f5f9",
        "muted": "#94a3b8",
        "dim": "#64748b",
        "accent": "#3b82f6",
        "accent_hover": "#2563eb",
        "accent_glow": "#60a5fa",
        "success": "#10b981",
        "success_glow": "#34d399",
        "warning": "#f59e0b",
        "error": "#ef4444",
        "badge": "#2563eb",
        "badge_text": "#ffffff",
        "toast_bg": "#1e293b",
        "toast_border": "#334155",
        "toast_success": "#10b981",
        "toast_warning": "#f59e0b",
        "toast_error": "#ef4444",
        "scrollbar": "#334155",
        "scrollbar_active": "#475569",
    }

    METHOD_COLORS = {
        "GET": "#10b981",
        "POST": "#3b82f6",
        "PUT": "#f59e0b",
        "PATCH": "#8b5cf6",
        "DELETE": "#ef4444",
    }

    def __init__(self, host: str, port: int) -> None:
        # Basic connection info
        self._host = host
        self._port = port
        self._base_url = f"http://{host}:{port}"

        # Threading and root window (created later)
        self._thread: Optional[threading.Thread] = None
        self._root: Optional["tk.Tk"] = None if tk else None

        # UI components (populated when the UI is built)
        self._cards_canvas: Optional["tk.Canvas"] = None
        self._cards_frame: Optional["ttk.Frame"] = None
        self._cards_scroller: Optional["ScrolledFrame"] = None
        self._mini_text: Optional["tk.Text"] = None
        self._mini_content_frame: Optional["tk.Frame"] = None
        self._mini_arrow: Optional["tk.Label"] = None
        self._mini_collapsed: bool = False
        self._hero_content_frame: Optional["tk.Frame"] = None
        self._hero_collapsed: bool = False
        self._hero_container: Optional["tk.Frame"] = None
        self._log_text: Optional["tk.Text"] = None
        self._health_label: Optional["tk.Label"] = None
        self._health_time_label: Optional["tk.Label"] = None
        self._health_status: Optional[str] = None
        self._health_indicator: Optional["tk.Canvas"] = None

        # Don't create any Tk variables before a root window exists
        self._toast_var: Optional["tk.StringVar"] = None
        self._toast_label: Optional["ttk.Label"] = None
        self._toast_container: Optional["tk.Frame"] = None
        self._toast_after: Optional[str] = None
        self._log_callback: Optional[Callable[[str], None]] = None
        self._doc_window: Optional["tk.Toplevel"] = None

        # Feature flags
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
            try:
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
        root.geometry("1200x800")
        try:
            root.configure(bg=self.COLORS["bg"])
        except Exception:
            pass
        root.minsize(1000, 700)
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
        
        # Main frames
        style.configure("Main.TFrame", background=colors["bg"])
        style.configure("Panel.TFrame", background=colors["panel"])
        style.configure("Hero.TFrame", background=colors["hero"])
        
        # Typography - modern font stack
        style.configure("ServiceHeading.TLabel", 
            background=colors["panel"], 
            foreground=colors["text"], 
            font=("SF Pro Display", 16, "bold"))
        style.configure("HeroTitle.TLabel", 
            background=colors["hero"], 
            foreground=colors["text"], 
            font=("SF Pro Display", 28, "bold"))
        style.configure("HeroSub.TLabel", 
            background=colors["hero"], 
            foreground=colors["muted"], 
            font=("SF Pro Text", 12))
        style.configure("HeroLabel.TLabel", 
            background=colors["hero"], 
            foreground=colors["muted"], 
            font=("SF Pro Text", 11, "bold"))
        
        # Toast notifications
        style.configure("ToastInfo.TLabel", 
            background=colors["toast_bg"], 
            foreground=colors["text"], 
            font=("SF Pro Text", 11))
        style.configure("ToastSuccess.TLabel", 
            background=colors["toast_bg"], 
            foreground=colors["toast_success"], 
            font=("SF Pro Text", 11, "bold"))
        style.configure("ToastWarning.TLabel", 
            background=colors["toast_bg"], 
            foreground=colors["toast_warning"], 
            font=("SF Pro Text", 11, "bold"))
        style.configure("ToastError.TLabel", 
            background=colors["toast_bg"], 
            foreground=colors["toast_error"], 
            font=("SF Pro Text", 11, "bold"))
        
        # Card components
        style.configure("CardContainer.TFrame", background=colors["panel"])
        style.configure("Card.TFrame", background=colors["card"], relief="flat", borderwidth=0)
        style.configure("CardTitle.TLabel", 
            background=colors["card"], 
            foreground=colors["accent_glow"], 
            font=("SF Pro Display", 15, "bold"))
        style.configure("CardBody.TLabel", 
            background=colors["card"], 
            foreground=colors["text"], 
            font=("SF Pro Text", 11))
        style.configure("Method.TLabel", 
            background=colors["card"], 
            foreground=colors["muted"], 
            font=("SF Mono", 10, "bold"))
        style.configure("Path.TLabel", 
            background=colors["card"], 
            foreground=colors["text"], 
            font=("SF Mono", 11))
        
        # Headers
        style.configure("Header.TLabel", 
            background=colors["bg"], 
            foreground=colors["text"], 
            font=("SF Pro Display", 20, "bold"))
        style.configure("Subheader.TLabel", 
            background=colors["bg"], 
            foreground=colors["muted"], 
            font=("SF Pro Text", 11))
        style.configure("PanelLabel.TLabel", 
            background=colors["panel"], 
            foreground=colors["dim"], 
            font=("SF Pro Text", 10, "bold"))
        
        # Modern buttons with hover effects
        style.configure("Accent.TButton", 
            background=colors["accent"], 
            foreground="#ffffff", 
            borderwidth=0,
            relief="flat",
            padding=(18, 10))
        style.map("Accent.TButton",
            background=[("active", colors["accent_hover"]), ("disabled", colors["panel"])],
            foreground=[("disabled", colors["muted"])])
        
        style.configure("Secondary.TButton", 
            background=colors["card"], 
            foreground=colors["text"], 
            borderwidth=1,
            relief="flat",
            padding=(18, 10))
        style.map("Secondary.TButton",
            background=[("active", colors["card_hover"])],
            foreground=[("disabled", colors["muted"])])
        
        style.configure("CardAction.TButton", 
            background=colors["card"], 
            foreground=colors["accent_glow"], 
            borderwidth=0,
            relief="flat",
            padding=(14, 8))
        style.map("CardAction.TButton",
            background=[("active", colors["card_hover"])])
        
        # Modern notebook/tabs
        style.configure("TNotebook", 
            background=colors["panel"], 
            borderwidth=0,
            tabmargins=[2, 5, 2, 0])
        style.configure("TNotebook.Tab", 
            background=colors["panel"], 
            foreground=colors["dim"], 
            padding=(20, 12),
            borderwidth=0)
        style.map("TNotebook.Tab",
            background=[("selected", colors["card"])],
            foreground=[("selected", colors["text"])],
            expand=[("selected", [1, 1, 1, 0])])

    def _build_layout(self, root: "tk.Tk") -> None:
        colors = self.COLORS
        container = ttk.Frame(root, style="Main.TFrame", padding=(0, 0, 0, 0))
        container.pack(fill="both", expand=True)

        # Modern hero section with gradient-like effect (collapsible)
        self._hero_container = tk.Frame(container, bg=colors["hero"])
        self._hero_container.pack(fill="x", pady=(0, 0))

        # Add subtle top border accent
        accent_line = tk.Frame(self._hero_container, bg=colors["accent"], height=3)
        accent_line.pack(fill="x")

        # Collapsible hero header
        hero_header = tk.Frame(self._hero_container, bg=colors["hero"], cursor="hand2")
        hero_header.pack(fill="x", padx=40, pady=(20, 12))
        
        self._hero_arrow = tk.Label(hero_header,
            text="▼",
            bg=colors["hero"],
            fg=colors["accent"],
            font=("SF Pro Text", 14, "bold"))
        self._hero_arrow.pack(side="left", padx=(0, 12))
        
        title_label = tk.Label(hero_header, 
            text="Tools API Control Center", 
            bg=colors["hero"], 
            fg=colors["text"], 
            font=("SF Pro Display", 28, "bold"))
        title_label.pack(side="left", anchor="w")
        
        url_label = tk.Label(hero_header, 
            text=f"🌐 {self._base_url}", 
            bg=colors["hero"], 
            fg=colors["muted"], 
            font=("SF Mono", 12))
        url_label.pack(side="left", anchor="w", padx=(20, 0))
        
        # Bind click events
        hero_header.bind("<Button-1>", lambda e: self._toggle_hero())
        self._hero_arrow.bind("<Button-1>", lambda e: self._toggle_hero())
        title_label.bind("<Button-1>", lambda e: self._toggle_hero())
        url_label.bind("<Button-1>", lambda e: self._toggle_hero())

        # Collapsible hero content
        self._hero_content_frame = tk.Frame(self._hero_container, bg=colors["hero"])
        self._hero_content_frame.pack(fill="x", padx=40, pady=(0, 35))

        # Health status with animated indicator
        health_row = tk.Frame(self._hero_content_frame, bg=colors["hero"])
        health_row.pack(fill="x", pady=(12, 0))

        # Animated health indicator circle
        self._health_indicator = tk.Canvas(health_row, 
            width=16, height=16, 
            bg=colors["hero"], 
            highlightthickness=0)
        self._health_indicator.pack(side="left")
        self._health_indicator.create_oval(2, 2, 14, 14, 
            fill=colors["muted"], 
            outline="", 
            tags="indicator")

        self._health_status = "Checking health..."
        self._health_label = tk.Label(health_row,
            text=self._health_status,
            bg=colors["hero"],
            fg=colors["muted"],
            font=("SF Pro Text", 13, "bold"))
        self._health_label.pack(side="left", padx=(10, 0))

        self._health_time_label = tk.Label(health_row,
            text="",
            bg=colors["hero"],
            fg=colors["dim"],
            font=("SF Pro Text", 11))
        self._health_time_label.pack(side="left", padx=(16, 0))

        self._create_button(health_row, "🔄 Refresh", self._refresh_health, primary=True).pack(side="right", padx=(8, 0))

        # Action buttons row
        action_row = tk.Frame(self._hero_content_frame, bg=colors["hero"])
        action_row.pack(fill="x", pady=(20, 0))

        self._create_button(action_row, "📖 API Documentation", self._open_docs, primary=True).pack(side="left")
        self._create_button(action_row, "📋 Endpoint Catalog", self._show_full_documentation).pack(side="left", padx=(12, 0))
        self._create_button(action_row, "📎 Copy URL", self._copy_base_url).pack(side="left", padx=(12, 0))

        # Modern toast notification
        if self._toast_var is not None:
            self._toast_container = tk.Frame(self._hero_content_frame, bg=colors["toast_bg"], padx=24, pady=16)
            
            self._toast_label = tk.Label(self._toast_container,
                textvariable=self._toast_var,
                bg=colors["toast_bg"],
                fg=colors["text"],
                font=("SF Pro Text", 11),
                anchor="w")
            self._toast_label.pack(fill="x")
            
            # Add border to toast
            self._toast_container.configure(highlightbackground=colors["toast_border"], 
                                           highlightthickness=1)

        # Modern notebook with cleaner tabs
        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True, padx=0, pady=(20, 0))

        overview_tab = ttk.Frame(notebook, style="Panel.TFrame")
        logs_tab = ttk.Frame(notebook, style="Panel.TFrame")
        notebook.add(overview_tab, text="📊 Overview")
        notebook.add(logs_tab, text="📝 Logs")

        overview_body = ttk.Frame(overview_tab, style="Panel.TFrame")
        overview_body.pack(fill="both", expand=True)

        # Service cards section with custom scrollbar
        cards_section = ttk.Frame(overview_body, style="Panel.TFrame")
        cards_section.pack(fill="both", expand=True, padx=32, pady=(24, 20))

        if self._use_bootstrap and ScrolledFrame is not None:
            scroller = ScrolledFrame(cards_section, autohide=True)
            scroller.pack(fill="both", expand=True)
            self._cards_scroller = scroller
            inner_container = (
                getattr(scroller, "scrollable_frame", None)
                or getattr(scroller, "scrolled_frame", None)
                or getattr(scroller, "frame", None)
                or getattr(scroller, "interior", None)
                or scroller
            )
            cards_parent = ttk.Frame(inner_container, style="CardContainer.TFrame")
            cards_parent.pack(fill="both", expand=True)
            self._cards_frame = cards_parent
            self._cards_canvas = None
        else:
            canvas = tk.Canvas(cards_section, bg=colors["panel"], highlightthickness=0)
            canvas.pack(side="left", fill="both", expand=True)
            
            # Custom styled scrollbar
            scrollbar_frame = tk.Frame(cards_section, bg=colors["panel"], width=12)
            scrollbar_frame.pack(side="right", fill="y", padx=(8, 0))
            
            scrollbar_canvas = tk.Canvas(scrollbar_frame, 
                bg=colors["panel"], 
                width=8, 
                highlightthickness=0)
            scrollbar_canvas.pack(fill="y", expand=True)
            
            scrollbar = ttk.Scrollbar(cards_section, orient="vertical", command=canvas.yview)
            scrollbar.pack(side="right", fill="y")
            canvas.configure(yscrollcommand=scrollbar.set)

            inner_frame = ttk.Frame(canvas, style="CardContainer.TFrame")
            window_id = canvas.create_window((0, 0), window=inner_frame, anchor="nw")
            inner_frame.bind("<Configure>",
                lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>",
                lambda event: canvas.itemconfigure(window_id, width=event.width))
            canvas.bind("<MouseWheel>", self._on_mousewheel)
            canvas.bind("<Button-4>", lambda event: self._scroll_canvas(-1))
            canvas.bind("<Button-5>", lambda event: self._scroll_canvas(1))

            self._cards_canvas = canvas
            self._cards_frame = inner_frame
            self._cards_scroller = None

        # Mini docs section - Collapsible
        mini_section = tk.Frame(overview_body, bg=colors["panel"])
        mini_section.pack(fill="both", expand=False, padx=32, pady=(0, 24))
        
        # Collapsible header
        self._mini_collapsed = False
        mini_header_frame = tk.Frame(mini_section, bg=colors["card"], cursor="hand2")
        mini_header_frame.pack(fill="x", pady=(0, 0))
        
        self._mini_arrow = tk.Label(mini_header_frame,
            text="▼",
            bg=colors["card"],
            fg=colors["accent"],
            font=("SF Pro Text", 12, "bold"))
        self._mini_arrow.pack(side="left", padx=(16, 8), pady=12)
        
        mini_header_label = tk.Label(mini_header_frame, 
            text="📄 Quick Reference", 
            bg=colors["card"], 
            fg=colors["text"], 
            font=("SF Pro Text", 12, "bold"))
        mini_header_label.pack(side="left", pady=12)
        
        # Bind click events to all header elements
        mini_header_frame.bind("<Button-1>", lambda e: self._toggle_mini_docs())
        self._mini_arrow.bind("<Button-1>", lambda e: self._toggle_mini_docs())
        mini_header_label.bind("<Button-1>", lambda e: self._toggle_mini_docs())
        
        # Content container
        self._mini_content_frame = tk.Frame(mini_section, bg=colors["card_border"], padx=1, pady=1)
        self._mini_content_frame.pack(fill="both", expand=True, pady=(2, 0))

        self._mini_text = tk.Text(self._mini_content_frame,
            height=11,
            wrap="word",
            bg=colors["mini_bg"],
            fg=colors["text"],
            insertbackground=colors["accent"],
            relief="flat",
            bd=0,
            padx=20,
            pady=16,
            font=("SF Mono", 10))
        self._mini_text.pack(fill="both", expand=True)
        self._mini_text.configure(state="disabled")

        # Logs tab
        logs_wrapper = ttk.Frame(logs_tab, style="Panel.TFrame")
        logs_wrapper.pack(fill="both", expand=True, padx=32, pady=24)

        logs_header = tk.Frame(logs_wrapper, bg=colors["panel"])
        logs_header.pack(fill="x", pady=(0, 16))
        
        logs_title = tk.Label(logs_header, 
            text="📡 Live Server Logs", 
            bg=colors["panel"], 
            fg=colors["text"], 
            font=("SF Pro Text", 13, "bold"))
        logs_title.pack(side="left")
        
        self._create_button(logs_header, "🗑️ Clear", self._clear_logs).pack(side="right")

        logs_frame = tk.Frame(logs_wrapper, bg=colors["card_border"], padx=1, pady=1)
        logs_frame.pack(fill="both", expand=True)

        logs_area = tk.Frame(logs_frame, bg=colors["log_bg"])
        logs_area.pack(fill="both", expand=True)

        self._log_text = tk.Text(logs_area,
            wrap="none",
            bg=colors["log_bg"],
            fg=colors["text"],
            insertbackground=colors["accent"],
            relief="flat",
            bd=0,
            padx=20,
            pady=16,
            font=("SF Mono", 10))
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

        # Add emoji indicators
        emoji_map = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
        }
        emoji = emoji_map.get(level.lower(), "ℹ️")
        
        style_map = {
            "info": "ToastInfo.TLabel",
            "success": "ToastSuccess.TLabel",
            "warning": "ToastWarning.TLabel",
            "error": "ToastError.TLabel",
        }
        
        try:
            self._toast_label.configure(
                text=f"{emoji} {message}",
                bg=self.COLORS["toast_bg"],
                fg=self.COLORS.get(f"toast_{level}", self.COLORS["text"]))
        except Exception:
            pass

        self._toast_container.pack(fill="x", pady=(20, 0))

        if self._toast_after and self._root is not None:
            try:
                self._root.after_cancel(self._toast_after)
            except Exception:
                pass
        self._toast_after = self._root.after(4000, self._hide_toast)

    def _hide_toast(self) -> None:
        if self._toast_container is not None:
            self._toast_container.pack_forget()
        self._toast_after = None

    def _copy_to_clipboard(self, text: str, success_message: str, *, level: str = "success") -> None:
        if self._root is None:
            return
        try:
            self._root.clipboard_clear()
            self._root.clipboard_append(text)
            self._root.update()  # Force clipboard update
            self._show_toast(success_message, level=level)
        except Exception as e:
            self._show_toast(f"Clipboard error: {str(e)}", level="error")

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

    def _create_method_badge(self, parent: "tk.Widget", method: str):
        method_upper = method.upper()
        if self._use_bootstrap:
            bootstyle = f"{self._method_bootstyle(method_upper)}-INVERSE"
            return ttk.Label(parent, text=method_upper, bootstyle=bootstyle, padding=(14, 6))  # type: ignore[arg-type]

        color = self.METHOD_COLORS.get(method_upper, self.COLORS["badge"])
        
        # Create modern rounded badge
        badge = tk.Label(parent,
            text=method_upper,
            bg=color,
            fg="#ffffff",
            font=("SF Mono", 9, "bold"),
            padx=12,
            pady=4)
        
        return badge

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

    def _on_mousewheel(self, event: "tk.Event") -> None:
        if not self._cards_canvas:
            return
        delta = 0
        if hasattr(event, "delta") and event.delta:
            delta = int(-event.delta / 120)
        elif getattr(event, "num", None) in (4, 5):
            delta = -1 if event.num == 4 else 1
        if delta:
            self._cards_canvas.yview_scroll(delta, "units")

    def _scroll_canvas(self, delta: int) -> None:
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

    def _toggle_hero(self) -> None:
        """Toggle the hero section collapse/expand instantly."""
        if self._hero_content_frame is None or self._hero_arrow is None or self._hero_container is None:
            return
        
        self._hero_collapsed = not self._hero_collapsed
        
        if self._hero_collapsed:
            # Collapse - hide content and repack hero with minimal padding
            self._hero_arrow.configure(text="▶")
            self._hero_content_frame.pack_forget()
            
            # Adjust padding when collapsed
            self._hero_container.pack_configure(pady=(0, 0))
        else:
            # Expand - show content and restore padding
            self._hero_arrow.configure(text="▼")
            self._hero_content_frame.pack(fill="x", padx=40, pady=(0, 35))
            self._hero_container.pack_configure(pady=(0, 0))

    def _toggle_mini_docs(self) -> None:
        """Toggle the mini docs section collapse/expand instantly."""
        if self._mini_content_frame is None or self._mini_arrow is None:
            return
        
        self._mini_collapsed = not self._mini_collapsed
        
        if self._mini_collapsed:
            # Collapse instantly
            self._mini_arrow.configure(text="▶")
            self._mini_content_frame.pack_forget()
        else:
            # Expand instantly
            self._mini_arrow.configure(text="▼")
            self._mini_content_frame.pack(fill="both", expand=True, pady=(2, 0))

    def _populate_service_cards(self) -> None:
        if self._cards_frame is None:
            return

        for child in self._cards_frame.winfo_children():
            child.destroy()

        services, error = get_service_details()
        if error:
            error_label = tk.Label(self._cards_frame,
                text=f"⚠️ {error}",
                bg=self.COLORS["panel"],
                fg=self.COLORS["error"],
                font=("SF Pro Text", 12),
                wraplength=800,
                justify="left")
            error_label.pack(fill="x", pady=16)
            return

        for service in services:
            section = tk.Frame(self._cards_frame, bg=self.COLORS["panel"])
            section.pack(fill="x", expand=True, pady=(0, 24))

            # Service heading with icon
            service_header = tk.Label(section,
                text=f"🔧 {service.get('name', 'Service')}",
                bg=self.COLORS["panel"],
                fg=self.COLORS["text"],
                font=("SF Pro Display", 17, "bold"),
                anchor="w")
            service_header.pack(fill="x", pady=(0, 8))

            summary = service.get("summary")
            if summary:
                summary_label = tk.Label(section,
                    text=summary,
                    bg=self.COLORS["panel"],
                    fg=self.COLORS["muted"],
                    font=("SF Pro Text", 11),
                    wraplength=900,
                    justify="left")
                summary_label.pack(fill="x", pady=(0, 16))

            for endpoint in service.get("endpoints", []):
                # Modern card with shadow effect (simulated with border)
                card_border = tk.Frame(section, 
                    bg=self.COLORS["card_border"], 
                    padx=1, 
                    pady=1)
                card_border.pack(fill="x", expand=True, pady=14)
                
                card = tk.Frame(card_border, 
                    bg=self.COLORS["card"], 
                    padx=28,
                    pady=24)
                card.pack(fill="x", expand=True)

                # Card title
                title_label = tk.Label(card,
                    text=endpoint["headline"],
                    bg=self.COLORS["card"],
                    fg=self.COLORS["accent_glow"],
                    font=("SF Pro Display", 15, "bold"),
                    anchor="w")
                title_label.pack(anchor="w")

                # Method and path row
                meta_row = tk.Frame(card, bg=self.COLORS["card"])
                meta_row.pack(fill="x", pady=(10, 14))
                
                badge = self._create_method_badge(meta_row, endpoint.get("method", "GET"))
                if badge:
                    badge.pack(side="left")
                
                path_label = tk.Label(meta_row,
                    text=endpoint.get("path", "/"),
                    bg=self.COLORS["card"],
                    fg=self.COLORS["text"],
                    font=("SF Mono", 11))
                path_label.pack(side="left", padx=(14, 0))
                
                content_type = endpoint.get("request", {}).get("content_type")
                if content_type:
                    ct_label = tk.Label(meta_row,
                        text=f"• {content_type}",
                        bg=self.COLORS["card"],
                        fg=self.COLORS["dim"],
                        font=("SF Mono", 10))
                    ct_label.pack(side="left", padx=(18, 0))

                # Tagline
                tagline = endpoint.get("tagline")
                if tagline:
                    tagline_label = tk.Label(card,
                        text=tagline,
                        bg=self.COLORS["card"],
                        fg=self.COLORS["muted"],
                        font=("SF Pro Text", 11),
                        wraplength=900,
                        justify="left")
                    tagline_label.pack(anchor="w", pady=(0, 12))

                # Details section
                detail_lines: List[str] = []

                request_fields = self._format_fields(endpoint.get("request", {}).get("fields"))
                if request_fields:
                    detail_lines.append("📤 Send:")
                    detail_lines.extend([f"  • {field}" for field in request_fields])
                else:
                    detail_lines.append("📤 Send: No request body documented.")

                response_fields = self._format_fields(endpoint.get("response", {}).get("fields"))
                if response_fields:
                    detail_lines.append("\n📥 Receive:")
                    detail_lines.extend([f"  • {field}" for field in response_fields])
                else:
                    detail_lines.append("\n📥 Receive: No structured response documented.")

                for note in endpoint.get("notes", []):
                    detail_lines.append(f"\n💡 Note: {note}")

                details_label = tk.Label(card,
                    text="\n".join(detail_lines),
                    bg=self.COLORS["card"],
                    fg=self.COLORS["text"],
                    font=("SF Pro Text", 11),
                    justify="left",
                    wraplength=900)
                details_label.pack(anchor="w", pady=(0, 18))

                # Action buttons
                action_row = tk.Frame(card, bg=self.COLORS["card"])
                action_row.pack(fill="x")
                
                # Use a wrapper to properly capture the endpoint
                def make_copy_handler(ep):
                    return lambda: self._copy_curl_command(ep)
                
                self._create_button(action_row, 
                    "📋 Copy cURL", 
                    make_copy_handler(endpoint), 
                    primary=True).pack(side="left")
                
                action_hint = tk.Label(action_row,
                    text="Includes base URL and example payload",
                    bg=self.COLORS["card"],
                    fg=self.COLORS["dim"],
                    font=("SF Pro Text", 10),
                    wraplength=600,
                    justify="left")
                action_hint.pack(side="left", padx=(18, 0))

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
        self._show_toast("Logs cleared", level="info")

    def _refresh_health(self) -> None:
        if not self._supported:
            return

        def worker() -> None:
            url = f"{self._base_url}/health"
            status_text = "Checking health..."
            color = self.COLORS["muted"]
            indicator_color = self.COLORS["muted"]
            
            try:
                response = httpx.get(url, timeout=3.0)
                if response.status_code == 200:
                    payload = response.json()
                    status_value = str(payload.get("status", "unknown")).lower()
                    if status_value == "ok":
                        color = self.COLORS["success"]
                        indicator_color = self.COLORS["success_glow"]
                        status_text = "✓ Healthy — All systems operational"
                    else:
                        color = self.COLORS["warning"]
                        indicator_color = self.COLORS["warning"]
                        status_text = f"Status: {status_value}"
                    details = f"{payload.get('service', 'Tools API')} {payload.get('version', '')}".strip()
                    if details:
                        status_text += f" ({details})"
                else:
                    color = self.COLORS["error"]
                    indicator_color = self.COLORS["error"]
                    status_text = f"⚠ HTTP {response.status_code}"
            except Exception as exc:
                color = self.COLORS["error"]
                indicator_color = self.COLORS["error"]
                status_text = f"✗ Unavailable ({exc.__class__.__name__})"

            checked_at = datetime.now().strftime("%H:%M:%S")
            self._schedule(lambda: self._update_health_display(status_text, color, indicator_color, checked_at))

        threading.Thread(target=worker, name="health-check", daemon=True).start()

    def _update_health_display(self, message: str, color: str, indicator_color: str, timestamp: str) -> None:
        if self._health_label is None or self._health_time_label is None:
            return
        
        self._health_label.configure(text=message, fg=color)
        self._health_time_label.configure(text=f"Last checked: {timestamp}")
        
        # Update indicator circle instantly
        if self._health_indicator:
            self._health_indicator.delete("indicator")
            self._health_indicator.create_oval(2, 2, 14, 14, 
                fill=indicator_color, 
                outline="",
                tags="indicator")

    def _open_docs(self) -> None:
        webbrowser.open(f"{self._base_url}/docs")
        self._show_toast("Opening API documentation in browser", level="info")

    def _show_full_documentation(self) -> None:
        if self._root is None or tk is None:
            return
        if self._doc_window is not None and bool(self._doc_window.winfo_exists()):
            self._doc_window.lift()
            self._doc_window.focus_force()
            return

        doc_window = tk.Toplevel(self._root)
        doc_window.title("📋 Tools API Endpoint Catalog")
        doc_window.configure(bg=self.COLORS["panel"])
        doc_window.geometry("800x700")
        doc_window.minsize(600, 500)

        # Header
        header = tk.Frame(doc_window, bg=self.COLORS["hero"], padx=32, pady=24)
        header.pack(fill="x")
        
        header_title = tk.Label(header,
            text="📋 Endpoint Catalog",
            bg=self.COLORS["hero"],
            fg=self.COLORS["text"],
            font=("SF Pro Display", 22, "bold"))
        header_title.pack(anchor="w")
        
        header_sub = tk.Label(header,
            text="Complete reference for all available API endpoints",
            bg=self.COLORS["hero"],
            fg=self.COLORS["muted"],
            font=("SF Pro Text", 11))
        header_sub.pack(anchor="w", pady=(6, 0))

        # Content area with border
        content_border = tk.Frame(doc_window, bg=self.COLORS["card_border"], padx=1, pady=1)
        content_border.pack(fill="both", expand=True, padx=32, pady=(20, 32))

        content_frame = tk.Frame(content_border, bg=self.COLORS["card"])
        content_frame.pack(fill="both", expand=True)

        text_widget = tk.Text(content_frame,
            wrap="word",
            bg=self.COLORS["card"],
            fg=self.COLORS["text"],
            insertbackground=self.COLORS["accent"],
            relief="flat",
            bd=0,
            padx=24,
            pady=20,
            font=("SF Mono", 10))
        text_widget.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(content_frame, orient="vertical", command=text_widget.yview)
        scrollbar.pack(side="right", fill="y")
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.insert("1.0", render_documentation())
        text_widget.configure(state="disabled")

        def on_close() -> None:
            if self._doc_window is not None:
                self._doc_window = None
            doc_window.destroy()

        doc_window.protocol("WM_DELETE_WINDOW", on_close)
        self._doc_window = doc_window

    def _copy_base_url(self) -> None:
        if self._root is None:
            return
        self._copy_to_clipboard(self._base_url, "Base URL copied to clipboard")

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
        self._toast_label = None
        self._toast_container = None
        self._root = None
        self._thread = None
        self._cards_canvas = None
        self._cards_frame = None
        self._cards_scroller = None
        self._mini_text = None
        self._mini_content_frame = None
        self._mini_arrow = None
        self._hero_content_frame = None
        self._hero_container = None
        self._log_text = None
        self._doc_window = None
        self._health_label = None
        self._health_time_label = None
        self._health_indicator = None


__all__ = ["ControlCenterUI"]