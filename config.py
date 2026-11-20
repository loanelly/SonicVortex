"""Configuration for the vertical video generator."""

WIDTH = 1080
HEIGHT = 1920
FPS = 60
OUTPUT_FILE = "output.mp4"
AUDIO_FILE = "track.mp3"
MAX_DURATION = 30
PROJECT_NAME = "SonicVortex"
WATERMARK_TEXT = "SonicVortex"

# The studio starts with 200 rings; increase to 2000 for a longer run.
RING_COUNT = 200
VISIBLE_RINGS = 26
PULSE_STRENGTH = 1.0
VIBRATION_STRENGTH = 1.0
AUDIO_SENSITIVITY = 1.0
RING_BREAK_COOLDOWN = 0.06
BREAK_RADIAL_RETENTION = 0.65
SPEED_GAIN_PER_BREAK = 1.015
MAX_SPEED = 1650.0
GAP_AIM_ASSIST = 0.20
GAP_AIM_JITTER_DEG = 6.0
RING_BREAK_ROTATION_GAIN = 1.008
AMBIENT_PARTICLE_COUNT = 45
DYNAMICS_LEVEL = "High"
BG_MODE = "solid"
BG_VIDEO_PATH = ""
INNER_RADIUS = 170
OUTER_RADIUS = 510
RING_THICKNESS = 4.0
GAP_ANGLE_DEG = 82.0
RING_GAP_DEGREES = GAP_ANGLE_DEG
RING_ROTATION_SPEED = 0.35
GRAVITY = 980.0
BALL_RADIUS = 14
BALL_SPEED = 650.0
MIN_BOUNCE_SPEED = 620.0
BOUNCE_RESTITUTION = 1.02  # Slight acceleration on each bounce.
TRAIL_LENGTH = 25

PARTICLES_PER_HIT = 40
PARTICLE_SPEED = 350.0
PARTICLE_LIFETIME = 0.6

# 8-bit RGB/RGBA colors: interpolate from purple to turquoise across the rings.
RING_COLOR_START = (170, 70, 255, 255)
RING_COLOR_END = (40, 255, 220, 255)
BACKGROUND_COLOR = (5, 5, 10)

COLOR_THEMES = {
    "Cyberpunk Neon": {
        "ring_inner": (170, 70, 255),
        "ring_outer": (40, 255, 220),
        "ball": (255, 40, 180),
        "trail": (90, 245, 255),
    },
    "Inferno Gold": {
        "ring_inner": (255, 45, 50),
        "ring_outer": (255, 205, 55),
        "ball": (255, 255, 245),
        "trail": (255, 125, 35),
    },
    "Matrix Toxic": {
        "ring_inner": (0, 180, 110),
        "ring_outer": (180, 255, 35),
        "ball": (80, 255, 35),
        "trail": (0, 220, 100),
    },
    "Oceanic Pulse": {
        "ring_inner": (20, 55, 190),
        "ring_outer": (100, 235, 255),
        "ball": (245, 255, 255),
        "trail": (75, 170, 255),
    },
    "Custom": {
        "ring_inner": (170, 70, 255),
        "ring_outer": (40, 255, 220),
        "ball": (255, 40, 180),
        "trail": (90, 245, 255),
    },
}

SPEED_PRESETS = {
    "Chill": {"ball_speed": 480.0, "gravity": 650.0},
    "Dynamic": {"ball_speed": 650.0, "gravity": 980.0},
    "Extreme": {"ball_speed": 880.0, "gravity": 1350.0},
}

BACKGROUND_MODES = {
    "Тёмный фон (Стандарт)": "solid",
    "Прозрачный фон (MOV)": "transparent",
    "Видео на заднем фоне": "video_bg",
    "Маска (видео внутри колец)": "video_mask",
}
