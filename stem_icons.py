import tkinter as tk

from PIL import Image, ImageTk


def stem_icon(parent, path, size, background):
    with Image.open(path) as original:
        image = original.resize((size, size), Image.Resampling.LANCZOS)
    photo = ImageTk.PhotoImage(image, master=parent)
    icon = tk.Label(parent, image=photo, bg=background, borderwidth=0, highlightthickness=0,
                    padx=0, pady=0)
    icon.image = photo
    return icon
