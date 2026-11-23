import tkinter as tk

from PIL import Image, ImageOps, ImageTk


ICON_FILL = {"bass": 0.96, "guitar": 0.88}


def stem_icon(parent, path, size, background):
    with Image.open(path) as original:
        fill = ICON_FILL.get(path.stem)
        if fill:
            # Scale the artwork within the original icon slot.
            bounds = original.getchannel("A").getbbox()
            target = max(1, round(size * fill))
            artwork = ImageOps.contain(original.crop(bounds), (target, target), Image.Resampling.LANCZOS)
            image = Image.new("RGBA", (size, size))
            image.paste(artwork, ((size - artwork.width) // 2, (size - artwork.height) // 2))
        else:
            image = original.resize((size, size), Image.Resampling.LANCZOS)
    photo = ImageTk.PhotoImage(image, master=parent)
    icon = tk.Label(parent, image=photo, bg=background, borderwidth=0, highlightthickness=0,
                    padx=0, pady=0)
    icon.image = photo
    return icon
