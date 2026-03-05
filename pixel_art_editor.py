"""
Pixel Art Editor - Windowed pixel art editor using Python tkinter.

Controls:
  Left Click         - Paint pixel
  Right Click        - Erase pixel
  C                  - Cycle forward through colors
  V                  - Cycle backward through colors
  Ctrl+Z             - Undo
  Ctrl+Y             - Redo
  Ctrl+S             - Save canvas to file
  Ctrl+L             - Load canvas from file
  Ctrl+R             - Clear canvas
  F                  - Toggle bucket fill tool (flood fill)
  E                  - Toggle eyedropper tool (pick color from canvas)
  X                  - Toggle horizontal mirror (left/right symmetry)
  Y                  - Toggle vertical mirror (top/bottom symmetry)
  Ctrl+P             - Open color picker to add a custom color
  Ctrl+= or Ctrl++   - Zoom in
  Ctrl+-             - Zoom out
  G                  - Toggle grid visibility
  Ctrl+E             - Export canvas as PNG
"""

import tkinter as tk
from tkinter import colorchooser, filedialog
import json
import os
import copy
import struct
import zlib

# --- Configuration ---
CANVAS_WIDTH = 40
CANVAS_HEIGHT = 24
PIXEL_SIZE = 20
PIXEL_SIZE_MIN = 4
PIXEL_SIZE_MAX = 48
PIXEL_SIZE_STEP = 4
SAVE_FILE = "canvas.json"
MAX_UNDO = 50
BACKGROUND_COLOR = "#1e1e1e"
GRID_COLOR = "#2e2e2e"
UI_BG = "#252526"
UI_FG = "#d4d4d4"

# --- Base Color Palette ---
# This is the starting palette. Custom colors added at runtime are appended to a copy of this list.
BASE_PALETTE = [
    ("White",   "#ffffff"),
    ("Red",     "#e05555"),
    ("Orange",  "#e09955"),
    ("Yellow",  "#e0d655"),
    ("Green",   "#55c46e"),
    ("Cyan",    "#55d4d4"),
    ("Blue",    "#5588e0"),
    ("Magenta", "#c455e0"),
    ("Pink",    "#e055a8"),
    ("Brown",   "#8b5e3c"),
    ("Black",   "#111111"),
]


def _write_png(width, height, pixels):
    """
    Build a valid PNG file in memory from a 2D list of (R, G, B) tuples.
    Returns raw bytes that can be written directly to a .png file.
    pixels[row][col] is an (R, G, B) tuple or None for transparent.
    The output PNG uses RGBA color (8 bits per channel).
    """
    def make_chunk(chunk_type, data):
        chunk_len = struct.pack(">I", len(data))
        chunk_data = chunk_type + data
        chunk_crc = struct.pack(">I", zlib.crc32(chunk_data) & 0xFFFFFFFF)
        return chunk_len + chunk_data + chunk_crc

    # PNG signature
    signature = b"\x89PNG\r\n\x1a\n"

    # IHDR chunk: width, height, bit depth, color type (6=RGBA), compression, filter, interlace
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = make_chunk(b"IHDR", ihdr_data)

    # IDAT chunk: raw pixel data, filtered and compressed
    raw_rows = []
    for row in pixels:
        row_bytes = b"\x00"  # filter type: None
        for pixel in row:
            if pixel is None:
                row_bytes += b"\x00\x00\x00\x00"  # transparent
            else:
                r, g, b = pixel
                row_bytes += bytes([r, g, b, 255])  # fully opaque
        raw_rows.append(row_bytes)

    raw_data = b"".join(raw_rows)
    compressed = zlib.compress(raw_data, level=9)
    idat = make_chunk(b"IDAT", compressed)

    # IEND chunk: marks end of PNG file
    iend = make_chunk(b"IEND", b"")

    return signature + ihdr + idat + iend


def _hex_to_rgb(hex_color):
    """Convert a hex color string like '#e05555' to an (R, G, B) tuple."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def empty_canvas():
    return [[None] * CANVAS_WIDTH for _ in range(CANVAS_HEIGHT)]


class PixelArtEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Pixel Art Editor")
        self.root.configure(bg=UI_BG)
        self.root.resizable(False, False)

        self.canvas_data = empty_canvas()
        self.palette = list(BASE_PALETTE)
        self.pixel_size = PIXEL_SIZE
        self.undo_stack = []
        self.redo_stack = []
        self.selected_color_idx = 0
        self.is_painting = False
        self.is_erasing = False
        self.fill_mode = False
        self.eyedropper_mode = False
        self.mirror_x = False
        self.mirror_y = False
        self.show_grid = True

        self._build_ui()
        self._bind_keys()
        self._draw_grid()
        self._update_palette_ui()
        self.grid_btn.config(bg="#1e7f4e", fg="#ffffff")
        self._set_status("Welcome! Paint: Left | Erase: Right | Fill: F | Eyedropper: E | Mirror: X/Y")

    def _build_ui(self):
        # --- Root layout: sidebar col 0, main area col 1 ---
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(self.root, bg="#1a1a1a", width=54, padx=4, pady=8)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)

        main_area = tk.Frame(self.root, bg=UI_BG)
        main_area.grid(row=0, column=1, sticky="nsew")

        # --- Top bar (inside main area) ---
        top_bar = tk.Frame(main_area, bg=UI_BG, pady=6)
        top_bar.pack(fill=tk.X, padx=10)

        tk.Label(top_bar, text="Pixel Art Editor", bg=UI_BG, fg="#569cd6",
                 font=("Consolas", 13, "bold")).pack(side=tk.LEFT)

        self.status_var = tk.StringVar(value="")
        tk.Label(top_bar, textvariable=self.status_var, bg=UI_BG, fg="#9cdcfe",
                 font=("Consolas", 9)).pack(side=tk.RIGHT)

        self.fill_mode_var = tk.StringVar(value="")
        self.mode_indicator = tk.Label(top_bar, textvariable=self.fill_mode_var,
                                       bg=UI_BG, fg="#ce9178", font=("Consolas", 9, "bold"))
        self.mode_indicator.pack(side=tk.RIGHT, padx=10)

        self.mirror_indicator_var = tk.StringVar(value="")
        tk.Label(top_bar, textvariable=self.mirror_indicator_var, bg=UI_BG, fg="#4ec9b0",
                 font=("Consolas", 9, "bold")).pack(side=tk.RIGHT, padx=4)

        self.zoom_var = tk.StringVar(value=f"Zoom: {PIXEL_SIZE}px")
        tk.Label(top_bar, textvariable=self.zoom_var, bg=UI_BG, fg="#dcdcaa",
                 font=("Consolas", 9)).pack(side=tk.RIGHT, padx=8)

        # --- Canvas (inside main area) ---
        self.canvas_frame = tk.Frame(main_area, bg=UI_BG, padx=10, pady=4)
        self.canvas_frame.pack()

        self.canvas = tk.Canvas(
            self.canvas_frame,
            width=CANVAS_WIDTH * self.pixel_size,
            height=CANVAS_HEIGHT * self.pixel_size,
            bg=BACKGROUND_COLOR,
            highlightthickness=1,
            highlightbackground="#3c3c3c",
            cursor="crosshair"
        )
        self.canvas.pack()

        self.pixel_rects = {}
        for row in range(CANVAS_HEIGHT):
            for col in range(CANVAS_WIDTH):
                x1, y1 = col * self.pixel_size, row * self.pixel_size
                x2, y2 = x1 + self.pixel_size, y1 + self.pixel_size
                rect = self.canvas.create_rectangle(
                    x1, y1, x2, y2,
                    fill=BACKGROUND_COLOR, outline=GRID_COLOR, width=1
                )
                self.pixel_rects[(row, col)] = rect

        self.canvas.bind("<ButtonPress-1>", self._on_left_press)
        self.canvas.bind("<ButtonRelease-1>", self._on_left_release)
        self.canvas.bind("<B1-Motion>", self._on_left_drag)
        self.canvas.bind("<ButtonPress-3>", self._on_right_press)
        self.canvas.bind("<ButtonRelease-3>", self._on_right_release)
        self.canvas.bind("<B3-Motion>", self._on_right_drag)

        # --- Palette bar (inside main area) ---
        self.palette_frame = tk.Frame(main_area, bg=UI_BG, padx=10, pady=6)
        self.palette_frame.pack(fill=tk.X)

        tk.Label(self.palette_frame, text="Palette  ", bg=UI_BG, fg=UI_FG,
                 font=("Consolas", 9)).pack(side=tk.LEFT)

        self.palette_buttons = []
        for i, (name, color) in enumerate(self.palette):
            btn = tk.Label(self.palette_frame, bg=color, width=3, height=1,
                           relief="flat", cursor="hand2")
            btn.pack(side=tk.LEFT, padx=2)
            btn.bind("<Button-1>", lambda e, idx=i: self._select_color(idx))
            self._add_tooltip(btn, name)
            self.palette_buttons.append(btn)

        self.color_preview = tk.Label(self.palette_frame, bg=self.palette[0][1],
                                      width=4, height=1, relief="solid", bd=2)
        self.color_preview.pack(side=tk.LEFT, padx=(10, 2))

        self.color_label = tk.Label(self.palette_frame, text=self.palette[0][0],
                                    bg=UI_BG, fg="#9cdcfe", font=("Consolas", 9))
        self.color_label.pack(side=tk.LEFT, padx=4)

        # --- Sidebar tool buttons ---
        SIDEBAR_TOOLS = [
            ("✏️",  "Draw (Left Click)",        None,                    False, None),
            ("🪣",  "Fill (F)",                  self._toggle_fill,       True,  "fill_btn"),
            ("💧",  "Eyedropper (E)",            self._toggle_eyedropper, True,  "eyedropper_btn"),
            ("↔️",  "Mirror Horizontal (X)",     self._toggle_mirror_x,   True,  "mirror_x_btn"),
            ("↕️",  "Mirror Vertical (Y)",       self._toggle_mirror_y,   True,  "mirror_y_btn"),
            ("▦",   "Grid Toggle (G)",           self._toggle_grid,       True,  "grid_btn"),
            ("🔍",  "Zoom In (Ctrl+=)",          self._zoom_in,           False, None),
            ("🔎",  "Zoom Out (Ctrl+-)",         self._zoom_out,          False, None),
            ("💾",  "Save (Ctrl+S)",             self._save,              False, None),
            ("📂",  "Load (Ctrl+L)",             self._load,              False, None),
            ("🖼️", "Export PNG (Ctrl+E)",        self._export_png,        False, None),
            ("↩️",  "Undo (Ctrl+Z)",             self._undo,              False, None),
            ("↪️",  "Redo (Ctrl+Y)",             self._redo,              False, None),
            ("🎨",  "Custom Color (Ctrl+P)",     self._open_color_picker, False, None),
            ("🗑️", "Clear Canvas (Ctrl+R)",     self._clear,             False, None),
        ]
        self._sidebar_btns = {}

        def add_separator():
            tk.Frame(self.sidebar, bg="#3a3a3a", height=1).pack(fill=tk.X, pady=4, padx=6)

        section_breaks = {2, 5, 8, 11}

        for idx, (icon, tooltip, callback, is_toggle, attr) in enumerate(SIDEBAR_TOOLS):
            if idx in section_breaks:
                add_separator()

            cmd = callback if callback else lambda: None
            btn = tk.Label(
                self.sidebar,
                text=icon,
                bg="#1a1a1a",
                fg=UI_FG,
                font=("Segoe UI Emoji", 13),
                width=2,
                pady=5,
                cursor="hand2",
                relief="flat"
            )
            btn.pack(fill=tk.X, padx=4, pady=1)
            btn.bind("<Button-1>", lambda e, c=cmd: c())
            self._add_sidebar_tooltip(btn, tooltip)

            if attr:
                setattr(self, attr, btn)
                self._sidebar_btns[attr] = btn

        # Draw tool highlighted by default
        self.sidebar.winfo_children()[0].config(bg="#2d2d2d", fg="#ffffff")

    def _add_tooltip(self, widget, text):
        tip = None

        def enter(e):
            nonlocal tip
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + 20
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            tk.Label(tip, text=text, bg="#3c3c3c", fg="white",
                     font=("Consolas", 8), padx=4, pady=2).pack()

        def leave(e):
            nonlocal tip
            if tip:
                tip.destroy()
                tip = None

        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def _add_sidebar_tooltip(self, widget, text):
        tip = None

        def enter(e):
            nonlocal tip
            x = widget.winfo_rootx() + widget.winfo_width() + 4
            y = widget.winfo_rooty()
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            tk.Label(tip, text=text, bg="#3c3c3c", fg="white",
                     font=("Consolas", 9), padx=8, pady=4).pack()

        def leave(e):
            nonlocal tip
            if tip:
                tip.destroy()
                tip = None

        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def _bind_keys(self):
        self.root.bind("<KeyPress-c>", lambda e: self._cycle_color(1))
        self.root.bind("<KeyPress-C>", lambda e: self._cycle_color(1))
        self.root.bind("<KeyPress-v>", lambda e: self._cycle_color(-1))
        self.root.bind("<KeyPress-V>", lambda e: self._cycle_color(-1))
        self.root.bind("<KeyPress-f>", lambda e: self._toggle_fill())
        self.root.bind("<KeyPress-F>", lambda e: self._toggle_fill())
        self.root.bind("<KeyPress-e>", lambda e: self._toggle_eyedropper())
        self.root.bind("<KeyPress-E>", lambda e: self._toggle_eyedropper())
        self.root.bind("<KeyPress-x>", lambda e: self._toggle_mirror_x())
        self.root.bind("<KeyPress-X>", lambda e: self._toggle_mirror_x())
        self.root.bind("<KeyPress-y>", lambda e: self._toggle_mirror_y())
        self.root.bind("<KeyPress-Y>", lambda e: self._toggle_mirror_y())
        self.root.bind("<Control-p>", lambda e: self._open_color_picker())
        self.root.bind("<Control-P>", lambda e: self._open_color_picker())
        self.root.bind("<KeyPress-g>", lambda e: self._toggle_grid())
        self.root.bind("<KeyPress-G>", lambda e: self._toggle_grid())
        self.root.bind("<Control-e>", lambda e: self._export_png())
        self.root.bind("<Control-E>", lambda e: self._export_png())
        self.root.bind("<Control-equal>", lambda e: self._zoom_in())
        self.root.bind("<Control-plus>", lambda e: self._zoom_in())
        self.root.bind("<Control-minus>", lambda e: self._zoom_out())
        self.root.bind("<Control-z>", lambda e: self._undo())
        self.root.bind("<Control-Z>", lambda e: self._undo())
        self.root.bind("<Control-y>", lambda e: self._redo())
        self.root.bind("<Control-Y>", lambda e: self._redo())
        self.root.bind("<Control-s>", lambda e: self._save())
        self.root.bind("<Control-S>", lambda e: self._save())
        self.root.bind("<Control-l>", lambda e: self._load())
        self.root.bind("<Control-L>", lambda e: self._load())
        self.root.bind("<Control-r>", lambda e: self._clear())
        self.root.bind("<Control-R>", lambda e: self._clear())

    def _get_cell(self, event):
        col = event.x // self.pixel_size
        row = event.y // self.pixel_size
        if 0 <= row < CANVAS_HEIGHT and 0 <= col < CANVAS_WIDTH:
            return row, col
        return None

    def _paint_cell(self, row, col):
        color = self.palette[self.selected_color_idx][1]
        cells = self._mirror_cells(row, col)
        for r, c in cells:
            if self.canvas_data[r][c] != color:
                self.canvas_data[r][c] = color
                outline = GRID_COLOR if self.show_grid else color
                self.canvas.itemconfig(self.pixel_rects[(r, c)], fill=color, outline=outline)

    def _erase_cell(self, row, col):
        cells = self._mirror_cells(row, col)
        for r, c in cells:
            if self.canvas_data[r][c] is not None:
                self.canvas_data[r][c] = None
                outline = GRID_COLOR if self.show_grid else BACKGROUND_COLOR
                self.canvas.itemconfig(self.pixel_rects[(r, c)],
                                       fill=BACKGROUND_COLOR, outline=outline)

    def _mirror_cells(self, row, col):
        cells = {(row, col)}
        if self.mirror_x:
            cells.add((row, CANVAS_WIDTH - 1 - col))
        if self.mirror_y:
            cells.add((CANVAS_HEIGHT - 1 - row, col))
        if self.mirror_x and self.mirror_y:
            cells.add((CANVAS_HEIGHT - 1 - row, CANVAS_WIDTH - 1 - col))
        return cells

    def _on_left_press(self, event):
        cell = self._get_cell(event)
        if not cell:
            return
        if self.eyedropper_mode:
            self._pick_color(*cell)
        elif self.fill_mode:
            self._push_undo()
            self._flood_fill(*cell)
        else:
            self._push_undo()
            self.is_painting = True
            self._paint_cell(*cell)

    def _on_left_release(self, event):
        self.is_painting = False

    def _on_left_drag(self, event):
        if self.is_painting:
            cell = self._get_cell(event)
            if cell:
                self._paint_cell(*cell)

    def _on_right_press(self, event):
        self._push_undo()
        self.is_erasing = True
        cell = self._get_cell(event)
        if cell:
            self._erase_cell(*cell)

    def _on_right_release(self, event):
        self.is_erasing = False

    def _on_right_drag(self, event):
        if self.is_erasing:
            cell = self._get_cell(event)
            if cell:
                self._erase_cell(*cell)

    def _toggle_fill(self):
        self.fill_mode = not self.fill_mode
        if self.fill_mode:
            self.fill_btn.config(bg="#0e639c", fg="#ffffff")
            self.fill_mode_var.set("[FILL MODE]")
            self.canvas.config(cursor="tcross")
            self._set_status("Fill mode ON. Click a region to flood fill.")
        else:
            self.fill_btn.config(bg="#1a1a1a", fg=UI_FG)
            self.fill_mode_var.set("")
            self.canvas.config(cursor="crosshair")
            self._set_status("Fill mode OFF.")

    def _flood_fill(self, start_row, start_col):
        target_color = self.canvas_data[start_row][start_col]
        fill_color = self.palette[self.selected_color_idx][1]

        if target_color == fill_color:
            return

        queue = [(start_row, start_col)]
        visited = set()
        visited.add((start_row, start_col))

        while queue:
            row, col = queue.pop(0)
            self.canvas_data[row][col] = fill_color
            self.canvas.itemconfig(self.pixel_rects[(row, col)],
                                   fill=fill_color, outline=GRID_COLOR)

            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = row + dr, col + dc
                if (0 <= nr < CANVAS_HEIGHT and 0 <= nc < CANVAS_WIDTH
                        and (nr, nc) not in visited
                        and self.canvas_data[nr][nc] == target_color):
                    visited.add((nr, nc))
                    queue.append((nr, nc))

    def _toggle_eyedropper(self):
        self.eyedropper_mode = not self.eyedropper_mode
        if self.eyedropper_mode:
            if self.fill_mode:
                self._toggle_fill()
            self.eyedropper_btn.config(bg="#6a0dad", fg="#ffffff")
            self.fill_mode_var.set("[EYEDROPPER]")
            self.canvas.config(cursor="dotbox")
            self._set_status("Eyedropper ON. Click any painted cell to pick its color.")
        else:
            self.eyedropper_btn.config(bg="#1a1a1a", fg=UI_FG)
            self.fill_mode_var.set("")
            self.canvas.config(cursor="crosshair")
            self._set_status("Eyedropper OFF.")

    def _pick_color(self, row, col):
        picked = self.canvas_data[row][col]
        if picked is None:
            self._set_status("No color on that cell.")
            return

        for i, (name, hex_color) in enumerate(self.palette):
            if hex_color == picked:
                self.selected_color_idx = i
                self._update_palette_ui()
                self._toggle_eyedropper()
                self._set_status(f"Picked: {name}")
                return

        self._set_status(f"Color {picked} not in palette.")
        self._toggle_eyedropper()

    def _toggle_mirror_x(self):
        self.mirror_x = not self.mirror_x
        self._update_mirror_indicator()
        state = "ON" if self.mirror_x else "OFF"
        self.mirror_x_btn.config(bg="#1e7f4e" if self.mirror_x else "#1a1a1a",
                                  fg="#ffffff" if self.mirror_x else UI_FG)
        self._set_status(f"Horizontal mirror {state}.")

    def _toggle_mirror_y(self):
        self.mirror_y = not self.mirror_y
        self._update_mirror_indicator()
        state = "ON" if self.mirror_y else "OFF"
        self.mirror_y_btn.config(bg="#1e7f4e" if self.mirror_y else "#1a1a1a",
                                  fg="#ffffff" if self.mirror_y else UI_FG)
        self._set_status(f"Vertical mirror {state}.")

    def _update_mirror_indicator(self):
        parts = []
        if self.mirror_x:
            parts.append("H")
        if self.mirror_y:
            parts.append("V")
        if parts:
            self.mirror_indicator_var.set(f"[MIRROR: {'+'.join(parts)}]")
        else:
            self.mirror_indicator_var.set("")

    def _toggle_grid(self):
        self.show_grid = not self.show_grid
        for row in range(CANVAS_HEIGHT):
            for col in range(CANVAS_WIDTH):
                color = self.canvas_data[row][col]
                fill = color if color else BACKGROUND_COLOR
                outline = GRID_COLOR if self.show_grid else fill
                self.canvas.itemconfig(self.pixel_rects[(row, col)], outline=outline)
        label = "ON" if self.show_grid else "OFF"
        self.grid_btn.config(
            bg="#1e7f4e" if self.show_grid else "#1a1a1a",
            fg="#ffffff" if self.show_grid else UI_FG
        )
        self._set_status(f"Grid {label}.")

    def _zoom_in(self):
        if self.pixel_size < PIXEL_SIZE_MAX:
            self.pixel_size += PIXEL_SIZE_STEP
            self._apply_zoom()
        else:
            self._set_status("Maximum zoom reached.")

    def _zoom_out(self):
        if self.pixel_size > PIXEL_SIZE_MIN:
            self.pixel_size -= PIXEL_SIZE_STEP
            self._apply_zoom()
        else:
            self._set_status("Minimum zoom reached.")

    def _apply_zoom(self):
        new_w = CANVAS_WIDTH * self.pixel_size
        new_h = CANVAS_HEIGHT * self.pixel_size
        self.canvas.config(width=new_w, height=new_h)

        for row in range(CANVAS_HEIGHT):
            for col in range(CANVAS_WIDTH):
                x1 = col * self.pixel_size
                y1 = row * self.pixel_size
                x2 = x1 + self.pixel_size
                y2 = y1 + self.pixel_size
                self.canvas.coords(self.pixel_rects[(row, col)], x1, y1, x2, y2)

        self.zoom_var.set(f"Zoom: {self.pixel_size}px")
        self._set_status(f"Zoom: {self.pixel_size}px per cell.")

    def _open_color_picker(self):
        result = colorchooser.askcolor(
            title="Pick a custom color",
            initialcolor=self.palette[self.selected_color_idx][1]
        )
        if result is None or result[1] is None:
            return

        hex_color = result[1].lower()

        for i, (name, existing) in enumerate(self.palette):
            if existing == hex_color:
                self.selected_color_idx = i
                self._update_palette_ui()
                self._set_status(f"Color already in palette: {name}")
                return

        custom_name = f"Custom {hex_color}"
        self.palette.append((custom_name, hex_color))
        new_idx = len(self.palette) - 1

        btn = tk.Label(self.palette_frame, bg=hex_color, width=3, height=1,
                       relief="flat", cursor="hand2")
        btn.pack(side=tk.LEFT, before=self.color_preview, padx=2)
        btn.bind("<Button-1>", lambda e, idx=new_idx: self._select_color(idx))
        self._add_tooltip(btn, custom_name)
        self.palette_buttons.append(btn)

        self.selected_color_idx = new_idx
        self._update_palette_ui()
        self._set_status(f"Custom color added: {hex_color}")

    def _export_png(self):
        filepath = filedialog.asksaveasfilename(
            title="Export as PNG",
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png"), ("All Files", "*.*")],
            initialfile="pixel_art.png"
        )
        if not filepath:
            return

        export_pixel_size = max(1, self.pixel_size)
        img_width = CANVAS_WIDTH * export_pixel_size
        img_height = CANVAS_HEIGHT * export_pixel_size

        pixels = []
        for row in range(CANVAS_HEIGHT):
            for _ in range(export_pixel_size):
                pixel_row = []
                for col in range(CANVAS_WIDTH):
                    color = self.canvas_data[row][col]
                    rgb = _hex_to_rgb(color) if color else None
                    for _ in range(export_pixel_size):
                        pixel_row.append(rgb)
                pixels.append(pixel_row)

        png_bytes = _write_png(img_width, img_height, pixels)

        try:
            with open(filepath, "wb") as f:
                f.write(png_bytes)
            self._set_status(f"Exported to {os.path.basename(filepath)}")
        except Exception as e:
            self._set_status(f"Export failed: {e}")

    def _select_color(self, idx):
        self.selected_color_idx = idx
        self._update_palette_ui()

    def _cycle_color(self, direction):
        self.selected_color_idx = (self.selected_color_idx + direction) % len(self.palette)
        self._update_palette_ui()
        self._set_status(f"Color: {self.palette[self.selected_color_idx][0]}")

    def _update_palette_ui(self):
        for i, btn in enumerate(self.palette_buttons):
            btn.config(relief="solid" if i == self.selected_color_idx else "flat",
                       bd=2 if i == self.selected_color_idx else 0)
        name, color = self.palette[self.selected_color_idx]
        self.color_preview.config(bg=color)
        self.color_label.config(text=name)

    def _draw_grid(self):
        outline = GRID_COLOR if self.show_grid else BACKGROUND_COLOR
        for row in range(CANVAS_HEIGHT):
            for col in range(CANVAS_WIDTH):
                self.canvas.itemconfig(self.pixel_rects[(row, col)],
                                       fill=BACKGROUND_COLOR, outline=outline)

    def _redraw_canvas(self):
        for row in range(CANVAS_HEIGHT):
            for col in range(CANVAS_WIDTH):
                color = self.canvas_data[row][col]
                fill = color if color else BACKGROUND_COLOR
                outline = GRID_COLOR if self.show_grid else fill
                self.canvas.itemconfig(self.pixel_rects[(row, col)],
                                       fill=fill, outline=outline)

    def _push_undo(self):
        self.undo_stack.append(copy.deepcopy(self.canvas_data))
        if len(self.undo_stack) > MAX_UNDO:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _undo(self):
        if self.undo_stack:
            self.redo_stack.append(copy.deepcopy(self.canvas_data))
            self.canvas_data = self.undo_stack.pop()
            self._redraw_canvas()
            self._set_status("Undone.")
        else:
            self._set_status("Nothing to undo.")

    def _redo(self):
        if self.redo_stack:
            self.undo_stack.append(copy.deepcopy(self.canvas_data))
            self.canvas_data = self.redo_stack.pop()
            self._redraw_canvas()
            self._set_status("Redone.")
        else:
            self._set_status("Nothing to redo.")

    def _save(self):
        try:
            with open(SAVE_FILE, "w") as f:
                json.dump({"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT,
                           "canvas": self.canvas_data}, f)
            self._set_status(f"Saved to {SAVE_FILE}")
        except Exception as e:
            self._set_status(f"Save failed: {e}")

    def _load(self):
        if not os.path.exists(SAVE_FILE):
            self._set_status("No save file found.")
            return
        try:
            with open(SAVE_FILE, "r") as f:
                data = json.load(f)
            loaded = data.get("canvas", empty_canvas())
            if len(loaded) != CANVAS_HEIGHT or any(len(r) != CANVAS_WIDTH for r in loaded):
                self._set_status("Canvas dimensions mismatch, load aborted.")
                return
            self._push_undo()
            self.canvas_data = loaded
            self._redraw_canvas()
            self._set_status(f"Loaded from {SAVE_FILE}")
        except Exception as e:
            self._set_status(f"Load failed: {e}")

    def _clear(self):
        self._push_undo()
        self.canvas_data = empty_canvas()
        self._redraw_canvas()
        self._set_status("Canvas cleared.")

    def _set_status(self, msg):
        self.status_var.set(msg)
        self.root.after(3000, lambda: self.status_var.set(""))


if __name__ == "__main__":
    root = tk.Tk()
    app = PixelArtEditor(root)
    root.mainloop()