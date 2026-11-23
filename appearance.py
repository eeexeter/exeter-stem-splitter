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

    def rounded(radius, fill, outline=None, height=None):
        radius = px(radius)
        size = (2 * radius + 3, height or 2 * radius + 3)
        image = Image.new("RGBA", (size[0] * 3, size[1] * 3))
        ImageDraw.Draw(image).rounded_rectangle(
            (0, 0, image.width - 1, image.height - 1), radius=min(radius * 3, image.height // 2),
            fill=fill, outline=outline, width=max(1, px(1)) * 3,
        )
        return photo(image, size)

    def surface(element, radius, states, outline=None):
        normal, *variants = states
        style.element_create(element, "image", rounded(radius, normal, outline),
                             *((state, rounded(radius, fill, border)) for state, fill, border in variants),
                             border=px(radius) + 1, padding=0, sticky="nsew")

    def button(style_name, element, states, outline=None):
        surface(element, 10, states, outline)
        style.layout(style_name, [(element, {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})
        ]})])

    button("TButton", "Rounded.Button", (BUTTON, ("disabled", PANEL, BORDER), ("pressed", "#2c2c2c", BORDER),
                                        ("focus", BUTTON, MUTED), ("active", "#404040", BORDER)), BORDER)
    button("Primary.TButton", "Rounded.PrimaryButton",
           (TEXT, ("disabled", PANEL, BORDER), ("pressed", "#bdbdbd", None),
            ("focus", TEXT, "#a0a0a0"), ("active", "#dedede", None)))
    style.configure("TButton", padding=(px(14), px(8)), foreground=TEXT)
    style.configure("Primary.TButton", foreground=BG, font=("Segoe UI", 10, "bold"))
    style.map("TButton", foreground=[("disabled", "#858585")])
    style.configure("Playback.TButton", padding=(px(9), px(3)))
    style.configure("StemPlay.TButton", padding=(px(9), px(3)))
    for name, background in (("TButton", BG), ("Panel.TButton", PANEL),
                             ("Playback.TButton", PANEL), ("StemPlay.TButton", FIELD)):
        style.configure(name, background=background)
        style.map(name, background=[(state, background) for state in ("active", "pressed", "disabled")])

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

    surface("Rounded.Field", 10, (FIELD, ("focus", FIELD, MUTED), ("disabled", FIELD, BORDER)), BORDER)
    arrow_size = (px(27), px(18))
    arrow = Image.new("RGBA", (3 * arrow_size[0], 3 * arrow_size[1]))
    cx, cy = arrow.width // 2, arrow.height // 2
    v = px(4) * 3
    ImageDraw.Draw(arrow).line(((cx - v, cy - v // 2), (cx, cy + v // 2), (cx + v, cy - v // 2)),
                             fill=MUTED, width=px(2) * 3, joint="curve")
    style.element_create("Rounded.Combobox.downarrow", "image", photo(arrow, arrow_size))
    for name in ("Entry", "Combobox"):
        children = [("Rounded.Combobox.downarrow", {"side": "right", "sticky": ""})] if name == "Combobox" else []
        children.append((f"{name}.padding", {"sticky": "nsew", "children": [
            (f"{name}.textarea", {"sticky": "nsew"})
        ]}))
        style.layout(f"T{name}", [("Rounded.Field", {"sticky": "nsew", "children": children})])
        style.configure(f"T{name}", background=PANEL, foreground=TEXT, fieldbackground=FIELD, padding=(px(11), px(8)),
                        selectbackground=BUTTON, selectforeground=TEXT)
        style.map(f"T{name}", background=[("readonly", PANEL), ("disabled", PANEL)],
                  fieldbackground=[("readonly", FIELD), ("disabled", FIELD)])

    for element, color in (("Rounded.Progressbar.trough", BORDER), ("Rounded.Progressbar.pbar", TEXT)):
        style.element_create(element, "image", rounded(4, color, height=px(8)),
                             border=(px(4), 0), padding=0, sticky="nsew")
    style.layout("Horizontal.TProgressbar", [("Rounded.Progressbar.trough", {"sticky": "nsew", "children": [
        ("Rounded.Progressbar.pbar", {"side": "left", "sticky": "ns"})
    ]})])
    style.configure("Horizontal.TProgressbar", background=BG, thickness=px(8))
    return images
