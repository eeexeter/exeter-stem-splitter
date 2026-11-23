import ctypes
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk
from tkinterdnd2 import COPY, DND_FILES, REFUSE_DROP, TkinterDnD

from appearance import BG, BORDER, FIELD, MUTED, PANEL, TEXT, RoundedPanel, configure_theme
from models import DEFAULT_MODEL, MODEL_STEMS, QUALITY_MODEL, SIX_STEM_MODEL
from stem_icons import stem_icon
from stem_player import StemPlayer
from version import VERSION
from windows_dialog import documents_folder, open_audio_file
from worker_job import start_worker


FROZEN = getattr(sys, "frozen", False)
ASSETS = Path(__file__).resolve().parent
ROOT = Path(sys.executable).resolve().parent if FROZEN else ASSETS
PYTHON = ROOT / "runtime" / "python.exe" if FROZEN else ROOT / ".venv" / "Scripts" / "python.exe"
WORKER = (ROOT / "runtime" if FROZEN else ROOT) / "separator.py"
CACHE = ROOT / ("runtime" if FROZEN else ".runtime") / "models"

MODEL_CHOICES = {
    "4 stems · Fast": DEFAULT_MODEL,
    "4 stems · Quality (slower)": QUALITY_MODEL,
    "6 stems · + Guitar & Piano": SIX_STEM_MODEL,
}

DROP_ICON_SCALES = (0.62, 0.75, 0.85, 0.92, 0.96, 0.985, 1.0)


def clock_time(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def read_worker(process, events):
    with process.stdout:
        for line in process.stdout:
            line = line.strip()
            if line.startswith("{"):
                try:
                    events.put(json.loads(line))
                except json.JSONDecodeError:
                    pass
    events.put({"exit": process.wait()})


class Timeline(tk.Canvas):
    def __init__(self, parent, position, pixels):
        super().__init__(parent, bg=FIELD, width=pixels(72), height=pixels(22),
                         highlightthickness=0, borderwidth=0, cursor="hand2", takefocus=True)
        self.position = position
        self.duration = 0
        self.pixels = pixels
        self.hovered = False
        self.rail = self.create_line(0, 0, 0, 0, fill=BORDER, width=pixels(4), capstyle="round")
        self.played = self.create_line(0, 0, 0, 0, fill=TEXT, width=pixels(4), capstyle="round")
        self.focus_ring = self.create_oval(0, 0, 0, 0, outline=MUTED, width=pixels(1), state="hidden")
        self.knob = self.create_oval(0, 0, 0, 0, fill=TEXT, outline="")
        self.bind("<Configure>", self.draw)
        self.bind("<Enter>", lambda _event: self.set_hover(True))
        self.bind("<Leave>", lambda _event: self.set_hover(False))
        self.bind("<FocusIn>", self.draw)
        self.bind("<FocusOut>", self.draw)
        self.position.trace_add("write", self.draw)

    def track_edges(self):
        margin = self.pixels(9)
        return margin, max(margin + 1, self.winfo_width() - margin - 1)

    def seconds_at(self, x):
        left, right = self.track_edges()
        fraction = max(0, min(1, (x - left) / (right - left)))
        return fraction * self.duration

    def set_duration(self, seconds):
        self.duration = seconds
        self.draw()

    def set_hover(self, hovered):
        self.hovered = hovered
        self.draw()

    def draw(self, *_event):
        left, right = self.track_edges()
        y = self.winfo_height() / 2
        fraction = self.position.get() / self.duration if self.duration else 0
        x = left + max(0, min(1, fraction)) * (right - left)
        radius = self.pixels(5.5 if self.hovered else 4)
        ring = radius + self.pixels(2)
        self.coords(self.rail, left, y, right, y)
        self.coords(self.played, left, y, x, y)
        self.itemconfigure(self.played, state="normal" if x > left else "hidden")
        self.coords(self.knob, x - radius, y - radius, x + radius, y + radius)
        self.coords(self.focus_ring, x - ring, y - ring, x + ring, y + ring)
        self.itemconfigure(self.focus_ring, state="normal" if self.focus_get() == self else "hidden")


class App:
    def __init__(self, root):
        self.root = root
        self.display_scale = root.winfo_fpixels("1i") / 96
        px = self.pixels
        self.source = tk.StringVar()
        self.output = tk.StringVar()
        self.destination = None
        self.track_name = ""
        self.model = tk.StringVar(value=next(iter(MODEL_CHOICES)))
        self.state = tk.StringVar(value="Select an audio file")
        self.result = None
        self.player = StemPlayer()
        self.displayed_playback_state = self.player.state
        self.play_buttons = {}
        self.stem_cards = {}
        self.stem_selection = {}
        self.card_press = None
        self.seeking = False
        self.playhead = tk.DoubleVar()
        self.playback_time = tk.StringVar(value="0:00 / 0:00")
        self.process = None
        self.worker_job = None
        self.staging = None
        self.events = queue.Queue()
        self.worker_error = ""
        self.processing_device = None
        self.closing = False
        self.drag_active = False
        self.dragging_stem = False
        self.drop_animation = None
        self.drop_frame = 0

        root.title(f"Stem Splitter {VERSION} — Demucs")
        root.configure(background=BG)
        root.geometry(f"{px(680)}x{px(465)}")
        root.minsize(px(590), px(450))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.option_add("*Font", ("Segoe UI", 10))
        root.option_add("*TCombobox*Listbox.background", PANEL)
        root.option_add("*TCombobox*Listbox.foreground", TEXT)
        root.option_add("*TCombobox*Listbox.selectBackground", TEXT)
        root.option_add("*TCombobox*Listbox.selectForeground", BG)

        self.theme_images = configure_theme(root, px)

        body = self.body = tk.Frame(root, bg=BG, padx=px(28), pady=px(23))
        body.pack(expand=True, fill="both")

        footer = tk.Frame(body, bg=BG)
        footer.pack(side="bottom", fill="x", pady=(px(15), 0))
        self.progress = ttk.Progressbar(footer, maximum=100)
        self.progress.pack(fill="x", pady=(0, px(5)))
        self.label(footer, variable=self.state, color=MUTED).pack(anchor="w")

        self.label(body, "Stem Splitter", size=27, bold=True).pack(anchor="w")
        self.label(body, "Demucs v4  ·  Local processing", color=MUTED).pack(anchor="w", pady=(px(2), px(16)))

        settings = RoundedPanel(body, outside=BG, fill=PANEL, radius=px(21),
                                padx=px(19), pady=px(15), outline=BORDER)
        settings.pack(fill="x")
        card = settings.content
        self.source_button = self.path_row(card, "Audio file", self.source, self.choose_source)
        self.output_button = self.path_row(card, "Output folder", self.output, self.choose_output, top=12)

        self.label(card, "Model", bg=PANEL, bold=True).pack(anchor="w", pady=(px(12), px(3)))
        self.model_menu = ttk.Combobox(card, textvariable=self.model, values=tuple(MODEL_CHOICES),
                                       width=28, exportselection=False)
        self.model_menu.pack(anchor="w")
        for event in ("<<ComboboxSelected>>", "<FocusOut>"):
            self.model_menu.bind(event, lambda selection: selection.widget.selection_clear())

        actions = tk.Frame(body, bg=BG)
        actions.pack(fill="x", pady=(px(14), 0))
        self.start_button = ttk.Button(actions, text="Split track", style="Primary.TButton", command=self.start)
        self.start_button.pack(side="left")
        self.result_button = ttk.Button(actions, text="Open output folder", style="Output.TButton",
                                        command=self.open_result)
        self.result_button.pack(side="right")

        self.playback = RoundedPanel(body, outside=BG, fill=PANEL, radius=px(21),
                                     padx=px(14), pady=px(11), outline=BORDER)
        header = tk.Frame(self.playback.content, bg=PANEL)
        header.pack(fill="x", pady=(0, px(6)))
        self.label(header, "Stems", bg=PANEL, bold=True).pack(side="left")
        self.stop_button = ttk.Button(header, text="Stop", style="Playback.TButton",
                                      command=self.stop_playback)
        self.stop_button.pack(side="right")
        self.select_stems_button = ttk.Button(header, text="Select all", style="Selection.TButton",
                                             command=self.toggle_stem_selection)
        self.select_stems_button.pack(side="right", padx=(0, px(8)))
        self.label(header, "Select stems, then drag", bg=PANEL, color=MUTED).pack(
            side="right", padx=(0, px(10)))
        self.stem_list = tk.Frame(self.playback.content, bg=PANEL)
        self.stem_list.pack(fill="x")
        self.stem_columns = []
        for column in range(2):
            self.stem_list.columnconfigure(column, weight=1, uniform="stems")
            stack = tk.Frame(self.stem_list, bg=PANEL)
            stack.grid(row=0, column=column, sticky="new", padx=px(3))
            self.stem_columns.append(stack)

        size = (px(20), px(20))
        with Image.open(ASSETS / "stem-icons" / "play.png") as play:
            self.play_photo = ImageTk.PhotoImage(play.resize(size, Image.Resampling.LANCZOS), master=root)
        pause = Image.new("RGBA", (96, 96))
        bars = ImageDraw.Draw(pause)
        for x in (25, 54):
            bars.rounded_rectangle((x, 14, x + 16, 82), radius=6, fill=TEXT)
        self.pause_photo = ImageTk.PhotoImage(pause.resize(size, Image.Resampling.LANCZOS), master=root)
        self.transport = tk.Frame(self.stem_list, bg=FIELD)
        self.playback_clock = self.label(self.transport, variable=self.playback_time, bg=FIELD,
                                         color=MUTED, anchor="e")
        self.playback_clock.pack(side="right", padx=(px(8), 0))
        self.timeline = Timeline(self.transport, self.playhead, px)
        self.timeline.pack(side="left", fill="x", expand=True)
        self.timeline.bind("<ButtonPress-1>", self.begin_seek)
        self.timeline.bind("<B1-Motion>", self.preview_seek)
        self.timeline.bind("<ButtonRelease-1>", self.end_seek)
        self.timeline.bind("<Left>", lambda _event: self.seek_to(self.playhead.get() - 5))
        self.timeline.bind("<Right>", lambda _event: self.seek_to(self.playhead.get() + 5))
        self.timeline.bind("<Home>", lambda _event: self.seek_to(0))
        self.timeline.bind("<End>", lambda _event: self.seek_to(self.player.duration))

        self.drop_overlay = tk.Canvas(root, bg=BG, highlightthickness=0, borderwidth=0)
        self.drop_border = self.drop_overlay.create_rectangle(0, 0, 0, 0, outline=MUTED,
                                                              width=px(2), dash=(px(5), px(5)))
        with Image.open(ASSETS / "stem-splitter-upload-icon.png") as icon:
            sizes = [px(128 * scale) for scale in DROP_ICON_SCALES]
            self.drop_frames = [ImageTk.PhotoImage(icon.resize((size, size), Image.Resampling.LANCZOS,
                                                               reducing_gap=3), master=root)
                                for size in sizes]
        self.drop_icon = self.drop_overlay.create_image(0, 0, image=self.drop_frames[0])
        self.drop_message = self.drop_overlay.create_text(0, 0, text="Release to add file",
                                                          fill=TEXT, font=("Segoe UI", 14, "bold"))
        self.drop_overlay.bind("<Configure>", self.draw_drop_overlay)
        root.drop_target_register(DND_FILES)
        root.dnd_bind("<<DropEnter>>", self.drop_action)
        root.dnd_bind("<<DropPosition>>", self.drop_action)
        root.dnd_bind("<<DropLeave>>", self.hide_drop_overlay)
        root.dnd_bind("<<Drop:DND_Files>>", self.drop_source)

        self.update_buttons()
        self.source_button.focus_set()
        root.update_idletasks()
        min_width = max(px(590), body.winfo_reqwidth())
        min_height = max(px(450), body.winfo_reqheight())
        root.minsize(min_width, min_height)
        root.geometry(f"{max(px(680), min_width)}x{max(px(465), min_height)}")
        root.after(80, self.poll)

    def pixels(self, size):
        return round(size * self.display_scale)

    @staticmethod
    def label(parent, text=None, *, variable=None, bg=BG, color=TEXT, size=10, bold=False, **options):
        return tk.Label(parent, text=text, textvariable=variable, bg=bg, fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"), **options)

    def path_row(self, parent, title, variable, command, top=0):
        self.label(parent, title, bg=PANEL, bold=True).pack(anchor="w", pady=(self.pixels(top), self.pixels(4)))
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x")
        pixel = max(1, self.pixels(1))
        outline = tk.Frame(row, bg=BORDER, padx=pixel, pady=pixel)
        outline.pack(side="left", fill="x", expand=True, padx=(0, self.pixels(8)))
        entry = ttk.Entry(outline, textvariable=variable, state="readonly", style="Path.TEntry")
        entry.pack(fill="x")
        entry.bind("<FocusIn>", lambda _event: outline.configure(bg=MUTED))
        entry.bind("<FocusOut>", lambda _event: outline.configure(bg=BORDER))
        button = ttk.Button(row, text="Browse…", style="Panel.TButton", command=command)
        button.pack(side="right")
        return button

    def choose_source(self):
        selected = open_audio_file(self.root, "Select an audio file", [
            ("Audio files", "*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus *.wma *.aiff"),
            ("All files", "*.*"),
        ])
        if selected:
            self.select_source(selected)

    def drop_action(self, _event):
        if self.process is not None or self.dragging_stem:
            self.hide_drop_overlay()
            return REFUSE_DROP
        if not self.drag_active:
            self.drag_active = True
            self.drop_frame = 0
            self.drop_overlay.place(x=0, y=0, relwidth=1, relheight=1)
            tk.Misc.tkraise(self.drop_overlay)
            self.animate_drop_overlay()
        return COPY

    def animate_drop_overlay(self):
        self.drop_overlay.itemconfigure(self.drop_icon, image=self.drop_frames[self.drop_frame])
        if self.drop_frame + 1 < len(self.drop_frames):
            self.drop_frame += 1
            self.drop_animation = self.root.after(16, self.animate_drop_overlay)
        else:
            self.drop_animation = None

    def draw_drop_overlay(self, _event=None):
        overlay = self.drop_overlay
        width, height = overlay.winfo_width(), overlay.winfo_height()
        x, y = width / 2, height / 2 - self.pixels(22)
        margin = self.pixels(14)
        overlay.coords(self.drop_border, margin, margin, width - margin, height - margin)
        overlay.coords(self.drop_icon, x, y)
        overlay.coords(self.drop_message, x, y + self.pixels(82))

    def hide_drop_overlay(self, _event=None):
        if self.drop_animation is not None:
            self.root.after_cancel(self.drop_animation)
            self.drop_animation = None
        self.drag_active = False
        self.drop_overlay.place_forget()

    def drop_source(self, event):
        self.hide_drop_overlay()
        if self.process is not None or self.dragging_stem:
            return REFUSE_DROP
        paths = self.root.tk.splitlist(event.data)
        if len(paths) != 1:
            self.state.set("Drop one audio file at a time")
            return REFUSE_DROP
        return COPY if self.select_source(paths[0]) else REFUSE_DROP

    def select_source(self, selected):
        source = Path(selected)
        if not source.is_file():
            self.state.set("Select an audio file")
            return False
        self.source.set(os.path.normpath(source))
        # Leave room for the stem suffix within Windows' filename component limit.
        self.track_name = source.stem.encode("utf-16-le")[:460].decode("utf-16-le", errors="ignore")
        self.set_output_parent(documents_folder())
        self.clear_result()
        self.set_progress(0)
        self.state.set("")
        self.update_buttons()
        return True

    def choose_output(self):
        selected = filedialog.askdirectory(parent=self.root,
                                           title="Choose where to save the stems",
                                           initialdir=self.destination.parent)
        if selected:
            self.set_output_parent(Path(selected))

    def set_output_parent(self, parent):
        self.destination = parent / f"{self.track_name} stems"
        self.output.set(str(self.destination))

    def update_buttons(self):
        busy = self.process is not None
        self.source_button.configure(state="disabled" if busy else "normal")
        self.output_button.configure(state="disabled" if busy or not self.source.get() else "normal")
        self.start_button.configure(state="disabled" if busy or not self.source.get() else "normal")
        self.result_button.configure(state="normal" if self.result and not busy else "disabled")
        self.model_menu.configure(state="disabled" if busy else "readonly")

    def set_progress(self, value=None):
        self.progress.stop()
        if value is None:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        else:
            self.progress.configure(mode="determinate", value=value)

    def start(self):
        self.hide_drop_overlay()
        source = Path(self.source.get())
        output = self.destination
        model = MODEL_CHOICES[self.model.get()]
        self.expected_outputs = MODEL_STEMS[model]
        self.clear_result()
        try:
            if not source.is_file():
                raise FileNotFoundError("The selected audio file was not found.")
            if not PYTHON.is_file() or not WORKER.is_file():
                raise FileNotFoundError("The runtime folder must be next to Stem Splitter.exe.")
            output.parent.mkdir(parents=True, exist_ok=True)
            self.staging = tempfile.TemporaryDirectory(prefix=".demucs-", dir=output.parent, ignore_cleanup_errors=True)
            command = [str(PYTHON), "-u", str(WORKER), str(source), self.staging.name, str(CACHE),
                       "--model", model, "--wait-for-start"]
            self.process, self.worker_job = start_worker(command)
        except OSError as exc:
            if self.staging:
                self.staging.cleanup()
                self.staging = None
            self.update_buttons()
            self.show_error(str(exc))
            return

        self.worker_error = ""
        self.processing_device = None
        self.state.set("Starting…")
        self.set_progress()
        self.update_buttons()
        threading.Thread(target=read_worker, args=(self.process, self.events), daemon=True).start()

    def poll(self):
        while not self.events.empty():
            event = self.events.get_nowait()
            if "exit" in event:
                self.finish(event["exit"])
                if self.closing:
                    return
            elif "error" in event:
                self.worker_error = event["error"]
            elif not self.closing:
                if "status" in event:
                    self.state.set(event["status"])
                    self.set_progress()
                    if "device" in event:
                        self.processing_device = event["device"]
                elif "progress" in event:
                    self.set_progress(event["progress"])
        if self.player.source is not None:
            try:
                self.player.poll()
                if self.player.state != self.displayed_playback_state:
                    self.update_playback_buttons()
                if not self.seeking:
                    self.update_playhead(self.player.position())
            except OSError as exc:
                self.playback_error(exc)
        self.root.after(80, self.poll)

    def finish(self, returncode):
        self.process = None
        self.worker_job.close()
        self.worker_job = None
        error = ""
        try:
            if not self.closing:
                if returncode:
                    raise RuntimeError(self.worker_error or f"The audio worker exited with code {returncode}.")
                staging = Path(self.staging.name)
                if {file.stem for file in staging.glob("*.wav") if file.stat().st_size > 44} != set(self.expected_outputs):
                    raise RuntimeError("Demucs did not save all requested WAV files.")
                for stem in self.expected_outputs:
                    (staging / f"{stem}.wav").rename(staging / self.stem_filename(stem))
                destination = self.destination
                index = 1
                while True:
                    result = destination if index == 1 else destination.with_name(f"{destination.name} ({index})")
                    try:
                        self.result = staging.rename(result)
                        break
                    except FileExistsError:
                        index += 1
        except (OSError, RuntimeError) as exc:
            error = str(exc)
        finally:
            self.staging.cleanup()
            self.staging = None

        if self.closing:
            self.root.destroy()
            return
        self.update_buttons()
        self.set_progress(100 if self.result else 0)
        if self.result:
            self.output.set(str(self.result))
            device = f" · {self.processing_device}" if self.processing_device else ""
            self.state.set(f"Done · Saved {len(self.expected_outputs)} stems{device}")
            self.show_stems({stem: self.result / self.stem_filename(stem) for stem in self.expected_outputs})
        else:
            self.show_error(error)

    def show_error(self, detail):
        self.state.set("Couldn't split the track")
        messagebox.showerror("Stem Splitter", detail, parent=self.root)

    def stem_filename(self, stem):
        label = "vocal" if stem == "vocals" else stem
        return f"{self.track_name} - {label}.wav"

    def start_stem_drag(self, path):
        self.card_press = None
        paths = (path,)
        if self.stem_selection[path].get():
            paths = tuple(selected for selected, checked in self.stem_selection.items() if checked.get())
        if any(not source.is_file() for source in paths):
            self.state.set("A WAV selected for export is missing.")
            return REFUSE_DROP
        self.dragging_stem = True
        return COPY, DND_FILES, tuple(map(str, paths))

    def end_stem_drag(self, _event):
        self.dragging_stem = False

    def press_stem_card(self, event, path):
        self.card_press = (path, event.x_root, event.y_root)

    def release_stem_card(self, event, path):
        press, self.card_press = self.card_press, None
        if press is not None and press[0] == path and not self.dragging_stem:
            if max(abs(event.x_root - press[1]), abs(event.y_root - press[2])) <= self.pixels(4):
                self.play_stem(path)

    def toggle_stem_selection(self):
        selected = not all(checked.get() for checked in self.stem_selection.values())
        for checked in self.stem_selection.values():
            checked.set(selected)
        self.update_stem_selection()

    def update_stem_selection(self):
        all_selected = self.stem_selection and all(checked.get() for checked in self.stem_selection.values())
        self.select_stems_button.configure(text="Clear selection" if all_selected else "Select all")

    def show_stems(self, files):
        px = self.pixels
        for index, (stem, path) in enumerate(files.items()):
            row = RoundedPanel(self.stem_columns[index % 2], outside=PANEL, fill=FIELD,
                               radius=px(11), padx=px(10), pady=px(4))
            row.pack(fill="x", pady=(px(5), 0))
            self.stem_cards[path] = row
            controls = tk.Frame(row.content, bg=FIELD)
            controls.pack(fill="x")
            checked = tk.BooleanVar(value=False)
            self.stem_selection[path] = checked
            checkbox = ttk.Checkbutton(controls, variable=checked, style="Stem.TCheckbutton",
                                       command=self.update_stem_selection)
            checkbox.pack(side="left", padx=(0, px(8)))
            icon = stem_icon(controls, ASSETS / "stem-icons" / f"{stem}.png", px(24), FIELD)
            icon.pack(side="left", padx=(0, px(7)))
            name = self.label(controls, stem.capitalize(), bg=FIELD)
            name.pack(side="left")
            button = ttk.Button(controls, text="Play", image=self.play_photo, style="StemPlay.TButton",
                                command=lambda source=path: self.play_stem(source))
            button.pack(side="right")
            self.play_buttons[path] = button
            for handle in (row, row.surface, row.content, controls, icon, name):
                handle.configure(cursor="hand2")
                handle.bind("<ButtonPress-1>", lambda event, source=path: self.press_stem_card(event, source))
                handle.bind("<ButtonRelease-1>", lambda event, source=path: self.release_stem_card(event, source))
                handle.drag_source_register(1, DND_FILES)
                handle.dnd_bind("<<DragInitCmd>>", lambda _event, source=path: self.start_stem_drag(source))
                handle.dnd_bind("<<DragEndCmd>>", self.end_stem_drag)
        self.update_playback_buttons()
        self.update_stem_selection()
        self.playback.pack(fill="x", pady=(px(12), 0))
        self.fit_playback()

    def clear_result(self):
        self.stop_playback()
        self.result = None
        if self.play_buttons:
            self.playback.pack_forget()
            for row in self.stem_cards.values():
                row.destroy()
            self.play_buttons.clear()
            self.stem_cards.clear()
            self.stem_selection.clear()
            self.fit_playback()

    def fit_playback(self):
        self.root.update_idletasks()
        width, _ = self.root.minsize()
        self.root.minsize(width, max(self.pixels(450), self.body.winfo_reqheight()))

    def play_stem(self, path):
        self.seeking = False
        show_timeline = self.player.source != path
        try:
            self.player.play(path)
            self.timeline.set_duration(self.player.duration)
            self.playback_clock.configure(width=2 * len(clock_time(self.player.duration)) + 3)
            self.update_playhead(self.player.position())
            if show_timeline:
                self.show_transport(self.stem_cards[path])
        except OSError as exc:
            self.playback_error(exc)
        self.update_playback_buttons()

    def stop_playback(self):
        try:
            self.player.stop()
        except OSError as exc:
            self.playback_error(exc)
        self.reset_timeline()
        self.update_playback_buttons()

    def reset_timeline(self):
        self.seeking = False
        self.card_press = None
        self.timeline.set_duration(0)
        self.update_playhead(0)
        if self.transport.winfo_manager():
            self.transport.pack_forget()
            self.fit_playback()

    def show_transport(self, card):
        self.transport.pack_forget()
        self.transport.pack(in_=card.content, fill="x", pady=(self.pixels(3), 0))
        self.transport.tkraise()
        self.fit_playback()

    def update_playhead(self, position):
        self.playhead.set(position)
        self.playback_time.set(f"{clock_time(position)} / {clock_time(self.player.duration)}")

    def begin_seek(self, event):
        if self.player.source is not None:
            self.timeline.focus_set()
            self.seeking = True
            self.preview_seek(event)
        return "break"

    def preview_seek(self, event):
        if self.seeking:
            self.update_playhead(self.timeline.seconds_at(event.x))
        return "break"

    def end_seek(self, event):
        if self.seeking:
            self.preview_seek(event)
            self.seeking = False
            self.seek_to(self.playhead.get())
        return "break"

    def seek_to(self, position):
        if self.player.source is not None:
            try:
                self.update_playhead(self.player.seek(position))
                self.update_playback_buttons()
            except OSError as exc:
                self.playback_error(exc)
        return "break"

    def update_playback_buttons(self):
        active = self.player.source
        self.displayed_playback_state = state = self.player.state
        active_text = {"paused": "Resume", "playing": "Pause"}.get(state, "Play")
        for path, button in self.play_buttons.items():
            playing = path == active and state == "playing"
            button.configure(text=active_text if path == active else "Play",
                             image=self.pause_photo if playing else self.play_photo)
        self.stop_button.configure(state="normal" if active else "disabled")

    def playback_error(self, error):
        try:
            self.player.stop()
        except OSError:
            pass
        self.reset_timeline()
        self.update_playback_buttons()
        self.state.set("Couldn't play the stem")
        messagebox.showerror("Couldn't play the stem", str(error), parent=self.root)

    def close(self):
        self.hide_drop_overlay()
        self.stop_playback()
        self.progress.stop()
        if self.process:
            self.closing = True
            self.worker_job.close()
            self.state.set("Cancelling…")
        else:
            self.root.destroy()

    def open_result(self):
        try:
            if not self.result or not self.result.is_dir():
                raise FileNotFoundError("The output folder is missing.")
            os.startfile(self.result)
        except OSError as exc:
            messagebox.showerror("Couldn't open the output folder", str(exc), parent=self.root)


if __name__ == "__main__":
    if not FROZEN:
        # The packaged executable gets the same setting from its manifest.
        ctypes.windll.user32.SetProcessDPIAware()
    window = TkinterDnD.Tk()
    window.iconbitmap(default=str(ASSETS / "stem-splitter-taskbar.ico"))
    App(window)
    window.mainloop()
