"""Dark creator-studio interface for configuring and monitoring renders."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Callable

from config import (
    AUDIO_FILE,
    AUDIO_SENSITIVITY,
    BACKGROUND_MODES,
    BG_MODE,
    BG_VIDEO_PATH,
    COLOR_THEMES,
    DYNAMICS_LEVEL,
    OUTPUT_FILE,
    PROJECT_NAME,
    PULSE_STRENGTH,
    RING_COUNT,
    SPEED_PRESETS,
    VIBRATION_STRENGTH,
    VISIBLE_RINGS,
    WATERMARK_TEXT,
)

_BG = "#0f111a"
_CARD = "#171b27"
_CARD_ALT = "#1c2130"
_TEXT = "#eef0fa"
_MUTED = "#9ca5bb"
_ACCENT = "#9b6bff"
_BORDER = "#2b3142"
_DYNAMICS = tuple(SPEED_PRESETS)
_THEME_COLOR_KEYS = ("ring_inner", "ring_outer", "ball")


@dataclass(frozen=True)
class StudioSettings:
    audio_path: str | None
    duration: float
    use_track_length: bool
    ring_count: int
    visible_rings: int
    ball_speed: float
    gravity: float
    dynamics_level: str
    pulse_strength: float
    vibration_strength: float
    audio_sensitivity: float
    background_mode: str
    background_video_path: str
    watermark_text: str
    watermark_opacity: float
    theme_name: str
    theme_colors: dict[str, tuple[int, int, int]]
    asmr_hits: bool
    output_path: str


RenderFunction = Callable[
    [StudioSettings, Callable[[int, int, float, float], None]], None
]


def _hex_color(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _parse_hex(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"Invalid color value: {value}")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def launch_menu(render_function: RenderFunction) -> None:
    """Run the studio window and render in a worker while keeping the UI live."""
    root = tk.Tk()
    root.title(f"{PROJECT_NAME} Studio")
    root.configure(bg=_BG)
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = max(640, min(1150, screen_width - 80))
    window_height = max(600, min(820, screen_height - 100))
    root.minsize(min(940, window_width), min(680, window_height))
    position_x = max(0, (screen_width - window_width) // 2)
    position_y = max(0, (screen_height - window_height) // 2)
    root.geometry(
        f"{window_width}x{window_height}+{position_x}+{position_y}"
    )
    root.resizable(True, True)
    root.option_add("*Font", ("Segoe UI", 10))
    root.option_add("*TCombobox*Listbox.background", "#1e2235")
    root.option_add("*TCombobox*Listbox.foreground", "#ffffff")

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        "Studio.Horizontal.TProgressbar",
        troughcolor=_CARD_ALT,
        background=_ACCENT,
        bordercolor=_CARD_ALT,
        lightcolor=_ACCENT,
        darkcolor=_ACCENT,
    )
    style.configure(
        "Studio.Vertical.TScrollbar",
        troughcolor=_BG,
        background=_CARD_ALT,
        bordercolor=_BG,
        arrowcolor=_TEXT,
    )
    style.configure(
        "Studio.TCombobox",
        fieldbackground="#1e2235",
        background="#1e2235",
        foreground="#ffffff",
        selectbackground="#1e2235",
        selectforeground="#ffffff",
        arrowcolor="#ffffff",
        bordercolor=_BORDER,
    )
    style.map(
        "Studio.TCombobox",
        fieldbackground=[("readonly", "#1e2235"), ("disabled", _CARD_ALT)],
        foreground=[("readonly", "#ffffff"), ("disabled", _MUTED)],
        selectbackground=[("readonly", "#1e2235")],
        selectforeground=[("readonly", "#ffffff")],
        background=[("active", "#292f45")],
    )

    footer = tk.Frame(root, bg=_BG, padx=22, pady=10)
    footer.pack(side="bottom", fill="x")

    audio_path: str | None = AUDIO_FILE if Path(AUDIO_FILE).is_file() else None
    audio_label = tk.StringVar(
        value=Path(audio_path).name if audio_path else "Тестовый ритм (без аудио)"
    )
    initial_mode = BG_MODE if BG_MODE in {"solid", "transparent", "video_bg", "video_mask"} else "solid"
    mode_labels = {mode: label for label, mode in BACKGROUND_MODES.items()}
    mode_value = tk.StringVar(value=mode_labels[initial_mode])
    background_video_path = tk.StringVar(value=BG_VIDEO_PATH)
    output_value = tk.StringVar(value=str(Path(OUTPUT_FILE).resolve()))
    duration_value = tk.StringVar(value="30 сек")
    track_length_value = tk.BooleanVar(value=False)
    ring_count_value = tk.StringVar(value=str(RING_COUNT))
    visible_value = tk.IntVar(value=VISIBLE_RINGS)
    dynamics_default = (
        "Dynamic" if DYNAMICS_LEVEL == "High" else DYNAMICS_LEVEL
    )
    dynamics_value = tk.StringVar(
        value=dynamics_default if dynamics_default in _DYNAMICS else "Dynamic"
    )
    pulse_value = tk.DoubleVar(value=PULSE_STRENGTH)
    vibration_value = tk.DoubleVar(value=VIBRATION_STRENGTH)
    sensitivity_value = tk.DoubleVar(value=AUDIO_SENSITIVITY)
    watermark_value = tk.StringVar(value=WATERMARK_TEXT)
    opacity_value = tk.DoubleVar(value=0.18)
    theme_value = tk.StringVar(value="Cyberpunk Neon")
    asmr_value = tk.BooleanVar(value=False)
    custom_colors = dict(COLOR_THEMES["Custom"])

    outer = tk.Frame(root, bg=_BG, padx=22, pady=12)
    outer.pack(fill="both", expand=True)
    header = tk.Frame(outer, bg=_BG)
    header.pack(fill="x", pady=(0, 9))
    tk.Label(
        header, text="SONICVORTEX", bg=_BG, fg=_TEXT, font=("Segoe UI", 21, "bold")
    ).pack(anchor="w")
    tk.Label(
        header,
        text="CREATOR STUDIO  /  NEON VIDEO GENERATOR",
        bg=_BG,
        fg=_MUTED,
        font=("Segoe UI", 9, "bold"),
    ).pack(anchor="w", pady=(2, 0))

    cards_area = tk.Frame(outer, bg=_BG)
    cards_area.pack(fill="both", expand=True)
    cards_area.rowconfigure(0, weight=1)
    cards_area.columnconfigure(0, weight=1)
    cards_canvas = tk.Canvas(
        cards_area,
        bg=_BG,
        borderwidth=0,
        highlightthickness=0,
    )
    cards_scrollbar = ttk.Scrollbar(
        cards_area,
        orient="vertical",
        command=cards_canvas.yview,
        style="Studio.Vertical.TScrollbar",
    )
    cards_canvas.configure(yscrollcommand=cards_scrollbar.set)
    cards_canvas.grid(row=0, column=0, sticky="nsew")
    cards_scrollbar.grid(row=0, column=1, sticky="ns")
    grid = tk.Frame(cards_canvas, bg=_BG)
    cards_window = cards_canvas.create_window(
        (0, 0), window=grid, anchor="nw"
    )

    def update_scroll_region(_event: tk.Event) -> None:
        cards_canvas.configure(scrollregion=cards_canvas.bbox("all"))

    def resize_cards(event: tk.Event) -> None:
        cards_canvas.itemconfigure(cards_window, width=event.width)

    def scroll_cards(event: tk.Event) -> str | None:
        pointer_x = root.winfo_pointerx()
        pointer_y = root.winfo_pointery()
        canvas_left = cards_canvas.winfo_rootx()
        canvas_top = cards_canvas.winfo_rooty()
        if not (
            canvas_left <= pointer_x < canvas_left + cards_canvas.winfo_width()
            and canvas_top <= pointer_y < canvas_top + cards_canvas.winfo_height()
        ):
            return None
        if getattr(event, "num", None) == 4:
            cards_canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            cards_canvas.yview_scroll(1, "units")
        else:
            delta = int(getattr(event, "delta", 0))
            if delta:
                cards_canvas.yview_scroll(-1 if delta > 0 else 1, "units")
        return "break"

    grid.bind("<Configure>", update_scroll_region)
    cards_canvas.bind("<Configure>", resize_cards)
    cards_canvas.bind("<MouseWheel>", scroll_cards)
    cards_canvas.bind("<Button-4>", scroll_cards)
    cards_canvas.bind("<Button-5>", scroll_cards)
    root.bind_all("<MouseWheel>", scroll_cards)
    root.bind_all("<Button-4>", scroll_cards)
    root.bind_all("<Button-5>", scroll_cards)
    for column in range(2):
        grid.columnconfigure(column, weight=1, uniform="studio")
    for row in range(2):
        grid.rowconfigure(row, weight=1, uniform="studio")

    def card(title: str, row: int, column: int) -> tk.Frame:
        frame = tk.Frame(
            grid,
            bg=_CARD,
            padx=12,
            pady=9,
            highlightthickness=1,
            highlightbackground=_BORDER,
        )
        frame.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=(0, 7) if column == 0 else (7, 0),
            pady=(0, 5) if row == 0 else (5, 0),
        )
        tk.Label(
            frame,
            text=title.upper(),
            bg=_CARD,
            fg=_ACCENT,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 6))
        return frame

    def label(parent: tk.Widget, text: str, pady: tuple[int, int] = (4, 2)) -> None:
        tk.Label(parent, text=text, bg=_CARD, fg=_MUTED, anchor="w").pack(
            fill="x", pady=pady
        )

    def button(parent: tk.Widget, text: str, command: Callable[[], None]) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=_CARD_ALT,
            fg=_TEXT,
            activebackground="#30374c",
            activeforeground=_TEXT,
            relief="flat",
            padx=9,
            pady=6,
            cursor="hand2",
        )

    def make_row(parent: tk.Widget) -> tk.Frame:
        row = tk.Frame(parent, bg=_CARD)
        row.pack(fill="x")
        return row

    audio_card = card("Аудио и экспорт", 0, 0)
    label(audio_card, "Аудиодорожка")
    audio_row = tk.Frame(audio_card, bg=_CARD_ALT, padx=8, pady=6)
    audio_row.pack(fill="x")
    tk.Label(
        audio_row, textvariable=audio_label, bg=_CARD_ALT, fg=_TEXT, anchor="w"
    ).pack(side="left", fill="x", expand=True)

    def choose_audio() -> None:
        nonlocal audio_path
        path = filedialog.askopenfilename(
            parent=root,
            title="Выберите аудиофайл",
            filetypes=[
                ("Аудиофайлы", "*.mp3 *.wav *.ogg *.flac"),
                ("Все файлы", "*.*"),
            ],
        )
        if path:
            audio_path = path
            audio_label.set(Path(path).name)

    button(audio_row, "Обзор…", choose_audio).pack(side="right", padx=(8, 0))

    label(audio_card, "Длительность")
    duration_row = make_row(audio_card)
    duration_box = ttk.Combobox(
        duration_row,
        textvariable=duration_value,
        values=("15 сек", "30 сек", "60 сек"),
        state="readonly",
        width=12,
        style="Studio.TCombobox",
    )
    duration_box.pack(side="left")
    tk.Checkbutton(
        duration_row,
        text="По длине трека",
        variable=track_length_value,
        bg=_CARD,
        fg=_TEXT,
        activebackground=_CARD,
        activeforeground=_TEXT,
        selectcolor=_CARD_ALT,
    ).pack(side="left", padx=(10, 0))

    label(audio_card, "Путь сохранения")
    output_row = tk.Frame(audio_card, bg=_CARD_ALT, padx=8, pady=6)
    output_row.pack(fill="x")
    output_entry = tk.Entry(
        output_row,
        textvariable=output_value,
        bg=_CARD_ALT,
        fg=_TEXT,
        insertbackground=_TEXT,
        relief="flat",
        width=36,
    )
    output_entry.pack(side="left", fill="x", expand=True)

    def current_extension() -> str:
        return ".mov" if BACKGROUND_MODES[mode_value.get()] == "transparent" else ".mp4"

    def enforce_output_extension(*_args: object) -> None:
        current = Path(output_value.get().strip())
        if current.name:
            desired = current.with_suffix(current_extension())
            if str(desired) != output_value.get():
                output_value.set(str(desired))

    def choose_output() -> None:
        extension = current_extension()
        path = filedialog.asksaveasfilename(
            parent=root,
            title="Сохранить результат",
            defaultextension=extension,
            initialfile=Path(output_value.get()).name or f"output{extension}",
            filetypes=[("Видео", f"*{extension}")],
        )
        if path:
            output_value.set(str(Path(path).with_suffix(extension)))

    button(output_row, "Сохранить…", choose_output).pack(side="right", padx=(8, 0))

    background_card = card("Фон и маска · Compositing", 0, 1)
    label(background_card, "Режим фона")
    mode_box = ttk.Combobox(
        background_card,
        textvariable=mode_value,
        values=tuple(BACKGROUND_MODES),
        state="readonly",
        style="Studio.TCombobox",
    )
    mode_box.pack(fill="x")
    label(
        background_card,
        "В прозрачном режиме используется MOV; для остальных — MP4.",
        pady=(5, 5),
    )

    label(background_card, "Фоновое видео (.mp4 / .mov)")
    bg_row = tk.Frame(background_card, bg=_CARD_ALT, padx=8, pady=6)
    bg_row.pack(fill="x")
    bg_path_label = tk.Label(
        bg_row,
        textvariable=background_video_path,
        bg=_CARD_ALT,
        fg=_TEXT,
        anchor="w",
    )
    bg_path_label.pack(side="left", fill="x", expand=True)
    bg_button = button(bg_row, "Выбрать видео…", lambda: None)
    bg_button.pack(side="right", padx=(8, 0))

    def choose_background_video() -> None:
        path = filedialog.askopenfilename(
            parent=root,
            title="Выберите фоновое видео",
            filetypes=[
                ("Видеофайлы", "*.mp4 *.mov"),
                ("Все файлы", "*.*"),
            ],
        )
        if path:
            background_video_path.set(path)

    bg_button.configure(command=choose_background_video)
    def update_background_controls(*_args: object) -> None:
        mode = BACKGROUND_MODES[mode_value.get()]
        state = "normal" if mode in {"video_bg", "video_mask"} else "disabled"
        bg_button.configure(state=state)
        bg_path_label.configure(fg=_TEXT if state == "normal" else _MUTED)
        enforce_output_extension()

    mode_box.bind("<<ComboboxSelected>>", update_background_controls)
    update_background_controls()

    dynamics_card = card("Динамика и кольца", 1, 0)
    label(dynamics_card, "Всего колец")
    rings_row = make_row(dynamics_card)
    tk.Spinbox(
        rings_row,
        from_=10,
        to=2000,
        textvariable=ring_count_value,
        width=10,
        bg=_CARD_ALT,
        fg=_TEXT,
        insertbackground=_TEXT,
        buttonbackground=_CARD_ALT,
        relief="flat",
    ).pack(side="left", ipady=5)
    tk.Label(rings_row, text="  симулируется последовательно", bg=_CARD, fg=_MUTED).pack(
        side="left"
    )

    label(dynamics_card, "Колец на экране")
    visible_scale = tk.Scale(
        dynamics_card,
        variable=visible_value,
        from_=10,
        to=45,
        resolution=1,
        orient="horizontal",
        showvalue=True,
        bg=_CARD,
        fg=_TEXT,
        troughcolor=_CARD_ALT,
        activebackground=_ACCENT,
        highlightthickness=0,
        bd=0,
    )
    visible_scale.pack(fill="x")
    label(dynamics_card, "Сила пульсации от басов")
    tk.Scale(
        dynamics_card,
        variable=pulse_value,
        from_=0.0,
        to=2.5,
        resolution=0.1,
        orient="horizontal",
        showvalue=True,
        bg=_CARD,
        fg=_TEXT,
        troughcolor=_CARD_ALT,
        activebackground=_ACCENT,
        highlightthickness=0,
        bd=0,
    ).pack(fill="x")
    label(dynamics_card, "Сила вибрации колец")
    tk.Scale(
        dynamics_card,
        variable=vibration_value,
        from_=0.0,
        to=2.5,
        resolution=0.1,
        orient="horizontal",
        showvalue=True,
        bg=_CARD,
        fg=_TEXT,
        troughcolor=_CARD_ALT,
        activebackground=_ACCENT,
        highlightthickness=0,
        bd=0,
    ).pack(fill="x")
    label(dynamics_card, "Чувствительность звука")
    tk.Scale(
        dynamics_card,
        variable=sensitivity_value,
        from_=0.2,
        to=3.0,
        resolution=0.1,
        orient="horizontal",
        showvalue=True,
        bg=_CARD,
        fg=_TEXT,
        troughcolor=_CARD_ALT,
        activebackground=_ACCENT,
        highlightthickness=0,
        bd=0,
    ).pack(fill="x")
    label(dynamics_card, "Пресет физики и камеры")
    ttk.Combobox(
        dynamics_card,
        textvariable=dynamics_value,
        values=_DYNAMICS,
        state="readonly",
        style="Studio.TCombobox",
    ).pack(fill="x")

    style_card = card("Стиль, водяной знак и звук", 1, 1)
    label(style_card, "Цветовая тема")
    theme_value = tk.StringVar(value="Cyberpunk Neon")
    theme_box = ttk.Combobox(
        style_card,
        textvariable=theme_value,
        values=tuple(COLOR_THEMES),
        state="readonly",
        style="Studio.TCombobox",
    )
    theme_box.pack(fill="x")
    swatch_frame = tk.Frame(style_card, bg=_CARD)
    swatch_frame.pack(fill="x", pady=(7, 0))
    swatches: dict[str, tk.Label] = {}
    for key, title in (
        ("ring_inner", "Внутреннее"),
        ("ring_outer", "Внешнее"),
        ("ball", "Шар"),
    ):
        cell = tk.Frame(swatch_frame, bg=_CARD)
        cell.pack(side="left", expand=True, fill="x")
        tk.Label(cell, text=title, bg=_CARD, fg=_MUTED, font=("Segoe UI", 8)).pack(
            anchor="w"
        )
        swatch = tk.Label(cell, text="     ", bg=_hex_color(COLOR_THEMES["Custom"][key]))
        swatch.pack(anchor="w", pady=(3, 0))
        swatches[key] = swatch
    custom_row = tk.Frame(style_card, bg=_CARD)
    custom_colors = dict(COLOR_THEMES["Custom"])

    def refresh_theme(*_args: object) -> None:
        colors = custom_colors if theme_value.get() == "Custom" else COLOR_THEMES[theme_value.get()]
        for key in _THEME_COLOR_KEYS:
            swatches[key].configure(bg=_hex_color(colors[key]))
        if theme_value.get() == "Custom":
            custom_row.pack(fill="x", pady=(6, 0))
        else:
            custom_row.pack_forget()

    def choose_theme_color(key: str) -> None:
        selected = colorchooser.askcolor(
            color=_hex_color(custom_colors[key]),
            parent=root,
            title="Выберите цвет",
        )[1]
        if selected:
            custom_colors[key] = _parse_hex(selected)
            theme_value.set("Custom")
            refresh_theme()

    for key, title in (
        ("ring_inner", "Цвет внутреннего кольца"),
        ("ring_outer", "Цвет внешнего кольца"),
        ("ball", "Цвет шара"),
    ):
        button(
            custom_row,
            title,
            lambda selected_key=key: choose_theme_color(selected_key),
        ).pack(side="left", padx=(0, 5))
    theme_box.bind("<<ComboboxSelected>>", refresh_theme)
    refresh_theme()

    label(style_card, "Водяной знак")
    watermark_value = tk.StringVar(value=WATERMARK_TEXT)
    watermark_entry = tk.Entry(
        style_card,
        textvariable=watermark_value,
        bg=_CARD_ALT,
        fg=_TEXT,
        insertbackground=_TEXT,
        relief="flat",
    )
    watermark_entry.pack(fill="x", ipady=6)
    label(style_card, "Прозрачность")
    opacity_value = tk.DoubleVar(value=0.18)
    tk.Scale(
        style_card,
        variable=opacity_value,
        from_=0.0,
        to=1.0,
        resolution=0.01,
        orient="horizontal",
        showvalue=True,
        bg=_CARD,
        fg=_TEXT,
        troughcolor=_CARD_ALT,
        activebackground=_ACCENT,
        highlightthickness=0,
        bd=0,
    ).pack(fill="x")
    asmr_value = tk.BooleanVar(value=False)
    tk.Checkbutton(
        style_card,
        text="Добавить ASMR-звуки отскоков и пробитий",
        variable=asmr_value,
        bg=_CARD,
        fg=_TEXT,
        activebackground=_CARD,
        activeforeground=_TEXT,
        selectcolor=_CARD_ALT,
    ).pack(anchor="w", pady=(5, 0))

    output_value.trace_add("write", enforce_output_extension)
    enforce_output_extension()
    status_text = tk.StringVar(value="Готово к созданию")
    tk.Label(footer, textvariable=status_text, bg=_BG, fg=_MUTED, anchor="w").pack(
        fill="x", pady=(0, 3)
    )
    progress = ttk.Progressbar(
        footer, mode="determinate", maximum=100, style="Studio.Horizontal.TProgressbar"
    )
    progress.pack(fill="x")
    details_text = tk.StringVar(value="Кадр — / —     Рендер — FPS     ETA —")
    tk.Label(footer, textvariable=details_text, bg=_BG, fg=_MUTED, anchor="w").pack(
        fill="x", pady=(3, 0)
    )
    action_row = tk.Frame(footer, bg=_BG)
    action_row.pack(fill="x", pady=(6, 0))
    open_video_button = button(action_row, "Открыть готовое видео", lambda: None)
    open_folder_button = button(action_row, "Открыть папку", lambda: None)
    create_button = tk.Button(
        action_row,
        text="Сгенерировать видео",
        bg=_ACCENT,
        fg="white",
        activebackground="#8150e5",
        activeforeground="white",
        relief="flat",
        font=("Segoe UI", 11, "bold"),
        padx=18,
        pady=9,
        cursor="hand2",
    )
    open_video_button.pack(side="left")
    open_folder_button.pack(side="left", padx=(8, 0))
    create_button.pack(side="right")
    open_video_button.configure(state="disabled")
    open_folder_button.configure(state="disabled")

    messages: queue.Queue[tuple[str, object]] = queue.Queue()
    completed_path: str | None = None

    def report_progress(frame: int, total: int, render_fps: float, eta: float) -> None:
        messages.put(("progress", (frame, total, render_fps, eta)))

    def start_render() -> None:
        try:
            ring_count = int(ring_count_value.get())
            visible_count = int(visible_value.get())
            pulse = float(pulse_value.get())
            vibration = float(vibration_value.get())
            sensitivity = float(sensitivity_value.get())
            opacity = float(opacity_value.get())
            if not 10 <= ring_count <= 2000:
                raise ValueError("Всего колец должно быть от 10 до 2000.")
            if not 10 <= visible_count <= 45 or visible_count > ring_count:
                raise ValueError("На экране должно быть от 10 до 45 колец и не больше общего числа.")
            if not 0.0 <= pulse <= 2.5 or not 0.0 <= vibration <= 2.5:
                raise ValueError("Силы пульсации и вибрации должны быть от 0.0 до 2.5.")
            if not 0.2 <= sensitivity <= 3.0:
                raise ValueError("Чувствительность звука должна быть от 0.2 до 3.0.")
            if not 0.0 <= opacity <= 1.0:
                raise ValueError("Прозрачность должна быть от 0.0 до 1.0.")

            mode = BACKGROUND_MODES[mode_value.get()]
            background_path = background_video_path.get().strip()
            if mode in {"video_bg", "video_mask"}:
                if not background_path or not Path(background_path).is_file():
                    raise ValueError("Выберите существующий файл фонового видео.")
            output = Path(output_value.get().strip()).expanduser()
            if not output.name:
                raise ValueError("Укажите путь для итогового видео.")
            output = output.with_suffix(".mov" if mode == "transparent" else ".mp4")
            duration_seconds = float(duration_value.get().split()[0])
            preset = SPEED_PRESETS[dynamics_value.get()]
            colors = (
                custom_colors.copy()
                if theme_value.get() == "Custom"
                else dict(COLOR_THEMES[theme_value.get()])
            )
            settings = StudioSettings(
                audio_path=audio_path,
                duration=duration_seconds,
                use_track_length=track_length_value.get(),
                ring_count=ring_count,
                visible_rings=visible_count,
                ball_speed=preset["ball_speed"],
                gravity=preset["gravity"],
                dynamics_level=dynamics_value.get(),
                pulse_strength=pulse,
                vibration_strength=vibration,
                audio_sensitivity=sensitivity,
                background_mode=mode,
                background_video_path=background_path,
                watermark_text=watermark_value.get(),
                watermark_opacity=opacity,
                theme_name=theme_value.get(),
                theme_colors=colors,
                asmr_hits=asmr_value.get(),
                output_path=str(output.resolve()),
            )
        except (ValueError, KeyError) as error:
            messagebox.showerror("Проверьте настройки", str(error), parent=root)
            return

        output_value.set(settings.output_path)
        progress.configure(value=0)
        status_text.set("Подготовка рендера…")
        details_text.set("Кадр — / —     Рендер — FPS     ETA —")
        create_button.configure(state="disabled")
        open_video_button.configure(state="disabled")
        open_folder_button.configure(state="disabled")

        def worker() -> None:
            try:
                render_function(settings, report_progress)
                messages.put(("complete", settings.output_path))
            except Exception as error:
                messages.put(("error", error))

        threading.Thread(target=worker, name="sonicvortex-render", daemon=True).start()

    create_button.configure(command=start_render)

    def open_path(path: str) -> None:
        try:
            import os
            import subprocess

            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(
                    ["open" if os.uname().sysname == "Darwin" else "xdg-open", path]
                )
        except OSError as error:
            messagebox.showerror("Не удалось открыть", str(error), parent=root)

    open_video_button.configure(
        command=lambda: open_path(completed_path) if completed_path else None
    )
    open_folder_button.configure(
        command=lambda: open_path(str(Path(completed_path).parent))
        if completed_path
        else None
    )

    def poll_messages() -> None:
        nonlocal completed_path
        try:
            while True:
                kind, payload = messages.get_nowait()
                if kind == "progress":
                    frame, total, render_fps, eta = payload  # type: ignore[misc]
                    progress.configure(value=100.0 * frame / max(total, 1))
                    status_text.set(f"Рендер: {100.0 * frame / max(total, 1):.1f}%")
                    details_text.set(
                        f"Кадр {frame:,} / {total:,}     "
                        f"{render_fps:.1f} FPS     ETA {eta:,.0f} сек."
                    )
                elif kind == "complete":
                    completed_path = str(payload)
                    progress.configure(value=100)
                    status_text.set("Видео успешно создано")
                    details_text.set(f"Файл: {completed_path}")
                    create_button.configure(state="normal")
                    open_video_button.configure(state="normal")
                    open_folder_button.configure(state="normal")
                elif kind == "error":
                    create_button.configure(state="normal")
                    status_text.set("При рендере произошла ошибка")
                    details_text.set(str(payload))
                    messagebox.showerror("Ошибка рендера", str(payload), parent=root)
        except queue.Empty:
            pass
        if root.winfo_exists():
            root.after(100, poll_messages)

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.after(100, poll_messages)
    root.mainloop()
