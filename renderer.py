"""OpenGL renderer for the vertical neon-ring video."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import TypeAlias

import moderngl
import numpy as np
import pygame

from config import (
    AMBIENT_PARTICLE_COUNT,
    BACKGROUND_COLOR,
    BALL_RADIUS,
    GAP_ANGLE_DEG,
    HEIGHT,
    INNER_RADIUS,
    OUTER_RADIUS,
    PARTICLE_LIFETIME,
    PULSE_STRENGTH,
    RING_COLOR_END,
    RING_COLOR_START,
    RING_COUNT,
    RING_THICKNESS,
    TRAIL_LENGTH,
    VISIBLE_RINGS,
    VIBRATION_STRENGTH,
    WIDTH,
    WATERMARK_TEXT,
)

Point: TypeAlias = tuple[float, float]
_EQ_BINS = 48
_AMBIENT_COUNT = AMBIENT_PARTICLE_COUNT
Particle: TypeAlias = (
    tuple[float, float, float]
    | tuple[float, float, float, float]
    | tuple[float, float, float, float, float, float]
)
Shockwave: TypeAlias = tuple[float, float, float]

_CIRCLE_VERTEX_SHADER = """
#version 330
uniform vec2 u_viewport;
uniform vec2 u_camera_center;
uniform float u_camera_zoom;
uniform float u_expansion;

in vec2 in_corner;
in vec2 in_center;
in float in_radius;
in float in_angle;
in float in_thickness;
in vec4 in_color;

out vec2 v_local;
out float v_radius;
out float v_angle;
out float v_thickness;
out vec4 v_color;

void main() {
    float extent = in_radius + u_expansion;
    vec2 pixel_position = in_center + in_corner * extent;
    pixel_position = u_camera_center
        + (pixel_position - u_camera_center) * u_camera_zoom;
    vec2 clip_position = vec2(
        pixel_position.x / u_viewport.x * 2.0 - 1.0,
        1.0 - pixel_position.y / u_viewport.y * 2.0
    );
    gl_Position = vec4(clip_position, 0.0, 1.0);
    v_local = in_corner * extent * u_camera_zoom;
    v_radius = in_radius * u_camera_zoom;
    v_angle = in_angle;
    v_thickness = in_thickness * u_camera_zoom;
    v_color = in_color;
}
"""

_RIBBON_VERTEX_SHADER = """
#version 330
uniform vec2 u_viewport;
uniform vec2 u_camera_center;
uniform float u_camera_zoom;
in vec2 in_position;
in vec4 in_color;
out vec4 v_color;
void main() {
    vec2 position = u_camera_center
        + (in_position - u_camera_center) * u_camera_zoom;
    vec2 clip = vec2(
        position.x / u_viewport.x * 2.0 - 1.0,
        1.0 - position.y / u_viewport.y * 2.0
    );
    gl_Position = vec4(clip, 0.0, 1.0);
    v_color = in_color;
}
"""

_RIBBON_FRAGMENT_SHADER = """
#version 330
in vec4 v_color;
out vec4 frag_color;
void main() {
    frag_color = v_color;
}
"""

_EQUALIZER_VERTEX_SHADER = """
#version 330
uniform vec2 u_viewport;
in vec2 in_position;
in vec4 in_color;
out vec4 v_color;
void main() {
    vec2 clip = vec2(
        in_position.x / u_viewport.x * 2.0 - 1.0,
        1.0 - in_position.y / u_viewport.y * 2.0
    );
    gl_Position = vec4(clip, 0.0, 1.0);
    v_color = in_color;
}
"""

_EQUALIZER_FRAGMENT_SHADER = """
#version 330
in vec4 v_color;
out vec4 frag_color;
void main() {
    frag_color = v_color;
}
"""

_CIRCLE_FRAGMENT_SHADER = """
#version 330
uniform int u_ring_mode;
uniform float u_gap_half_angle;
uniform float u_sub_bass;
uniform float u_high_energy;
uniform float u_vibration_strength;
uniform float u_time;
uniform float u_inner_radius;
uniform float u_outer_radius;

in vec2 v_local;
in float v_radius;
in float v_angle;
in float v_thickness;
in vec4 v_color;
out vec4 frag_color;

void main() {
    float distance_from_center = length(v_local);
    float gap_coverage = 1.0;
    float angle = atan(v_local.y, v_local.x);
    if (u_ring_mode == 1) {
        float angle_delta = atan(sin(angle - v_angle), cos(angle - v_angle));
        float angle_width = max(fwidth(angle_delta), 0.001);
        gap_coverage = smoothstep(
            u_gap_half_angle - angle_width * 0.5,
            u_gap_half_angle + angle_width * 0.5,
            abs(angle_delta)
        );
    }
    float edge_distance = u_ring_mode != 0
        ? abs(distance_from_center - v_radius)
        : distance_from_center;
    if (u_ring_mode == 1) {
        float radial_fraction = clamp(
            (v_radius - u_inner_radius) / (u_outer_radius - u_inner_radius),
            0.0,
            1.0
        );
        float wave = sin(angle * 28.0 + v_angle * 3.0 + u_time * 20.0);
        float bass_vibration = (
            u_high_energy * 0.8 + u_sub_bass * 0.18
        ) * u_vibration_strength;
        edge_distance = abs(
            distance_from_center - v_radius
            + wave * bass_vibration * (0.25 + 1.25 * radial_fraction)
        );
    }
    float edge_width = max(fwidth(edge_distance), 0.5);
    float coverage;
    if (u_ring_mode != 0) {
        coverage = 1.0 - smoothstep(
            v_thickness * 0.5 - edge_width * 0.5,
            v_thickness * 0.5 + edge_width * 0.5,
            edge_distance
        );
    } else {
        coverage = 1.0 - smoothstep(
            v_radius - edge_width,
            v_radius + edge_width,
            distance_from_center
        );
    }
    if (coverage <= 0.0) {
        discard;
    }
    coverage *= gap_coverage;
    frag_color = vec4(v_color.rgb, v_color.a * coverage);
}
"""

_SCREEN_VERTEX_SHADER = """
#version 330
in vec2 in_position;
in vec2 in_uv;
out vec2 v_uv;

void main() {
    gl_Position = vec4(in_position, 0.0, 1.0);
    v_uv = in_uv;
}
"""

_BRIGHT_FRAGMENT_SHADER = """
#version 330
uniform sampler2D u_image;
in vec2 v_uv;
out vec4 frag_color;

void main() {
    vec3 color = texture(u_image, v_uv).rgb;
    vec3 bright = max(color - vec3(0.52), vec3(0.0));
    frag_color = vec4(bright, max(max(bright.r, bright.g), bright.b));
}
"""

_BLUR_FRAGMENT_SHADER = """
#version 330
uniform sampler2D u_image;
uniform vec2 u_direction;
uniform vec2 u_texel;
in vec2 v_uv;
out vec4 frag_color;

void main() {
    vec2 offset = u_direction * u_texel * 2.2;
    vec4 color = texture(u_image, v_uv) * 0.227027;
    color += texture(u_image, v_uv + offset) * 0.1945946;
    color += texture(u_image, v_uv - offset) * 0.1945946;
    color += texture(u_image, v_uv + offset * 2.0) * 0.1216216;
    color += texture(u_image, v_uv - offset * 2.0) * 0.1216216;
    color += texture(u_image, v_uv + offset * 3.0) * 0.054054;
    color += texture(u_image, v_uv - offset * 3.0) * 0.054054;
    color += texture(u_image, v_uv + offset * 4.0) * 0.016216;
    color += texture(u_image, v_uv - offset * 4.0) * 0.016216;
    frag_color = color;
}
"""

_COMPOSITE_FRAGMENT_SHADER = """
#version 330
uniform sampler2D u_scene;
uniform sampler2D u_glow;
uniform sampler2D u_background;
uniform int u_mode;
in vec2 v_uv;
out vec4 frag_color;

void main() {
    vec4 scene = texture(u_scene, v_uv);
    vec4 glow = texture(u_glow, v_uv);
    vec3 color = scene.rgb + glow.rgb * 1.65;
    if (u_mode == 1) {
        float alpha = max(scene.a, glow.a * 1.65);
        frag_color = vec4(color, alpha);
    } else if (u_mode == 2) {
        vec3 background = texture(u_background, v_uv).rgb;
        frag_color = vec4(background + color, 1.0);
    } else if (u_mode == 3) {
        vec3 background = texture(u_background, v_uv).rgb;
        frag_color = vec4(background * scene.a + color, 1.0);
    } else {
        frag_color = vec4(color, 1.0);
    }
}
"""

_TEXT_VERTEX_SHADER = """
#version 330
uniform vec2 u_center;
uniform vec2 u_size;

in vec2 in_corner;
in vec2 in_uv;
out vec2 v_uv;

void main() {
    gl_Position = vec4(u_center + in_corner * u_size * 0.5, 0.0, 1.0);
    v_uv = in_uv;
}
"""

_TEXT_FRAGMENT_SHADER = """
#version 330
uniform sampler2D u_text;
in vec2 v_uv;
out vec4 frag_color;

void main() {
    frag_color = texture(u_text, v_uv);
}
"""

_QUAD_VERTICES = np.array(
    [
        -1.0, -1.0, 0.0, 0.0,
        1.0, -1.0, 1.0, 0.0,
        1.0, 1.0, 1.0, 1.0,
        -1.0, -1.0, 0.0, 0.0,
        1.0, 1.0, 1.0, 1.0,
        -1.0, 1.0, 0.0, 1.0,
    ],
    dtype="f4",
)

_CIRCLE_CORNERS = np.array(
    [-1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, -1.0, 1.0, 1.0, -1.0, 1.0],
    dtype="f4",
)

_TEXT_CORNERS = np.array(
    [
        -1.0, -1.0, 0.0, 0.0,
        1.0, -1.0, 1.0, 0.0,
        1.0, 1.0, 1.0, 1.0,
        -1.0, -1.0, 0.0, 0.0,
        1.0, 1.0, 1.0, 1.0,
        -1.0, 1.0, 0.0, 1.0,
    ],
    dtype="f4",
)


class Renderer:
    """Render fixed-resolution frames to an offscreen OpenGL framebuffer.

    The ball and trail positions use pixel coordinates with (0, 0) at the
    top-left. Particles are (x, y, age_seconds) tuples; their motion is handled
    by the simulation and their size and opacity are derived from their age.
    """

    def __init__(
        self,
        ring_count: int = RING_COUNT,
        watermark_text: str = WATERMARK_TEXT,
        visible_rings: int = VISIBLE_RINGS,
        theme_colors: dict[str, tuple[int, int, int]] | None = None,
        watermark_opacity: float = 0.18,
        background_mode: str = "solid",
    ) -> None:
        if ring_count <= 0:
            raise ValueError("ring_count must be greater than zero")
        if visible_rings <= 0:
            raise ValueError("visible_rings must be greater than zero")
        if not 0.0 <= watermark_opacity <= 1.0:
            raise ValueError("watermark_opacity must be between zero and one")
        if background_mode not in {"solid", "transparent", "video_bg", "video_mask"}:
            raise ValueError(f"Unsupported background mode: {background_mode}")
        self.ring_count = ring_count
        self.visible_ring_count = min(ring_count, visible_rings)
        self.camera_zoom = 1.0
        self.background_mode = background_mode
        self._background_texture: moderngl.Texture | None = None
        self.theme_colors = theme_colors or {
            "ring_inner": RING_COLOR_START[:3],
            "ring_outer": RING_COLOR_END[:3],
            "ball": (255, 40, 180),
            "trail": (90, 245, 255),
        }
        self.watermark_opacity = watermark_opacity
        pygame.init()
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(
            pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE
        )
        pygame.display.set_mode(
            (1, 1), pygame.OPENGL | pygame.DOUBLEBUF | pygame.HIDDEN
        )

        self.ctx = moderngl.create_context(require=330)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE)
        if background_mode in {"video_bg", "video_mask"}:
            self._background_texture = self.ctx.texture(
                (WIDTH, HEIGHT), components=3, dtype="f1"
            )
            self._background_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._background_texture.repeat_x = False
            self._background_texture.repeat_y = False

        self._scene_fbo, self._scene_texture = self._make_fbo()
        self._bright_fbo, self._bright_texture = self._make_fbo()
        self._blur_fbo, self._blur_texture = self._make_fbo()
        self._glow_fbo, self._glow_texture = self._make_fbo()
        self._output_fbo, self._output_texture = self._make_fbo()
        self.fbo = self._output_fbo

        self._circle_program = self.ctx.program(
            vertex_shader=_CIRCLE_VERTEX_SHADER,
            fragment_shader=_CIRCLE_FRAGMENT_SHADER,
        )
        self._bright_program = self.ctx.program(
            vertex_shader=_SCREEN_VERTEX_SHADER,
            fragment_shader=_BRIGHT_FRAGMENT_SHADER,
        )
        self._blur_program = self.ctx.program(
            vertex_shader=_SCREEN_VERTEX_SHADER,
            fragment_shader=_BLUR_FRAGMENT_SHADER,
        )
        self._composite_program = self.ctx.program(
            vertex_shader=_SCREEN_VERTEX_SHADER,
            fragment_shader=_COMPOSITE_FRAGMENT_SHADER,
        )
        self._text_program = self.ctx.program(
            vertex_shader=_TEXT_VERTEX_SHADER,
            fragment_shader=_TEXT_FRAGMENT_SHADER,
        )
        self._ribbon_program = self.ctx.program(
            vertex_shader=_RIBBON_VERTEX_SHADER,
            fragment_shader=_RIBBON_FRAGMENT_SHADER,
        )
        self._equalizer_program = self.ctx.program(
            vertex_shader=_EQUALIZER_VERTEX_SHADER,
            fragment_shader=_EQUALIZER_FRAGMENT_SHADER,
        )

        self._circle_corners = self.ctx.buffer(_CIRCLE_CORNERS.tobytes())
        self._circle_instances = self.ctx.buffer(reserve=9 * 4)
        self._circle_vao = self.ctx.vertex_array(
            self._circle_program,
            [
                (self._circle_corners, "2f", "in_corner"),
                (
                    self._circle_instances,
                    "2f 1f 1f 1f 4f /i",
                    "in_center",
                    "in_radius",
                    "in_angle",
                    "in_thickness",
                    "in_color",
                ),
            ],
        )
        self._ribbon_buffer = self.ctx.buffer(
            reserve=max(1, (TRAIL_LENGTH - 1) * 6 * 6 * 4)
        )
        self._ribbon_vao = self.ctx.vertex_array(
            self._ribbon_program,
            [(self._ribbon_buffer, "2f 4f", "in_position", "in_color")],
        )
        self._ribbon_program["u_viewport"].value = (float(WIDTH), float(HEIGHT))
        self._ribbon_program["u_camera_center"].value = (
            WIDTH / 2.0,
            HEIGHT / 2.0,
        )
        self._equalizer_buffer = self.ctx.buffer(
            reserve=_EQ_BINS * 2 * 6 * 6 * 4
        )
        self._equalizer_vao = self.ctx.vertex_array(
            self._equalizer_program,
            [(self._equalizer_buffer, "2f 4f", "in_position", "in_color")],
        )
        self._equalizer_program["u_viewport"].value = (
            float(WIDTH),
            float(HEIGHT),
        )
        ambient_rng = np.random.default_rng(8143)
        self._ambient_base = np.column_stack(
            (
                ambient_rng.uniform(0.0, WIDTH, _AMBIENT_COUNT),
                ambient_rng.uniform(0.0, HEIGHT, _AMBIENT_COUNT),
            )
        )
        self._ambient_velocity = ambient_rng.uniform(
            -4.0, 4.0, (_AMBIENT_COUNT, 2)
        )
        self._ambient_phase = ambient_rng.uniform(0.0, math.tau, _AMBIENT_COUNT)
        self._ambient_radius = ambient_rng.uniform(1.0, 2.8, _AMBIENT_COUNT)
        self._quad_buffer = self.ctx.buffer(_QUAD_VERTICES.tobytes())
        self._screen_vaos = {
            program: self.ctx.vertex_array(
                program, [(self._quad_buffer, "2f 2f", "in_position", "in_uv")]
            )
            for program in (
                self._bright_program,
                self._blur_program,
                self._composite_program,
            )
        }

        self._text_buffer = self.ctx.buffer(_TEXT_CORNERS.tobytes())
        self._text_vao = self.ctx.vertex_array(
            self._text_program,
            [(self._text_buffer, "2f 2f", "in_corner", "in_uv")],
        )
        self._font = pygame.font.Font(None, 120)
        self._watermark_font = pygame.font.SysFont("segoeui", 48, bold=True)
        self._text_texture: moderngl.Texture | None = None
        self._text_size = (0, 0)
        self._displayed_count: int | None = None
        self._watermark_texture: moderngl.Texture | None = None
        self._watermark_size = (0, 0)
        self._displayed_watermark: str | None = None

        self._center = (WIDTH / 2.0, HEIGHT / 2.0)
        self._ring_data = self._make_ring_data()
        self._circle_program["u_viewport"].value = (float(WIDTH), float(HEIGHT))
        self._circle_program["u_camera_center"].value = (
            WIDTH / 2.0,
            HEIGHT / 2.0,
        )
        self._circle_program["u_camera_zoom"].value = 1.0
        self._circle_program["u_expansion"].value = 4.0
        self._circle_program["u_gap_half_angle"].value = math.radians(
            GAP_ANGLE_DEG / 2.0
        )
        self._circle_program["u_sub_bass"].value = 0.0
        self._circle_program["u_high_energy"].value = 0.0
        self._circle_program["u_vibration_strength"].value = VIBRATION_STRENGTH
        self._circle_program["u_time"].value = 0.0
        self._bright_program["u_image"].value = 0
        self._blur_program["u_image"].value = 0
        self._blur_program["u_texel"].value = (1.0 / WIDTH, 1.0 / HEIGHT)
        self._composite_program["u_scene"].value = 0
        self._composite_program["u_glow"].value = 1
        self._composite_program["u_background"].value = 2
        self._composite_program["u_mode"].value = {
            "solid": 0,
            "transparent": 1,
            "video_bg": 2,
            "video_mask": 3,
        }[background_mode]
        self._text_program["u_text"].value = 0
        self._circle_program["u_inner_radius"].value = float(INNER_RADIUS)
        self._circle_program["u_outer_radius"].value = float(OUTER_RADIUS)
        self._update_watermark(watermark_text)

    def _make_fbo(self) -> tuple[moderngl.Framebuffer, moderngl.Texture]:
        texture = self.ctx.texture((WIDTH, HEIGHT), components=4, dtype="f1")
        texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        texture.repeat_x = False
        texture.repeat_y = False
        return self.ctx.framebuffer(color_attachments=[texture]), texture

    @staticmethod
    def _normalized_color(color: Sequence[int]) -> tuple[float, float, float, float]:
        if len(color) == 3:
            red, green, blue = color
            alpha = 255
        elif len(color) == 4:
            red, green, blue, alpha = color
        else:
            raise ValueError("Colors must contain three RGB or four RGBA channels")
        return red / 255.0, green / 255.0, blue / 255.0, alpha / 255.0

    def _make_ring_data(self) -> np.ndarray:
        start = np.asarray(
            self._normalized_color(self.theme_colors["ring_inner"]), dtype="f4"
        )
        end = np.asarray(
            self._normalized_color(self.theme_colors["ring_outer"]), dtype="f4"
        )
        ring_spacing = (OUTER_RADIUS - INNER_RADIUS) / self.visible_ring_count
        radii = INNER_RADIUS + (np.arange(self.ring_count) + 0.5) * ring_spacing
        colors = np.linspace(start, end, self.ring_count, dtype="f4")
        data = np.empty((self.ring_count, 9), dtype="f4")
        data[:, 0:2] = self._center
        data[:, 2] = radii
        data[:, 3] = 0.0
        data[:, 4] = RING_THICKNESS
        data[:, 5:9] = colors
        return data

    def _draw_circles(self, data: np.ndarray, ring_mode: int | bool = False) -> None:
        if not len(data):
            return
        self._circle_instances.orphan(data.nbytes)
        self._circle_instances.write(data.tobytes())
        self._circle_program["u_ring_mode"].value = int(ring_mode)
        self._circle_vao.render(
            mode=moderngl.TRIANGLES, vertices=6, instances=len(data)
        )

    def _draw_ambient_particles(self, simulation_time: float, sub_bass: float) -> None:
        drift_scale = 1.0 + min(1.5, max(0.0, sub_bass)) * 0.9
        positions = (
            self._ambient_base
            + self._ambient_velocity * (simulation_time * drift_scale)
        )
        positions[:, 0] %= WIDTH
        positions[:, 1] %= HEIGHT
        shimmer = 0.5 + 0.5 * np.sin(
            self._ambient_phase + simulation_time * 0.8
        )
        data = np.empty((_AMBIENT_COUNT, 9), dtype="f4")
        data[:, 0:2] = positions
        data[:, 2] = self._ambient_radius
        data[:, 3] = 0.0
        data[:, 4] = 1.0
        data[:, 5] = self.theme_colors["trail"][0] / 255.0
        data[:, 6] = self.theme_colors["trail"][1] / 255.0
        data[:, 7] = self.theme_colors["trail"][2] / 255.0
        data[:, 8] = 0.08 + shimmer * 0.12
        self._draw_circles(data)

    def _draw_ribbon(self, points: Sequence[Point]) -> None:
        if len(points) < 2:
            return
        vertices: list[tuple[float, float, float, float, float, float]] = []
        color = tuple(channel / 255.0 for channel in self.theme_colors["trail"])
        width_at = [
            0.8 + (index + 1) / len(points) * BALL_RADIUS * 0.9
            for index in range(len(points))
        ]
        alpha_at = [
            ((index + 1) / len(points)) ** 1.8 * 0.9
            for index in range(len(points))
        ]
        for index in range(len(points) - 1):
            x0, y0 = points[index]
            x1, y1 = points[index + 1]
            tangent_x = x1 - x0
            tangent_y = y1 - y0
            tangent_length = math.hypot(tangent_x, tangent_y)
            if tangent_length <= 1e-6:
                continue
            normal_x = -tangent_y / tangent_length
            normal_y = tangent_x / tangent_length
            half0 = width_at[index] * 0.5
            half1 = width_at[index + 1] * 0.5
            p0 = (x0 + normal_x * half0, y0 + normal_y * half0)
            p1 = (x0 - normal_x * half0, y0 - normal_y * half0)
            p2 = (x1 + normal_x * half1, y1 + normal_y * half1)
            p3 = (x1 - normal_x * half1, y1 - normal_y * half1)
            c0 = (*color, alpha_at[index])
            c1 = (*color, alpha_at[index + 1])
            vertices.extend(
                (
                    (*p0, *c0),
                    (*p1, *c0),
                    (*p2, *c1),
                    (*p2, *c1),
                    (*p1, *c0),
                    (*p3, *c1),
                )
            )
        if vertices:
            data = np.asarray(vertices, dtype="f4")
            self._ribbon_buffer.orphan(data.nbytes)
            self._ribbon_buffer.write(data.tobytes())
            self._ribbon_program["u_camera_zoom"].value = self.camera_zoom
            self._ribbon_vao.render(mode=moderngl.TRIANGLES, vertices=len(vertices))

    def _draw_equalizer(self, spectrum: Sequence[float] | None) -> None:
        if spectrum is None:
            return
        levels = np.asarray(spectrum, dtype=np.float32).reshape(-1)
        if levels.size == 0:
            return
        if levels.size != _EQ_BINS:
            raise ValueError(f"Expected {_EQ_BINS} equalizer bins, got {levels.size}")
        levels = np.clip(levels, 0.0, 1.5)
        palette_inner = np.asarray(self.theme_colors["ring_inner"], dtype=np.float32)
        palette_outer = np.asarray(self.theme_colors["ring_outer"], dtype=np.float32)
        span = WIDTH * 0.72
        step = span / _EQ_BINS
        bar_width = max(3.0, step * 0.48)
        vertices: list[tuple[float, float, float, float, float, float]] = []

        def append_quad(
            left: float, top: float, right: float, bottom: float, color: tuple[float, ...]
        ) -> None:
            a = (left, top, *color)
            b = (right, top, *color)
            c = (right, bottom, *color)
            d = (left, bottom, *color)
            vertices.extend((a, b, c, a, c, d))

        for index, value in enumerate(levels):
            ratio = index / max(1, _EQ_BINS - 1)
            rgb = palette_inner * (1.0 - ratio) + palette_outer * ratio
            energy = min(1.0, float(value) / 1.5)
            alpha = 0.14 + energy * 0.86
            color = (
                float(rgb[0] / 255.0),
                float(rgb[1] / 255.0),
                float(rgb[2] / 255.0),
                alpha,
            )
            x = WIDTH * 0.14 + index * step + (step - bar_width) * 0.5
            height = 5.0 + energy * 105.0
            top_base = 115.0
            bottom_base = HEIGHT - top_base
            append_quad(x, top_base, x + bar_width, top_base + height, color)
            append_quad(x, bottom_base - height, x + bar_width, bottom_base, color)
        data = np.asarray(vertices, dtype="f4")
        self._equalizer_buffer.orphan(data.nbytes)
        self._equalizer_buffer.write(data.tobytes())
        self._equalizer_vao.render(mode=moderngl.TRIANGLES, vertices=len(vertices))

    def _draw_particles(self, particles: Iterable[Particle]) -> None:
        data: list[tuple[float, ...]] = []
        for particle in particles:
            x, y, age = particle[:3]
            scale = particle[3] if len(particle) >= 4 else 1.0
            velocity = particle[4:6] if len(particle) >= 6 else (0.0, 0.0)
            if age < 0.0 or age >= PARTICLE_LIFETIME:
                continue
            remaining = 1.0 - age / PARTICLE_LIFETIME
            radius = max(1.0, 5.0 * scale * remaining)
            speed = math.hypot(*velocity)
            if speed > 1e-6:
                tail_length = min(18.0, speed * 0.045) * remaining
                for segment in range(3, 0, -1):
                    fraction = segment / 3.0
                    data.append(
                        (
                            x - velocity[0] / speed * tail_length * fraction,
                            y - velocity[1] / speed * tail_length * fraction,
                            max(0.7, radius * (1.0 - fraction * 0.65)),
                            0.0,
                            1.0,
                            self.theme_colors["trail"][0] / 255.0,
                            self.theme_colors["trail"][1] / 255.0,
                            self.theme_colors["trail"][2] / 255.0,
                            scale * remaining * remaining * (1.0 - fraction * 0.65),
                        )
                    )
            data.append(
                (
                    x,
                    y,
                    radius,
                    0.0,
                    1.0,
                    self.theme_colors["trail"][0] / 255.0,
                    self.theme_colors["trail"][1] / 255.0,
                    self.theme_colors["trail"][2] / 255.0,
                    scale * remaining * remaining,
                )
            )
        if data:
            self._draw_circles(np.asarray(data, dtype="f4"))

    def _draw_shockwaves(self, shockwaves: Iterable[Shockwave]) -> None:
        data: list[tuple[float, ...]] = []
        for x, y, age in shockwaves:
            if age < 0.0 or age >= 0.55:
                continue
            progress = age / 0.55
            data.append(
                (
                    x,
                    y,
                    8.0 + progress * 92.0,
                    0.0,
                    max(1.0, (1.0 - progress) * 7.0),
                    self.theme_colors["trail"][0] / 255.0,
                    self.theme_colors["trail"][1] / 255.0,
                    self.theme_colors["trail"][2] / 255.0,
                    (1.0 - progress) ** 2 * 0.95,
                )
            )
        if data:
            self._draw_circles(np.asarray(data, dtype="f4"), ring_mode=2)

    def _update_counter(self, count: int) -> None:
        if count == self._displayed_count:
            return
        surface = self._font.render(str(count), True, (105, 85, 125))
        if self._text_texture is not None:
            self._text_texture.release()
        image = pygame.image.tostring(surface, "RGBA", True)
        self._text_texture = self.ctx.texture(surface.get_size(), 4, image)
        self._text_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._text_size = surface.get_size()
        self._displayed_count = count

    def _update_watermark(self, text: str) -> None:
        normalized_text = text.strip()
        if normalized_text == self._displayed_watermark:
            return
        if self._watermark_texture is not None:
            self._watermark_texture.release()
            self._watermark_texture = None
        self._watermark_size = (0, 0)
        self._displayed_watermark = normalized_text
        if not normalized_text:
            return

        surface = self._watermark_font.render(
            normalized_text, True, (220, 195, 255)
        )
        padded_surface = pygame.Surface(
            (surface.get_width() + 20, surface.get_height()),
            flags=pygame.SRCALPHA,
        )
        padded_surface.blit(surface, (10, 0))
        surface = padded_surface
        alpha = pygame.surfarray.pixels_alpha(surface)
        alpha[:] = (alpha.astype(np.float32) * self.watermark_opacity).astype(np.uint8)
        del alpha
        image = pygame.image.tostring(surface, "RGBA", True)
        self._watermark_texture = self.ctx.texture(surface.get_size(), 4, image)
        self._watermark_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._watermark_size = surface.get_size()

    def _draw_watermark(self) -> None:
        if self._watermark_texture is None:
            return
        self._watermark_texture.use(location=0)
        self._text_program["u_center"].value = (
            0.0,
            -2.0 * 120.0 / HEIGHT,
        )
        self._text_program["u_size"].value = (
            2.0 * self._watermark_size[0] / WIDTH,
            2.0 * self._watermark_size[1] / HEIGHT,
        )
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
        self._text_vao.render(mode=moderngl.TRIANGLES, vertices=6)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE)

    def _draw_counter(self) -> None:
        if self._text_texture is None:
            return
        self._text_texture.use(location=0)
        self._text_program["u_center"].value = (0.0, 0.0)
        self._text_program["u_size"].value = (
            2.0 * self._text_size[0] / WIDTH,
            2.0 * self._text_size[1] / HEIGHT,
        )
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
        self._text_vao.render(mode=moderngl.TRIANGLES, vertices=6)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE)

    def _draw_fullscreen(
        self, framebuffer: moderngl.Framebuffer, program: moderngl.Program
    ) -> None:
        framebuffer.use()
        self.ctx.viewport = (0, 0, WIDTH, HEIGHT)
        self._screen_vaos[program].render(mode=moderngl.TRIANGLES, vertices=6)

    def _apply_bloom(self) -> None:
        self.ctx.disable(moderngl.BLEND)

        self._scene_texture.use(location=0)
        self._draw_fullscreen(self._bright_fbo, self._bright_program)

        self._bright_texture.use(location=0)
        self._blur_program["u_direction"].value = (1.0, 0.0)
        self._draw_fullscreen(self._blur_fbo, self._blur_program)

        self._blur_texture.use(location=0)
        self._blur_program["u_direction"].value = (0.0, 1.0)
        self._draw_fullscreen(self._glow_fbo, self._blur_program)

        self._scene_texture.use(location=0)
        self._glow_texture.use(location=1)
        if self._background_texture is not None:
            self._background_texture.use(location=2)
        self._draw_fullscreen(self._output_fbo, self._composite_program)
        self.ctx.enable(moderngl.BLEND)

    def _set_camera_zoom(self, zoom: float) -> None:
        if not math.isfinite(zoom) or zoom < 1.0 or zoom > 1.1:
            raise ValueError("camera_zoom must be between 1.0 and 1.1")
        self.camera_zoom = float(zoom)
        self._circle_program["u_camera_zoom"].value = float(zoom)

    def render(
        self,
        ball_position: Point | None = None,
        trail: Sequence[Point] = (),
        particles: Iterable[Particle] = (),
        rings_remaining: int | None = None,
        bass_energy: float = 0.0,
        ring_angles: Sequence[float] | None = None,
        ring_radii: Sequence[float] | None = None,
        ring_indices: Sequence[int] | None = None,
        simulation_time: float = 0.0,
        shake_amount: float = 0.0,
        pulse_strength: float = PULSE_STRENGTH,
        vibration_strength: float = VIBRATION_STRENGTH,
        background_frame: bytes | None = None,
        sub_bass: float | None = None,
        mid_energy: float = 0.0,
        high_energy: float = 0.0,
        shockwaves: Iterable[Shockwave] = (),
        camera_zoom: float = 1.0,
        spectrum: Sequence[float] | None = None,
    ) -> None:
        """Render a frame from top-left-origin positions and particle ages."""
        if not 0.0 <= pulse_strength <= 2.5:
            raise ValueError("pulse_strength must be between 0.0 and 2.5")
        if not 0.0 <= vibration_strength <= 2.5:
            raise ValueError("vibration_strength must be between 0.0 and 2.5")
        if not 0.0 <= mid_energy <= 1.5 or not 0.0 <= high_energy <= 1.5:
            raise ValueError("Frequency-band energies must be between 0.0 and 1.5")
        if sub_bass is None:
            sub_bass = bass_energy
        if not 0.0 <= sub_bass <= 1.5:
            raise ValueError("sub_bass must be between 0.0 and 1.5")
        if self._background_texture is not None:
            if background_frame is None or len(background_frame) != WIDTH * HEIGHT * 3:
                raise ValueError("Video background mode requires one RGB frame")
            image = np.frombuffer(background_frame, dtype=np.uint8).reshape(
                HEIGHT, WIDTH, 3
            )
            self._background_texture.write(np.flipud(image).tobytes())
        elif background_frame is not None:
            raise ValueError("A background frame was provided for a non-video mode")
        self._scene_fbo.use()
        self.ctx.viewport = (0, 0, WIDTH, HEIGHT)
        self._set_camera_zoom(camera_zoom)
        self._circle_program["u_camera_center"].value = self._center
        self._circle_program["u_sub_bass"].value = float(sub_bass)
        self._circle_program["u_high_energy"].value = float(high_energy)
        self._circle_program["u_vibration_strength"].value = float(
            vibration_strength
        )
        self._circle_program["u_time"].value = float(simulation_time)
        self._circle_program["u_inner_radius"].value = float(INNER_RADIUS)
        self._circle_program["u_outer_radius"].value = float(OUTER_RADIUS)
        background = tuple(channel / 255.0 for channel in BACKGROUND_COLOR)
        if self.background_mode == "solid":
            self._scene_fbo.clear(*background, 1.0)
        else:
            self._scene_fbo.clear(0.0, 0.0, 0.0, 0.0)

        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE)
        self._draw_ambient_particles(simulation_time, sub_bass)
        self._draw_watermark()
        self._draw_equalizer(spectrum)
        if rings_remaining is None:
            rings_remaining = self.ring_count
        active_count = max(0, min(self.ring_count, rings_remaining))
        visible_count = min(active_count, self.visible_ring_count)
        if ring_indices is None:
            removed_count = self.ring_count - active_count
            visible_indices = np.arange(
                removed_count, removed_count + visible_count, dtype=np.intp
            )
        else:
            visible_indices = np.asarray(ring_indices, dtype=np.intp)
            if visible_indices.size > self.visible_ring_count:
                raise ValueError(
                    f"At most {self.visible_ring_count} rings may be visible"
                )
            if np.any(visible_indices < 0) or np.any(
                visible_indices >= self.ring_count
            ):
                raise ValueError("ring_indices contains an out-of-range ring index")
        if ring_radii is not None and len(ring_radii) != visible_indices.size:
            raise ValueError(
                f"Expected {visible_indices.size} ring radii, got {len(ring_radii)}"
            )
        energy = float(np.clip(sub_bass, 0.0, 1.5))
        active_rings = self._ring_data[visible_indices].copy()
        if ring_angles is not None:
            if len(ring_angles) != self.ring_count:
                raise ValueError(
                    f"Expected {self.ring_count} ring angles, got {len(ring_angles)}"
                )
            active_rings[:, 3] = np.asarray(ring_angles)[visible_indices]
        if ring_radii is not None:
            active_rings[:, 2] = ring_radii
        if visible_count:
            radial_fraction = np.clip(
                (active_rings[:, 2] - INNER_RADIUS)
                / max(OUTER_RADIUS - INNER_RADIUS, 1.0),
                0.0,
                1.0,
            )
            inner_band = radial_fraction < (1.0 / 3.0)
            middle_band = (radial_fraction >= (1.0 / 3.0)) & (
                radial_fraction < (2.0 / 3.0)
            )
            pulse_energy = np.where(
                inner_band,
                energy,
                np.where(middle_band, mid_energy, energy * 0.3),
            )
            pulse_amplitude = np.where(
                inner_band, 11.0, np.where(middle_band, 7.0, 1.5)
            )
            phase = simulation_time * math.tau * 2.0 + visible_indices * 0.31
            active_rings[:, 2] += (
                pulse_energy * pulse_strength * pulse_amplitude
                + np.sin(phase)
                * energy
                * 0.5
                * vibration_strength
            )
            active_rings[:, 4] = (
                RING_THICKNESS
                + np.where(inner_band, energy, 0.0) * pulse_strength * 2.4
                + np.where(middle_band, mid_energy, 0.0) * pulse_strength * 1.6
                + np.where(~(inner_band | middle_band), high_energy, 0.0)
                * vibration_strength
                * 0.8
            )
            active_rings[:, 5:8] *= (
                1.0 + np.maximum(energy, np.maximum(mid_energy, high_energy)) * 0.2
            )
        self._draw_circles(active_rings, ring_mode=True)

        self._update_counter(rings_remaining)
        self._draw_counter()

        trail_points = trail[-TRAIL_LENGTH:]
        self._draw_ribbon(trail_points)

        if ball_position is not None:
            ball_data = np.array(
                [
                    (
                        ball_position[0],
                        ball_position[1],
                        BALL_RADIUS * 1.4,
                        0.0,
                        1.0,
                        self.theme_colors["ball"][0] / 255.0,
                        self.theme_colors["ball"][1] / 255.0,
                        self.theme_colors["ball"][2] / 255.0,
                        1.0,
                    ),
                    (
                        ball_position[0],
                        ball_position[1],
                        BALL_RADIUS * 0.48,
                        0.0,
                        1.0,
                        min(1.0, self.theme_colors["ball"][0] / 255.0 * 0.35 + 0.65),
                        min(1.0, self.theme_colors["ball"][1] / 255.0 * 0.35 + 0.65),
                        min(1.0, self.theme_colors["ball"][2] / 255.0 * 0.35 + 0.65),
                        1.0,
                    )
                ],
                dtype="f4",
            )
            self._draw_circles(ball_data)

        self._draw_shockwaves(shockwaves)
        self._draw_particles(particles)
        self._apply_bloom()

    def read_frame(self) -> bytes:
        """Return the completed RGB/RGBA frame with its first row at the top."""
        components = 4 if self.background_mode == "transparent" else 3
        raw = self._output_fbo.read(components=components, alignment=1)
        row_size = WIDTH * components
        return b"".join(
            raw[row * row_size : (row + 1) * row_size]
            for row in range(HEIGHT - 1, -1, -1)
        )

    def close(self) -> None:
        """Release OpenGL resources and the hidden pygame context window."""
        if self._text_texture is not None:
            self._text_texture.release()
        if self._watermark_texture is not None:
            self._watermark_texture.release()
        self._circle_vao.release()
        self._text_vao.release()
        self._ribbon_vao.release()
        self._equalizer_vao.release()
        for vao in self._screen_vaos.values():
            vao.release()
        for buffer in (
            self._circle_corners,
            self._circle_instances,
            self._quad_buffer,
            self._text_buffer,
            self._ribbon_buffer,
            self._equalizer_buffer,
        ):
            buffer.release()
        for program in (
            self._circle_program,
            self._bright_program,
            self._blur_program,
            self._composite_program,
            self._text_program,
            self._ribbon_program,
            self._equalizer_program,
        ):
            program.release()
        for framebuffer in (
            self._scene_fbo,
            self._bright_fbo,
            self._blur_fbo,
            self._glow_fbo,
            self._output_fbo,
        ):
            framebuffer.release()
        for texture in (
            self._scene_texture,
            self._bright_texture,
            self._blur_texture,
            self._glow_texture,
            self._output_texture,
        ):
            texture.release()
        if self._background_texture is not None:
            self._background_texture.release()
        self.ctx.release()
        pygame.display.quit()
