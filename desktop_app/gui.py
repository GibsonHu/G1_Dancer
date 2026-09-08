from __future__ import annotations

import datetime as dt
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Dict

from g1_dancer.remote import RemoteClient


def launch(url: str, ssh_target: str, ssh_port: int) -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        raise RuntimeError("Tkinter is not installed. Install your OS python3-tk package.") from exc

    root = tk.Tk()
    root.title("G1 DANCER")
    root.geometry("920x700")
    root.minsize(800, 620)
    icon_ref = None
    try:
        icon_ref = tk.PhotoImage(file=Path(__file__).with_name("assets") / "app_icon.png")
        root.iconphoto(True, icon_ref)
    except tk.TclError:
        pass

    url_var = tk.StringVar(value=url)
    ssh_var = tk.StringVar(value=ssh_target)
    port_var = tk.StringVar(value=str(ssh_port))
    dance_var = tk.StringVar(value="Refresh to load existing dances")
    mp3_var = tk.StringVar()
    status_var = tk.StringVar(value="Ready — connect to the development-PC hotspot.")
    dance_ids: Dict[str, str] = {}
    paused = {"value": False}
    logs_visible = {"value": False}

    style = ttk.Style(root)
    style.configure("App.TNotebook", padding=2)
    style.configure("App.TNotebook.Tab", font=("TkDefaultFont", 12, "bold"), padding=(28, 12))
    style.configure("Big.TButton", font=("TkDefaultFont", 18, "bold"), padding=(42, 30))
    style.configure("Status.TLabel", font=("TkDefaultFont", 11), padding=(8, 8))

    # The generated blurred version of dancer_1.png is bundled with the app.
    canvas = tk.Canvas(root, highlightthickness=0, background="#141b29")
    canvas.pack(fill="both", expand=True)
    asset = Path(__file__).with_name("assets") / "dancer_1_blurred.png"
    background = {"source": None, "photo": None, "item": None}
    try:
        from PIL import Image, ImageOps, ImageTk

        background["source"] = Image.open(asset)

        def resize_background(event: Any) -> None:
            if event.width < 2 or event.height < 2:
                return
            image = ImageOps.fit(
                background["source"].copy(), (event.width, event.height), Image.Resampling.LANCZOS
            )
            background["photo"] = ImageTk.PhotoImage(image)
            if background["item"] is None:
                background["item"] = canvas.create_image(0, 0, anchor="nw", image=background["photo"])
            else:
                canvas.itemconfigure(background["item"], image=background["photo"])

        canvas.bind("<Configure>", resize_background)
    except (ImportError, OSError):
        # The blurred image is still usable without Pillow, just without resize-to-window.
        try:
            background["photo"] = tk.PhotoImage(file=asset)
            background["item"] = canvas.create_image(0, 0, anchor="nw", image=background["photo"])
        except tk.TclError:
            pass

    canvas.create_text(
        460, 34, text="G1 DANCER", fill="white", font=("TkDefaultFont", 25, "bold"), tags="title"
    )

    notebook = ttk.Notebook(canvas, style="App.TNotebook")
    canvas.create_window(30, 75, anchor="nw", window=notebook, width=860, height=590, tags="notebook")

    def resize_content(event: Any) -> None:
        width, height = max(1, event.width), max(1, event.height)
        canvas.coords("title", width / 2, 34)
        canvas.itemconfigure("notebook", width=max(740, width - 60), height=max(500, height - 110))

    canvas.bind("<Configure>", resize_content, add="+")

    connection_tab = ttk.Frame(notebook, padding=24)
    dance_tab = ttk.Frame(notebook, padding=24)
    notebook.add(connection_tab, text="Connection")
    notebook.add(dance_tab, text="Dance")
    connection_tab.columnconfigure(0, weight=1)
    dance_tab.columnconfigure(0, weight=1)

    def show_info() -> None:
        messagebox.showinfo(
            "G1 DANCER",
            "Connection tab\nStart the service on the development PC, then use Refresh dances.\n\n"
            "Dance tab\nChoose an existing dance, optionally attach an MP3, test it with Play linked music, "
            "or use Play to begin the dance.\n\n"
            "Pause suspends music and stops future timeline steps. Reset stops audio and motion. "
            "An action already in progress may finish; keep the physical E-stop ready.",
        )

    connection_card = ttk.LabelFrame(connection_tab, text="Development PC", padding=18)
    connection_card.grid(row=0, column=0, sticky="ew")
    connection_card.columnconfigure(1, weight=1)
    ttk.Label(connection_card, text="API address").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=6)
    ttk.Entry(connection_card, textvariable=url_var).grid(row=0, column=1, sticky="ew", pady=6)
    ttk.Label(connection_card, text="SSH target").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=6)
    ttk.Entry(connection_card, textvariable=ssh_var).grid(row=1, column=1, sticky="ew", pady=6)
    port_row = ttk.Frame(connection_card)
    port_row.grid(row=2, column=1, sticky="w", pady=(6, 0))
    ttk.Label(port_row, text="SSH port").pack(side="left", padx=(0, 8))
    ttk.Entry(port_row, textvariable=port_var, width=7).pack(side="left")

    connection_actions = ttk.Frame(connection_tab)
    connection_actions.grid(row=1, column=0, sticky="ew", pady=18)

    log_frame = ttk.LabelFrame(connection_tab, text="Activity log", padding=8)
    log_frame.grid(row=3, column=0, sticky="nsew")
    connection_tab.rowconfigure(3, weight=1)
    log_frame.columnconfigure(0, weight=1)
    log_frame.rowconfigure(0, weight=1)
    log_text = tk.Text(log_frame, height=11, wrap="word", state="disabled", font=("TkFixedFont", 10))
    log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=log_text.yview)
    log_text.configure(yscrollcommand=log_scroll.set)
    log_text.grid(row=0, column=0, sticky="nsew")
    log_scroll.grid(row=0, column=1, sticky="ns")
    log_frame.grid_remove()

    dance_card = ttk.LabelFrame(dance_tab, text="Choose dance and music", padding=18)
    dance_card.grid(row=0, column=0, sticky="ew")
    dance_card.columnconfigure(0, weight=1)
    dance_box = ttk.Combobox(dance_card, textvariable=dance_var, state="readonly", font=("TkDefaultFont", 13))
    dance_box.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
    ttk.Entry(dance_card, textvariable=mp3_var).grid(row=1, column=0, sticky="ew", padx=(0, 10))

    playback_box = ttk.LabelFrame(dance_tab, text="Playback", padding=28)
    playback_box.grid(row=1, column=0, pady=(26, 0))
    playback_row = ttk.Frame(playback_box)
    playback_row.pack()

    status_bar = ttk.Frame(dance_tab)
    status_bar.grid(row=2, column=0, sticky="ew", pady=(18, 0))
    status_bar.columnconfigure(0, weight=1)
    ttk.Label(status_bar, textvariable=status_var, style="Status.TLabel", wraplength=650).grid(
        row=0, column=0, sticky="w"
    )

    def log(message: str) -> None:
        timestamp = dt.datetime.now().strftime("%H:%M:%S")
        log_text.configure(state="normal")
        log_text.insert("end", f"{timestamp}  {message}\n")
        log_text.see("end")
        log_text.configure(state="disabled")

    def toggle_logs() -> None:
        logs_visible["value"] = not logs_visible["value"]
        if logs_visible["value"]:
            log_frame.grid()
            logs_button.configure(text="Hide log")
        else:
            log_frame.grid_remove()
            logs_button.configure(text="Show log")

    def client() -> RemoteClient:
        return RemoteClient(url_var.get().strip())

    def complete(success: Callable[[Any], None], activity: str, result: Any = None, error: Exception | None = None) -> None:
        if error is not None:
            status_var.set(f"Could not {activity.lower()}: {error}")
            log(f"ERROR  {activity}: {error}")
            messagebox.showerror("G1 DANCER", str(error))
        else:
            log(f"OK     {activity}")
            success(result)

    def background(work: Callable[[], Any], success: Callable[[Any], None], activity: str) -> None:
        status_var.set(f"{activity}…")
        log(f"START  {activity}")

        def run() -> None:
            try:
                root.after(0, complete, success, activity, work(), None)
            except Exception as exc:
                root.after(0, complete, success, activity, None, exc)

        threading.Thread(target=run, daemon=True).start()

    def refresh() -> None:
        def done(response: Dict[str, Any]) -> None:
            previous_id = dance_ids.get(dance_var.get())
            dance_ids.clear()
            labels, selected_label = [], ""
            for routine in response.get("routines", []):
                audio_note = " • MP3" if routine.get("audio") else ""
                label = f"{routine['name']} ({routine['id']}){audio_note}"
                dance_ids[label] = routine["id"]
                labels.append(label)
                if routine["id"] == previous_id:
                    selected_label = label
            dance_box["values"] = labels
            if labels:
                dance_var.set(selected_label or labels[0])
                status_var.set(f"Ready — {len(labels)} dance(s) available.")
                notebook.select(dance_tab)
            else:
                dance_var.set("No dances found on the development PC")
                status_var.set("Connected, but no existing dances were found.")

        background(lambda: client().request("GET", "/api/routines"), done, "Refreshing dances")

    def start_service() -> None:
        def work() -> str:
            port = int(port_var.get())
            if not 1 <= port <= 65535:
                raise ValueError("SSH port must be between 1 and 65535")
            target = ssh_var.get().strip()
            if not target or target.startswith("-"):
                raise ValueError("Invalid SSH target")
            result = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-p", str(port), target,
                 "systemctl", "--user", "start", "g1-dancer.service"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout).strip() or "Remote service failed to start")
            return "Development-PC service started."

        def done(text: str) -> None:
            status_var.set(text)
            root.after(500, refresh)

        background(work, done, "Starting remote service")

    def selected_id() -> str:
        routine_id = dance_ids.get(dance_var.get())
        if not routine_id:
            raise RuntimeError("Refresh and select an existing dance first.")
        return routine_id

    def choose_mp3() -> None:
        filename = filedialog.askopenfilename(title="Choose a song", filetypes=[("MP3 audio", "*.mp3")])
        if filename:
            mp3_var.set(filename)
            log(f"Selected MP3: {Path(filename).name}")

    def add_mp3() -> None:
        try:
            routine_id, path = selected_id(), Path(mp3_var.get())
        except Exception as exc:
            complete(lambda _: None, "Selecting an MP3", error=exc)
            return

        def done(_: Any) -> None:
            status_var.set(f"MP3 attached to {routine_id}.")
            refresh()

        background(lambda: client().upload(routine_id, path), done, f"Uploading {path.name}")

    def play() -> None:
        try:
            routine_id = selected_id()
        except Exception as exc:
            complete(lambda _: None, "Selecting a dance", error=exc)
            return
        if not messagebox.askyesno("Confirm robot motion", "Is the area clear, with the physical E-stop ready?", icon="warning"):
            log("CANCEL Play confirmation declined")
            return
        paused["value"] = False
        pause_button.configure(text="Pause")
        background(lambda: client().request("POST", f"/api/routines/{routine_id}/play", b"{}", safety_confirmed=True),
                   lambda _: status_var.set(f"Playing {routine_id}."), f"Playing {routine_id}")

    def play_music() -> None:
        try:
            routine_id = selected_id()
        except Exception as exc:
            complete(lambda _: None, "Selecting a dance", error=exc)
            return
        paused["value"] = False
        pause_button.configure(text="Pause")
        background(lambda: client().request("POST", f"/api/routines/{routine_id}/music", b"{}"),
                   lambda _: status_var.set(f"Playing linked music for {routine_id}."), f"Playing music for {routine_id}")

    def toggle_pause() -> None:
        endpoint = "/api/resume" if paused["value"] else "/api/pause"
        activity = "Resuming" if paused["value"] else "Pausing"

        def done(_: Any) -> None:
            paused["value"] = not paused["value"]
            pause_button.configure(text="Resume" if paused["value"] else "Pause")
            status_var.set("Paused." if paused["value"] else "Playing.")

        background(lambda: client().request("POST", endpoint, b"{}"), done, activity)

    def reset() -> None:
        paused["value"] = False
        pause_button.configure(text="Pause")
        background(lambda: client().request("POST", "/api/reset", b"{}"),
                   lambda _: status_var.set("Reset complete — ready."), "Resetting dance and audio")

    ttk.Button(connection_actions, text="Start remote service", command=start_service).pack(side="left")
    ttk.Button(connection_actions, text="Refresh dances", command=refresh).pack(side="left", padx=10)
    ttk.Button(connection_actions, text="Info", command=show_info).pack(side="right")
    logs_button = ttk.Button(connection_tab, text="Show log", command=toggle_logs)
    logs_button.grid(row=2, column=0, sticky="w", pady=(0, 10))

    ttk.Button(dance_card, text="Browse…", command=choose_mp3).grid(row=1, column=1, sticky="e")
    music_actions = ttk.Frame(dance_card)
    music_actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
    ttk.Button(music_actions, text="Play linked music", command=play_music).pack(side="left")
    ttk.Button(music_actions, text="Add / replace MP3", command=add_mp3).pack(side="right")
    ttk.Button(playback_row, text="Play", style="Big.TButton", width=14, command=play).pack(side="left", padx=10)
    pause_button = ttk.Button(playback_row, text="Pause", style="Big.TButton", width=14, command=toggle_pause)
    pause_button.pack(side="left", padx=10)
    ttk.Button(playback_row, text="Reset", style="Big.TButton", width=14, command=reset).pack(side="left", padx=10)

    log("GUI opened")
    root.mainloop()
