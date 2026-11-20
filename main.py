"""Generate the vertical neon-ring video and mux its audio."""

from __future__ import annotations

import math
import os
import random
import subprocess
import tempfile
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import imageio_ffmpeg

from audio import AudioProcessor, mux_audio_video, synthesize_impact_audio
from config import (
    AUDIO_SENSITIVITY,
    BALL_RADIUS,
    BALL_SPEED,
    BREAK_RADIAL_RETENTION,
    BOUNCE_RESTITUTION,
    FPS,
    GAP_AIM_ASSIST,
    GAP_AIM_JITTER_DEG,
    GAP_ANGLE_DEG,
    GRAVITY,
    HEIGHT,
    INNER_RADIUS,
    MAX_DURATION,
    MAX_SPEED,
    MIN_BOUNCE_SPEED,
    OUTER_RADIUS,
    OUTPUT_FILE,
    PARTICLES_PER_HIT,
    PARTICLE_LIFETIME,
    PARTICLE_SPEED,
    PULSE_STRENGTH,
    RING_ROTATION_SPEED,
    RING_BREAK_ROTATION_GAIN,
    RING_BREAK_COOLDOWN,
    SPEED_GAIN_PER_BREAK,
    TRAIL_LENGTH,
    VIBRATION_STRENGTH,
    VISIBLE_RINGS,
    WATERMARK_TEXT,
    WIDTH,
)
from gui import StudioSettings, launch_menu
from renderer import Renderer

SUB_STEPS = 10
BEAT_PARTICLE_COUNT = 12


@dataclass
class _Particle:
    x: float
    y: float
    vx: float
    vy: float
    age: float = 0.0
    scale: float = 1.0


def _spawn_hit_particles(
    particles: list[_Particle], x: float, y: float, rng: random.Random
) -> None:
    for _ in range(PARTICLES_PER_HIT):
        angle = rng.uniform(0.0, math.tau)
        speed = PARTICLE_SPEED * rng.uniform(0.45, 1.0)
        particles.append(
            _Particle(
                x,
                y,
                math.cos(angle) * speed,
                math.sin(angle) * speed,
            )
        )


def _spawn_beat_particles(
    particles: list[_Particle],
    ball_position: tuple[float, float],
    ring_radius: float,
    center: tuple[float, float],
    rng: random.Random,
) -> None:
    for _ in range(BEAT_PARTICLE_COUNT):
        angle = rng.uniform(0.0, math.tau)
        if rng.random() < 0.5:
            x = center[0] + math.cos(angle) * ring_radius
            y = center[1] + math.sin(angle) * ring_radius
            speed = PARTICLE_SPEED * 0.18
            scale = 0.45
        else:
            x, y = ball_position
            speed = PARTICLE_SPEED * 0.25
            scale = 0.55
        particles.append(
            _Particle(
                x,
                y,
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                scale=scale,
            )
        )


def _advance_particles(particles: list[_Particle], dt: float) -> None:
    for particle in particles:
        particle.x += particle.vx * dt
        particle.y += particle.vy * dt
        particle.age += dt
    particles[:] = [
        particle for particle in particles if particle.age < PARTICLE_LIFETIME
    ]


def _advance_shockwaves(shockwaves: list[tuple[float, float, float]], dt: float) -> None:
    shockwaves[:] = [
        (x, y, age + dt)
        for x, y, age in shockwaves
        if age + dt < 0.55
    ]


def _angle_delta(angle: float, ring_angle: float) -> float:
    """Signed wrapped angular difference in screen coordinates (x right, y down)."""
    return math.atan2(
        math.sin(angle - ring_angle),
        math.cos(angle - ring_angle),
    )


def _is_inside_ring_gap(angle: float, ring_angle: float, radius: float) -> bool:
    half_gap = math.radians(GAP_ANGLE_DEG / 2.0)
    ball_angular_margin = math.asin(
        min(1.0, BALL_RADIUS / max(radius, 1.0))
    )
    return abs(_angle_delta(angle, ring_angle)) < half_gap - ball_angular_margin


def _clamp_ball_inside_ring(
    ball_x: float,
    ball_y: float,
    velocity_x: float,
    velocity_y: float,
    center: tuple[float, float],
    ring_radius: float,
    ring_angle: float,
    min_bounce_speed: float,
    rng: random.Random,
) -> tuple[float, float, float, float]:
    """Project the ball to the inner side of a ring and reflect outward motion."""
    offset_x = ball_x - center[0]
    offset_y = ball_y - center[1]
    distance = math.hypot(offset_x, offset_y)
    normal_x = offset_x / max(distance, 1e-8)
    normal_y = offset_y / max(distance, 1e-8)
    contact_radius = max(0.0, ring_radius - BALL_RADIUS - 0.5)
    ball_x = center[0] + normal_x * contact_radius
    ball_y = center[1] + normal_y * contact_radius

    radial_speed = velocity_x * normal_x + velocity_y * normal_y
    if radial_speed > 0.0:
        velocity_x -= 2.0 * radial_speed * normal_x
        velocity_y -= 2.0 * radial_speed * normal_y
        velocity_x *= BOUNCE_RESTITUTION
        velocity_y *= BOUNCE_RESTITUTION

    angle_offset = math.radians(rng.uniform(-8.0, 8.0))
    cosine = math.cos(angle_offset)
    sine = math.sin(angle_offset)
    velocity_x, velocity_y = (
        velocity_x * cosine - velocity_y * sine,
        velocity_x * sine + velocity_y * cosine,
    )
    velocity_angle = math.atan2(velocity_y, velocity_x)
    aim_angle = _angle_delta(ring_angle, velocity_angle)
    aim_angle = aim_angle * GAP_AIM_ASSIST + math.radians(
        rng.uniform(-GAP_AIM_JITTER_DEG, GAP_AIM_JITTER_DEG)
    )
    cosine = math.cos(aim_angle)
    sine = math.sin(aim_angle)
    velocity_x, velocity_y = (
        velocity_x * cosine - velocity_y * sine,
        velocity_x * sine + velocity_y * cosine,
    )
    radial_speed = velocity_x * normal_x + velocity_y * normal_y
    if radial_speed >= 0.0:
        velocity_x -= (radial_speed + 1.0) * normal_x
        velocity_y -= (radial_speed + 1.0) * normal_y

    speed = math.hypot(velocity_x, velocity_y)
    if speed < min_bounce_speed:
        if speed <= 1e-8:
            velocity_x = -normal_x * min_bounce_speed
            velocity_y = -normal_y * min_bounce_speed
        else:
            scale = min_bounce_speed / speed
            velocity_x *= scale
            velocity_y *= scale
    velocity_x, velocity_y = _limit_speed(velocity_x, velocity_y)
    return ball_x, ball_y, velocity_x, velocity_y


def _limit_speed(velocity_x: float, velocity_y: float) -> tuple[float, float]:
    speed = math.hypot(velocity_x, velocity_y)
    if speed > MAX_SPEED:
        scale = MAX_SPEED / speed
        return velocity_x * scale, velocity_y * scale
    return velocity_x, velocity_y


def _ring_slot_radii(
    count: int, visible_rings: int = VISIBLE_RINGS
) -> list[float]:
    spacing = (OUTER_RADIUS - INNER_RADIUS) / visible_rings
    return [
        INNER_RADIUS + (index + 0.5) * spacing
        for index in range(min(count, visible_rings))
    ]


def _rendered_ring_radius(
    radius: float,
    ring_index: int,
    simulation_time: float,
    sub_bass: float,
    mid_energy: float,
    pulse_strength: float,
    vibration_strength: float,
) -> float:
    radial_fraction = min(
        1.0,
        max(0.0, (radius - INNER_RADIUS) / max(OUTER_RADIUS - INNER_RADIUS, 1.0)),
    )
    if radial_fraction < 1.0 / 3.0:
        pulse_energy, pulse_amplitude = sub_bass, 11.0
    elif radial_fraction < 2.0 / 3.0:
        pulse_energy, pulse_amplitude = mid_energy, 7.0
    else:
        pulse_energy, pulse_amplitude = sub_bass * 0.3, 1.5
    phase = simulation_time * math.tau * 2.0 + ring_index * 0.31
    return (
        radius
        + pulse_energy * pulse_strength * pulse_amplitude
        + math.sin(phase) * sub_bass * 0.5 * vibration_strength
    )


def _ffmpeg_command(
    ffmpeg_path: str, temp_path: Path, transparent: bool = False
) -> list[str]:
    input_pixel_format = "rgba" if transparent else "rgb24"
    if transparent:
        video_codec = ["-c:v", "png", "-pix_fmt", "rgba"]
    else:
        video_codec = [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "18",
            "-preset",
            "fast",
        ]
    return [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        input_pixel_format,
        "-s:v",
        f"{WIDTH}x{HEIGHT}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-an",
        *video_codec,
        str(temp_path),
    ]


def _loop_background_frames(path: str):
    while True:
        reader = imageio_ffmpeg.read_frames(
            path,
            pix_fmt="rgb24",
            output_params=["-vf", f"scale={WIDTH}:{HEIGHT}"],
        )
        try:
            next(reader)
            frame_count = 0
            for frame in reader:
                frame_count += 1
                if len(frame) != WIDTH * HEIGHT * 3:
                    raise RuntimeError(
                        f"Decoded background frame has unexpected size: {len(frame)}"
                    )
                yield frame
            if frame_count == 0:
                raise ValueError("Background video contains no frames")
        finally:
            reader.close()


def generate_video(
    audio_path: str | None,
    duration: float,
    ring_count: int,
    output_path: str = OUTPUT_FILE,
    watermark_text: str = WATERMARK_TEXT,
    visible_rings: int = VISIBLE_RINGS,
    ball_speed: float = BALL_SPEED,
    gravity: float = GRAVITY,
    theme_colors: dict[str, tuple[int, int, int]] | None = None,
    watermark_opacity: float = 0.18,
    asmr_hits: bool = False,
    progress_callback: Callable[[int, int, float, float], None] | None = None,
    pulse_strength: float = PULSE_STRENGTH,
    vibration_strength: float = VIBRATION_STRENGTH,
    background_mode: str = "solid",
    background_video_path: str = "",
    dynamics_level: str = "Dynamic",
    audio_sensitivity: float = AUDIO_SENSITIVITY,
) -> None:
    if duration <= 0:
        raise ValueError("duration must be greater than zero")
    if ring_count <= 0:
        raise ValueError("ring_count must be greater than zero")
    if visible_rings <= 0 or visible_rings > ring_count:
        raise ValueError("visible_rings must be between one and ring_count")
    if not 0.0 <= pulse_strength <= 2.5:
        raise ValueError("pulse_strength must be between 0.0 and 2.5")
    if not 0.0 <= vibration_strength <= 2.5:
        raise ValueError("vibration_strength must be between 0.0 and 2.5")
    if not 0.2 <= audio_sensitivity <= 3.0:
        raise ValueError("audio_sensitivity must be between 0.2 and 3.0")
    if background_mode not in {"solid", "transparent", "video_bg", "video_mask"}:
        raise ValueError(f"Unsupported background mode: {background_mode}")
    if background_mode in {"video_bg", "video_mask"} and not Path(
        background_video_path
    ).is_file():
        raise ValueError("A valid background video is required for this mode")
    camera_punch_max = {"Chill": 0.02, "Dynamic": 0.05, "Extreme": 0.08}.get(
        dynamics_level
    )
    if camera_punch_max is None:
        raise ValueError(f"Unsupported dynamics level: {dynamics_level}")

    audio = AudioProcessor(
        audio_path=audio_path,
        max_duration=duration,
        sensitivity=audio_sensitivity,
    )
    total_frames = audio.total_frames
    if total_frames <= 0:
        raise ValueError("Audio analysis produced no frames to render")

    final_path = Path(output_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_extension = ".mov" if background_mode == "transparent" else ".mp4"
    temp_path = final_path.with_name(
        f".{final_path.stem}.temp_video{temp_extension}"
    )
    impact_path = final_path.with_name(f".{final_path.stem}.hits.wav")

    center = (WIDTH / 2.0, HEIGHT / 2.0)
    ball_x, ball_y = center
    velocity_x = ball_speed * 0.6
    velocity_y = -ball_speed * 0.8
    rings_remaining = ring_count
    ring_spacing = (OUTER_RADIUS - INNER_RADIUS) / visible_rings
    rng = random.Random()
    ring_angles = [rng.uniform(0.0, math.tau) for _ in range(ring_count)]
    ring_angular_speeds = [
        RING_ROTATION_SPEED * (1.0 if index % 2 == 0 else -1.0)
        * (0.8 + 0.4 * index / max(1, ring_count - 1))
        for index in range(ring_count)
    ]
    visible_count = min(ring_count, visible_rings)
    ring_indices = list(range(visible_count))
    ring_radii = _ring_slot_radii(ring_count, visible_rings)
    transition_start: list[float] | None = None
    transition_elapsed = 0.0
    transition_duration = 0.12
    break_cooldown_duration = RING_BREAK_COOLDOWN
    break_cooldown = 0.0
    min_bounce_speed = MIN_BOUNCE_SPEED
    simulation_time = 0.0
    camera_zoom = 1.0
    camera_zoom_velocity = 0.0
    trail: deque[tuple[float, float]] = deque(maxlen=TRAIL_LENGTH)
    particles: list[_Particle] = []
    substep_dt = 1.0 / (FPS * SUB_STEPS)
    process: subprocess.Popen[bytes] | None = None
    renderer: Renderer | None = None
    completed = False
    bounce_times: list[float] = []
    break_times: list[float] = []
    shockwaves: list[tuple[float, float, float]] = []
    render_started = time.monotonic()
    last_progress_time = render_started
    background_frames = (
        _loop_background_frames(background_video_path)
        if background_mode in {"video_bg", "video_mask"}
        else None
    )

    try:
        renderer = Renderer(
            ring_count=ring_count,
            watermark_text=watermark_text,
            visible_rings=visible_rings,
            theme_colors=theme_colors,
            watermark_opacity=watermark_opacity,
            background_mode=background_mode,
        )
        with tempfile.TemporaryFile() as ffmpeg_stderr:
            process = subprocess.Popen(
                _ffmpeg_command(
                    imageio_ffmpeg.get_ffmpeg_exe(),
                    temp_path,
                    transparent=background_mode == "transparent",
                ),
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=ffmpeg_stderr,
            )
            if process.stdin is None:
                raise RuntimeError("Could not open ffmpeg stdin for raw video frames")

            sub_bass_data = getattr(audio, "sub_bass", None)
            if sub_bass_data is None:
                sub_bass_data = audio.bass_energy
            mid_energy_data = getattr(audio, "mid_energy", None)
            high_energy_data = getattr(audio, "high_energy", None)
            spectrum_data = getattr(audio, "spectrum", None)
            for frame_index in range(total_frames):
                sub_bass = float(sub_bass_data[frame_index])
                mid_energy = (
                    float(mid_energy_data[frame_index])
                    if mid_energy_data is not None
                    else 0.0
                )
                high_energy = (
                    float(high_energy_data[frame_index])
                    if high_energy_data is not None
                    else 0.0
                )
                broke_ring_this_tick = False
                for _ in range(SUB_STEPS):
                    for index in ring_indices:
                        ring_angles[index] = (
                            ring_angles[index]
                            + ring_angular_speeds[index] * substep_dt
                        ) % math.tau
                    simulation_time += substep_dt
                    break_cooldown = max(0.0, break_cooldown - substep_dt)
                    camera_target = 1.0 + camera_punch_max * max(
                        0.0, min(1.0, (sub_bass - 0.65) / 0.35)
                    )
                    camera_zoom_velocity += (
                        (camera_target - camera_zoom) * 90.0
                        - camera_zoom_velocity * 18.0
                    ) * substep_dt
                    camera_zoom = max(
                        1.0,
                        min(1.0 + camera_punch_max, camera_zoom + camera_zoom_velocity * substep_dt),
                    )

                    if transition_start is not None:
                        transition_elapsed = min(
                            transition_duration, transition_elapsed + substep_dt
                        )
                        progress = transition_elapsed / transition_duration
                        eased_progress = progress * progress * (3.0 - 2.0 * progress)
                        targets = _ring_slot_radii(rings_remaining, visible_rings)
                        ring_radii = [
                            start + (target - start) * eased_progress
                            for start, target in zip(transition_start, targets)
                        ]
                        if transition_elapsed >= transition_duration:
                            ring_radii = targets
                            transition_start = None

                    previous_distance = math.hypot(
                        ball_x - center[0], ball_y - center[1]
                    )
                    velocity_y += gravity * substep_dt
                    velocity_x, velocity_y = _limit_speed(velocity_x, velocity_y)
                    ball_x += velocity_x * substep_dt
                    ball_y += velocity_y * substep_dt

                    offset_x = ball_x - center[0]
                    offset_y = ball_y - center[1]
                    distance = math.hypot(offset_x, offset_y)
                    while rings_remaining > 0 and ring_indices:
                        if break_cooldown > 0.0 and ring_radii:
                            ring_radii[0] = max(
                                ring_radii[0],
                                distance + BALL_RADIUS + 8.0,
                            )
                        ring_index = ring_indices[0]
                        ring_radius = _rendered_ring_radius(
                            ring_radii[0],
                            ring_index,
                            simulation_time,
                            sub_bass,
                            mid_energy,
                            pulse_strength,
                            vibration_strength,
                        )
                        collision_radius = ring_radius - BALL_RADIUS
                        if distance + BALL_RADIUS < ring_radius:
                            break

                        angle = math.atan2(offset_y, offset_x)
                        in_gap = _is_inside_ring_gap(
                            angle, ring_angles[ring_index], ring_radius
                        )
                        if in_gap:
                            if distance < collision_radius:
                                break
                            crossed_outward = (
                                previous_distance < collision_radius <= distance
                                and distance > previous_distance
                            )
                            if (
                                not crossed_outward
                                or broke_ring_this_tick
                                or break_cooldown > 0.0
                            ):
                                ball_x, ball_y, velocity_x, velocity_y = (
                                    _clamp_ball_inside_ring(
                                        ball_x,
                                        ball_y,
                                        velocity_x,
                                        velocity_y,
                                        center,
                                        ring_radius,
                                        ring_angles[ring_index],
                                        min_bounce_speed,
                                        rng,
                                    )
                                )
                                if asmr_hits:
                                    bounce_times.append(simulation_time)
                                break

                            hit_x = (
                                center[0]
                                + offset_x / max(distance, 1e-8) * ring_radius
                            )
                            hit_y = (
                                center[1]
                                + offset_y / max(distance, 1e-8) * ring_radius
                            )
                            _spawn_hit_particles(particles, hit_x, hit_y, rng)
                            shockwaves.append((hit_x, hit_y, 0.0))
                            radial_speed = (
                                velocity_x * offset_x + velocity_y * offset_y
                            ) / max(distance, 1e-8)
                            radial_retention = 1.0 - BREAK_RADIAL_RETENTION
                            velocity_x -= radial_retention * radial_speed * (
                                offset_x / max(distance, 1e-8)
                            )
                            velocity_y -= radial_retention * radial_speed * (
                                offset_y / max(distance, 1e-8)
                            )
                            if asmr_hits:
                                break_times.append(simulation_time)

                            previous_visible_indices = set(ring_indices)
                            rings_remaining -= 1
                            speed = math.hypot(velocity_x, velocity_y)
                            if speed > 1e-8:
                                accelerated_speed = min(
                                    MAX_SPEED, speed * SPEED_GAIN_PER_BREAK
                                )
                                speed_scale = accelerated_speed / speed
                                velocity_x *= speed_scale
                                velocity_y *= speed_scale
                            min_bounce_speed = min(
                                MAX_SPEED,
                                min_bounce_speed * SPEED_GAIN_PER_BREAK,
                            )
                            ring_radii.pop(0)
                            visible_count = min(rings_remaining, visible_rings)
                            first_ring_index = ring_count - rings_remaining
                            for index in range(first_ring_index, ring_count):
                                ring_angular_speeds[index] *= (
                                    RING_BREAK_ROTATION_GAIN
                                )
                            ring_indices = list(
                                range(
                                    first_ring_index,
                                    first_ring_index + visible_count,
                                )
                            )
                            for index in ring_indices:
                                if index not in previous_visible_indices:
                                    ring_angles[index] = (
                                        ring_angular_speeds[index] * simulation_time
                                    ) % math.tau
                            if len(ring_radii) < visible_count:
                                ring_radii.append(OUTER_RADIUS + ring_spacing * 0.5)

                            if rings_remaining and ring_radii:
                                current_distance = math.hypot(
                                    ball_x - center[0], ball_y - center[1]
                                )
                                required_radius = (
                                    current_distance
                                    + BALL_RADIUS
                                    + 8.0
                                )
                                ring_radii[0] = max(ring_radii[0], required_radius)

                            transition_start = ring_radii.copy()
                            transition_elapsed = 0.0
                            break_cooldown = break_cooldown_duration
                            broke_ring_this_tick = True
                            offset_x = ball_x - center[0]
                            offset_y = ball_y - center[1]
                            distance = math.hypot(offset_x, offset_y)
                            break

                        ball_x, ball_y, velocity_x, velocity_y = (
                            _clamp_ball_inside_ring(
                                ball_x,
                                ball_y,
                                velocity_x,
                                velocity_y,
                                center,
                                ring_radius,
                                ring_angles[ring_index],
                                min_bounce_speed,
                                rng,
                            )
                        )
                        if asmr_hits:
                            bounce_times.append(simulation_time)
                        offset_x = ball_x - center[0]
                        offset_y = ball_y - center[1]
                        distance = math.hypot(offset_x, offset_y)
                        break

                    _advance_particles(particles, substep_dt)
                    _advance_shockwaves(shockwaves, substep_dt)

                trail.append((ball_x, ball_y))
                active_ring_radius = (
                    _rendered_ring_radius(
                        ring_radii[0],
                        ring_indices[0],
                        simulation_time,
                        sub_bass,
                        mid_energy,
                        pulse_strength,
                        vibration_strength,
                    )
                    if ring_radii
                    else OUTER_RADIUS
                )
                if bool(audio.is_beat[frame_index]):
                    _spawn_beat_particles(
                        particles,
                        (ball_x, ball_y),
                        active_ring_radius,
                        center,
                        rng,
                    )

                renderer.render(
                    ball_position=(ball_x, ball_y),
                    trail=tuple(trail),
                    particles=[
                        (
                            particle.x,
                            particle.y,
                            particle.age,
                            particle.scale,
                            particle.vx,
                            particle.vy,
                        )
                        for particle in particles
                    ],
                    rings_remaining=rings_remaining,
                    bass_energy=sub_bass,
                    ring_angles=ring_angles,
                    ring_radii=ring_radii,
                    ring_indices=ring_indices,
                    simulation_time=simulation_time,
                    pulse_strength=pulse_strength,
                    vibration_strength=vibration_strength,
                    sub_bass=sub_bass,
                    mid_energy=mid_energy,
                    high_energy=high_energy,
                    shockwaves=tuple(shockwaves),
                    camera_zoom=camera_zoom,
                    spectrum=(
                        spectrum_data[frame_index]
                        if spectrum_data is not None
                        else None
                    ),
                    background_frame=(
                        next(background_frames) if background_frames is not None else None
                    ),
                )
                frame = renderer.read_frame()
                components = 4 if background_mode == "transparent" else 3
                expected_size = WIDTH * HEIGHT * components
                if len(frame) != expected_size:
                    raise RuntimeError(
                        f"Renderer returned {len(frame)} bytes; expected {expected_size}"
                    )
                process.stdin.write(frame)

                now = time.monotonic()
                if progress_callback is not None and (
                    frame_index == total_frames - 1 or now - last_progress_time >= 0.15
                ):
                    elapsed = max(now - render_started, 1e-6)
                    render_fps = (frame_index + 1) / elapsed
                    eta = (total_frames - frame_index - 1) / max(render_fps, 1e-6)
                    progress_callback(frame_index + 1, total_frames, render_fps, eta)
                    last_progress_time = now

                if frame_index == total_frames - 1 or (frame_index + 1) % max(
                    1, total_frames // 100
                ) == 0:
                    print(
                        f"\rFrame {frame_index + 1} / {total_frames} "
                        f"({(frame_index + 1) * 100 / total_frames:.1f}%)",
                        end="\n" if frame_index == total_frames - 1 else "",
                        flush=True,
                    )

            process.stdin.close()
            return_code = process.wait()
            ffmpeg_stderr.seek(0)
            error_output = ffmpeg_stderr.read()
            if return_code:
                raise subprocess.CalledProcessError(
                    return_code,
                    process.args,
                    stderr=error_output,
                )
        completed = True
    except BaseException:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        raise
    finally:
        if renderer is not None:
            renderer.close()
        if background_frames is not None:
            background_frames.close()
        if not completed and temp_path.exists():
            temp_path.unlink()

    try:
        valid_audio_path = (
            audio_path if audio_path is not None and Path(audio_path).is_file() else None
        )
        if asmr_hits:
            synthesize_impact_audio(
                impact_path,
                bounce_times,
                break_times,
                total_frames / FPS,
            )
        if valid_audio_path is not None or asmr_hits:
            mux_audio_video(
                str(temp_path),
                valid_audio_path,
                str(final_path),
                str(impact_path) if asmr_hits else None,
            )
        else:
            os.replace(temp_path, final_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
        if impact_path.exists():
            impact_path.unlink()


def run() -> None:
    def render(
        settings: "StudioSettings",
        progress_callback: Callable[[int, int, float, float], None],
    ) -> None:
        duration = settings.duration
        if settings.use_track_length and settings.audio_path:
            import librosa

            duration = float(librosa.get_duration(path=settings.audio_path))
            if duration <= 0.0:
                raise ValueError("Selected audio track has no playable duration")
        elif settings.use_track_length:
            duration = float(MAX_DURATION)
        generate_video(
            settings.audio_path,
            duration,
            settings.ring_count,
            output_path=settings.output_path,
            watermark_text=settings.watermark_text,
            visible_rings=settings.visible_rings,
            ball_speed=settings.ball_speed,
            gravity=settings.gravity,
            theme_colors=settings.theme_colors,
            watermark_opacity=settings.watermark_opacity,
            asmr_hits=settings.asmr_hits,
            progress_callback=progress_callback,
            pulse_strength=settings.pulse_strength,
            vibration_strength=settings.vibration_strength,
            background_mode=settings.background_mode,
            background_video_path=settings.background_video_path,
            dynamics_level=settings.dynamics_level,
            audio_sensitivity=settings.audio_sensitivity,
        )

    launch_menu(render)


if __name__ == "__main__":
    run()
