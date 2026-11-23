from math import cos, pi, sin
import tkinter as tk
from tkinter import font, ttk

from PIL import Image, ImageDraw, ImageTk


BG = "#181818"
PANEL = "#292929"
FIELD = "#202020"
TEXT = "#f1f1f1"
MUTED = "#aeaeae"
BORDER = "#3e3e3e"
BUTTON = "#353535"


class RoundedPanel(tk.Frame):
    def __init__(self, parent, *, outside, fill, radius, padx, pady, outline=None):
        super().__init__(parent, bg=outside)
        self.radius = radius
        self.surface = tk.Canvas(self, bg=outside, borderwidth=0, highlightthickness=0)
        self.surface.place(relwidth=1, relheight=1)
        self.outline = bool(outline)
        self.shape = self.surface.create_polygon(0, 0, 0, 0, 0, 0, fill=fill, outline=outline or "")
        self.content = tk.Frame(self, bg=fill)
        self.content.pack(fill="both", expand=True, padx=padx, pady=pady)
        self.surface.bind("<Configure>", self.redraw)

    def redraw(self, event):
        inset = 0.5 if self.outline else 0
        width, height = event.width - inset, event.height - inset
        r = min(self.radius, width / 2, height / 2)
        corners = ((width - r, inset + r), (width - r, height - r),
                   (inset + r, height - r), (inset + r, inset + r))
        points = []
        for corner, (x, y) in enumerate(corners):
            for segment in range(9):
                angle = (corner - 1 + segment / 8) * pi / 2
                points.extend((x + r * cos(angle), y + r * sin(angle)))
        self.surface.coords(self.shape, *points)


def configure_theme(root, px):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=BG)
    images = []

    def photo(image, size):
        result = ImageTk.PhotoImage(image.resize(size, Image.Resampling.LANCZOS), master=root)
        images.append(result)
        return result

    normal_font = font.Font(root=root, family="Segoe UI", size=10)
    bold_font = font.Font(root=root, family="Segoe UI", size=10, weight="bold")

    def button_surface(name, text, backdrop, *, compact=False, primary=False, icon=False):
        button_font = bold_font if primary else normal_font
        width = px(20) if icon else button_font.measure(text)
        height = px(20) if icon else button_font.metrics("linespace")
        size = (width + 2 * px(9 if compact else 14), height + 2 * px(4 if compact else 8))
        radius = min(px(12 if icon else 10), size[1] // 2)
        normal, pressed, hover = (TEXT, "#bdbdbd", "#dedede") if primary else (BUTTON, "#2c2c2c", "#414141")
        border = None if primary else BORDER

        def button_photo(fill, outline):
            # Draw each fixed-size button once. Tk can blit it without stretching a texture.
            image = Image.new("RGB", (size[0] * 3, size[1] * 3), backdrop)
            ImageDraw.Draw(image).rounded_rectangle(
                (0, 0, image.width - 1, image.height - 1), radius=radius * 3,
                fill=fill, outline=outline, width=max(1, px(1)) * 3,
            )
            return photo(image, size)

        element = f"Rounded.{name}.border"
        style.element_create(element, "image", button_photo(normal, border),
                             ("disabled", button_photo(PANEL, BORDER)),
                             ("pressed", button_photo(pressed, border)),
                             ("focus", button_photo(normal, MUTED)),
                             ("active", button_photo(hover, border)),
                             padding=0, sticky="")
        layout = [(element, {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})
        ]})]
        style.layout(name, layout)
        style.configure(name, background=backdrop)
        style.map(name, background=[(state, backdrop) for state in ("disabled", "active", "pressed")])

    button_surface("Primary.TButton", "Split track", BG, primary=True)
    button_surface("Output.TButton", "Open output folder", BG)
    button_surface("Panel.TButton", "Browse…", PANEL)
    button_surface("Playback.TButton", "Stop", PANEL, compact=True)
    button_surface("Selection.TButton", "Clear selection", PANEL, compact=True)
    button_surface("StemPlay.TButton", "", FIELD, compact=True, icon=True)
    style.configure("TButton", padding=0, width=0, foreground=TEXT, font=("Segoe UI", 10))
    style.map("TButton", foreground=[("disabled", "#858585")])
    style.configure("Primary.TButton", foreground=BG, font=("Segoe UI", 10, "bold"))

    def checkmark(selected, outline):
        size = px(15)
        image = Image.new("RGBA", (size * 3, size * 3))
        draw = ImageDraw.Draw(image)
        end = image.width - 1
        draw.rounded_rectangle((0, 0, end, end), radius=px(4) * 3,
                               fill=TEXT if selected else FIELD, outline=outline, width=3)
        if selected:
            draw.line(((end * .23, end * .49), (end * .41, end * .66), (end * .75, end * .32)),
                      fill=BG, width=max(3, px(2) * 3), joint="curve")
        return photo(image, (size, size))

    style.element_create("Rounded.Checkbutton.indicator", "image", checkmark(False, BORDER),
                         ("selected", "focus", checkmark(True, MUTED)),
                         ("selected", checkmark(True, TEXT)),
                         ("focus", checkmark(False, TEXT)),
                         ("active", checkmark(False, MUTED)))
    style.layout("Stem.TCheckbutton", [("Rounded.Checkbutton.indicator", {"sticky": "w"})])
    style.configure("Stem.TCheckbutton", background=FIELD)

    for name in ("TEntry", "TCombobox"):
        style.configure(name, background=BUTTON, foreground=TEXT, fieldbackground=FIELD,
                        padding=(px(11), px(8)), bordercolor=BORDER, lightcolor=FIELD, darkcolor=FIELD,
                        selectbackground=BUTTON, selectforeground=TEXT)
        style.map(name, fieldbackground=[("readonly", FIELD), ("disabled", FIELD)],
                  bordercolor=[("focus", MUTED)])
    style.layout("Path.TEntry", [("Entry.padding", {"sticky": "nsew", "children": [
        ("Entry.textarea", {"sticky": "nsew"})
    ]})])
    style.configure("Path.TEntry", background=FIELD)
    style.map("Path.TEntry", background=[("readonly", FIELD), ("disabled", FIELD)])
    style.configure("TCombobox", arrowsize=px(15), arrowcolor=MUTED)
    style.map("TCombobox", background=[("active", "#414141"), ("readonly", BUTTON)],
              arrowcolor=[("disabled", MUTED)],
              selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", TEXT)])
    style.configure("Horizontal.TProgressbar", background=TEXT, troughcolor=BORDER,
                    bordercolor=BORDER, lightcolor=TEXT, darkcolor=TEXT, thickness=px(7))
    return images
