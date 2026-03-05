# Pixel Art Editor

A lightweight pixel art editor built entirely with Python's standard library — no external dependencies. Just download and run.

![Python](https://img.shields.io/badge/Python-3.8+-blue) ![License](https://img.shields.io/badge/License-MIT-green)

---

## Features

- **Draw & Erase** — left click to paint, right click to erase, drag to paint continuously
- **Bucket Fill** — flood fills any connected region with the active color
- **Eyedropper** — pick any color directly from the canvas
- **Mirror Drawing** — horizontal, vertical, or four-way symmetry while painting
- **Custom Colors** — open the OS color picker and add any color to your palette live
- **Zoom** — scale the canvas from 4px to 48px per cell
- **Grid Toggle** — show or hide the grid for a clean preview
- **Export PNG** — export your art as a properly scaled PNG file, no libraries needed
- **Undo / Redo** — 50-step history
- **Save / Load** — persist your work to a local JSON file

---

## Requirements

- Python 3.8 or higher
- No external packages — uses only the Python standard library (`tkinter`, `json`, `struct`, `zlib`)

---

## Running

```bash
python pixel_art_editor.py
```

---

## Controls

| Action | Input |
|---|---|
| Paint | Left Click / Drag |
| Erase | Right Click / Drag |
| Cycle colors forward | C |
| Cycle colors backward | V |
| Toggle fill tool | F |
| Toggle eyedropper | E |
| Toggle horizontal mirror | X |
| Toggle vertical mirror | Y |
| Toggle grid | G |
| Zoom in | Ctrl+= |
| Zoom out | Ctrl+- |
| Custom color picker | Ctrl+P |
| Export PNG | Ctrl+E |
| Save | Ctrl+S |
| Load | Ctrl+L |
| Undo | Ctrl+Z |
| Redo | Ctrl+Y |
| Clear canvas | Ctrl+R |

---

## Canvas

- Default size: **40 × 24** cells
- Default cell size: **20px** (adjustable via zoom)
- Exports scale with current zoom level

---

## Project Structure

```
pixel-art-editor/
└── pixel_art_editor.py   # entire application, single file
```

---

## License

MIT
