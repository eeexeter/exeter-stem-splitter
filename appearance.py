from math import cos, pi, sin
import tkinter as tk
from tkinter import ttk

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

    style.configure("TButton", padding=(px(14), px(8)), background=BUTTON, foreground=TEXT,
                    bordercolor=BORDER, lightcolor=BUTTON, darkcolor=BUTTON)
    style.map("TButton", background=[("pressed", "#2c2c2c"), ("active", "#414141")],
              foreground=[("disabled", "#858585")])
    style.configure("Primary.TButton", background=TEXT, foreground=BG,
                    bordercolor=TEXT, lightcolor=TEXT, darkcolor=TEXT,
                    font=("Segoe UI", 10, "bold"))
    style.map("Primary.TButton", background=[("disabled", BUTTON), ("pressed", "#bdbdbd"), ("active", "#dedede")],
              bordercolor=[("disabled", BORDER)])
    for name in ("Playback.TButton", "StemPlay.TButton"):
        style.configure(name, padding=(px(9), px(3)))

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
    style.configure("TCombobox", arrowsize=px(15), arrowcolor=MUTED)
    style.map("TCombobox", background=[("active", "#414141"), ("readonly", BUTTON)],
              arrowcolor=[("disabled", MUTED)])
    style.configure("Horizontal.TProgressbar", background=TEXT, troughcolor=BORDER,
                    bordercolor=BORDER, lightcolor=TEXT, darkcolor=TEXT, thickness=px(7))
    return images
