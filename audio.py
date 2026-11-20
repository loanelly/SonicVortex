"""Audio analysis and audio/video muxing helpers."""

from __future__ import annotations

import subprocess
import warnings
from pathlib import Path

import imageio_ffmpeg
import librosa
import numpy as np
from scipy.signal import find_peaks

from config import AUDIO_FILE, AUDIO_SENSITIVITY, FPS, MAX_DURATION

_SAMPLE_RATE = 22050
_STFT_HOP_LENGTH = 256
_SPECTRUM_BINS = 48


class AudioProcessor:
    """Load audio and calculate per-video-frame bass energy and beat markers."""

    def __init__(
        self,
        audio_path: str | None = AUDIO_FILE,
        max_duration: float = MAX_DURATION,
        sensitivity: float = AUDIO_SENSITIVITY,
    ) -> None:
        if max_duration <= 0.0:
            raise ValueError("max_duration must be greater than zero")
        if not 0.2 <= sensitivity <= 3.0:
            raise ValueError("sensitivity must be between 0.2 and 3.0")
        self.audio_path = audio_path
        self.duration = float(max_duration)
        self.sample_rate = _SAMPLE_RATE
        self.sensitivity = float(sensitivity)

        audio_file = Path(audio_path) if audio_path else None
        if audio_file is not None and audio_file.is_file():
            samples, self.sample_rate = librosa.load(
                str(audio_file),
                sr=_SAMPLE_RATE,
                mono=True,
                duration=self.duration,
            )
            samples = self._fit_duration(samples)
        else:
            warnings.warn(
                f"Audio file '{audio_path}' was not found or selected; "
                f"using a {self.duration:g}-second test beat.",
                RuntimeWarning,
                stacklevel=2,
            )
            samples = self._make_test_beat()

        self.total_frames = int(np.ceil(self.duration * FPS))
        (
            self.sub_bass,
            self.mid_energy,
            self.high_energy,
            self.spectrum,
            self.is_beat,
        ) = self._analyze(samples)
        self.bass_energy = self.sub_bass

    def _fit_duration(self, samples: np.ndarray) -> np.ndarray:
        target_samples = max(1, int(round(self.duration * self.sample_rate)))
        if samples.size == 0:
            warnings.warn(
                f"Audio file '{self.audio_path}' contains no samples; "
                "using a test beat instead.",
                RuntimeWarning,
                stacklevel=2,
            )
            return self._make_test_beat()
        if samples.size < target_samples:
            repeats = int(np.ceil(target_samples / samples.size))
            samples = np.tile(samples, repeats)
        return np.asarray(samples[:target_samples], dtype=np.float32)

    def _make_test_beat(self) -> np.ndarray:
        sample_count = max(1, int(round(self.duration * self.sample_rate)))
        time = np.arange(sample_count, dtype=np.float32) / self.sample_rate
        beat_phase = np.mod(time, 0.5)
        envelope = np.exp(-beat_phase * 22.0) * (beat_phase < 0.12)
        return (0.75 * envelope * np.sin(2.0 * np.pi * 70.0 * time)).astype(
            np.float32
        )

    def _analyze(
        self, samples: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        if not self.total_frames:
            empty = np.zeros(0, dtype=np.float32)
            return (
                empty,
                empty.copy(),
                empty.copy(),
                np.zeros((0, _SPECTRUM_BINS), dtype=np.float32),
                np.zeros(0, dtype=bool),
            )

        n_fft = 4096
        spectrum = np.abs(
            librosa.stft(
                np.asarray(samples, dtype=np.float32),
                n_fft=n_fft,
                hop_length=_STFT_HOP_LENGTH,
                center=True,
            )
        )
        frequencies = librosa.fft_frequencies(
            sr=self.sample_rate, n_fft=n_fft
        )
        band_ranges = ((20.0, 120.0), (250.0, 2000.0), (4000.0, 12000.0))
        stft_times = librosa.frames_to_time(
            np.arange(spectrum.shape[1]),
            sr=self.sample_rate,
            hop_length=_STFT_HOP_LENGTH,
        )
        frame_times = np.arange(self.total_frames, dtype=np.float64) / FPS
        raw_band_energies: list[np.ndarray] = []
        for low_hz, high_hz in band_ranges:
            mask = (frequencies >= low_hz) & (frequencies <= high_hz)
            if not np.any(mask):
                raise RuntimeError(f"No STFT bins available for {low_hz:g}-{high_hz:g} Hz")
            raw = np.sqrt(np.mean(np.square(spectrum[mask], dtype=np.float64), axis=0))
            frame_energy = np.interp(frame_times, stft_times, raw).astype(np.float32)
            raw_band_energies.append(frame_energy)

        reference_level = max(
            (float(np.percentile(energy, 95)) for energy in raw_band_energies),
            default=0.0,
        )
        band_energies = [
            self._normalize_band(energy, reference_level)
            for energy in raw_band_energies
        ]
        band_energies = [
            np.clip(energy * self.sensitivity, 0.0, 1.5).astype(np.float32)
            for energy in band_energies
        ]

        sub_bass, mid_energy, high_energy = (
            self._smooth_band(energy) for energy in band_energies
        )
        spectrum = self._analyze_spectrum(spectrum, frequencies, frame_times, reference_level)

        min_distance = max(1, int(round(0.25 * FPS)))
        prominence = max(0.08, 0.12 * float(np.ptp(sub_bass)))
        peaks, _ = find_peaks(
            sub_bass,
            distance=min_distance,
            prominence=prominence,
            height=max(0.2, float(np.percentile(sub_bass, 60))),
        )
        beats = np.zeros(self.total_frames, dtype=bool)
        beats[peaks] = True
        return sub_bass, mid_energy, high_energy, spectrum, beats

    def _analyze_spectrum(
        self,
        spectrum: np.ndarray,
        frequencies: np.ndarray,
        frame_times: np.ndarray,
        reference_level: float,
    ) -> np.ndarray:
        edges = np.geomspace(30.0, 12000.0, _SPECTRUM_BINS + 1)
        stft_times = librosa.frames_to_time(
            np.arange(spectrum.shape[1]),
            sr=self.sample_rate,
            hop_length=_STFT_HOP_LENGTH,
        )
        bins = np.zeros((_SPECTRUM_BINS, len(frame_times)), dtype=np.float32)
        for index, (low, high) in enumerate(zip(edges[:-1], edges[1:])):
            mask = (frequencies >= low) & (frequencies < high)
            if not np.any(mask):
                continue
            energy = np.sqrt(
                np.mean(np.square(spectrum[mask], dtype=np.float64), axis=0)
            )
            frame_energy = np.interp(frame_times, stft_times, energy).astype(
                np.float32
            )
            level = float(np.percentile(frame_energy, 95))
            if level > max(reference_level * 5e-2, np.finfo(np.float32).eps):
                bins[index] = np.clip(
                    frame_energy / level * self.sensitivity, 0.0, 1.5
                )
        return np.stack(
            [self._smooth_band(row) for row in bins], axis=1
        ).astype(np.float32)

    @staticmethod
    def _normalize_band(
        energy: np.ndarray, reference_level: float | None = None
    ) -> np.ndarray:
        if not np.any(energy):
            return np.zeros_like(energy, dtype=np.float32)
        level = float(np.percentile(energy, 95))
        noise_floor = (
            reference_level * 5e-2
            if reference_level is not None
            else np.finfo(np.float32).eps
        )
        if level <= max(noise_floor, np.finfo(np.float32).eps):
            return np.zeros_like(energy, dtype=np.float32)
        return np.clip(energy / level, 0.0, 1.0).astype(np.float32)

    @staticmethod
    def _smooth_band(
        energy: np.ndarray, attack_seconds: float = 0.035, release_seconds: float = 0.22
    ) -> np.ndarray:
        result = np.empty_like(energy, dtype=np.float32)
        attack = 1.0 - np.exp(-1.0 / (FPS * attack_seconds))
        release = 1.0 - np.exp(-1.0 / (FPS * release_seconds))
        previous = 0.0
        for index, value in enumerate(energy):
            coefficient = attack if value > previous else release
            previous += coefficient * (float(value) - previous)
            result[index] = previous
        return result


def synthesize_impact_audio(
    output_path: str | Path,
    bounce_times: list[float],
    break_times: list[float],
    duration: float,
    sample_rate: int = _SAMPLE_RATE,
) -> None:
    """Create short synthesized plucks, with rising pentatonic notes on breaks."""
    if duration <= 0.0:
        raise ValueError("duration must be greater than zero")
    sample_count = max(1, int(np.ceil(duration * sample_rate)))
    output = np.zeros(sample_count, dtype=np.float64)
    sound_duration = 0.24
    sound_samples = int(sound_duration * sample_rate)
    times = np.arange(sound_samples, dtype=np.float64) / sample_rate
    pitch_drop = 0.045
    phase_curve = 2.0 * np.pi * pitch_drop * (1.0 - np.exp(-times / pitch_drop))
    envelope = np.exp(-times * 17.0)
    click_envelope = np.exp(-times * 125.0)
    rng = np.random.default_rng(2026)
    click_noise = rng.uniform(-1.0, 1.0, sound_samples) * click_envelope
    pentatonic = np.asarray((0, 2, 4, 7, 9), dtype=np.int32)
    events: list[tuple[float, float]] = []
    for event_time in bounce_times:
        events.append((event_time, 290.0))
    for index, event_time in enumerate(sorted(break_times)):
        octave, scale_index = divmod(index, len(pentatonic))
        frequency = min(
            4000.0,
            330.0 * 2.0 ** (octave + pentatonic[scale_index] / 12.0),
        )
        events.append((event_time, frequency))

    for event_time, frequency in sorted(events):
        start = int(round(event_time * sample_rate))
        if start >= sample_count or start + sound_samples <= 0:
            continue
        tone = np.sin(frequency * phase_curve) * envelope * 0.34
        tone += click_noise * 0.12
        source_start = max(0, -start)
        destination_start = max(0, start)
        count = min(sound_samples - source_start, sample_count - destination_start)
        output[destination_start : destination_start + count] += tone[
            source_start : source_start + count
        ]
    peak = float(np.max(np.abs(output)))
    if peak > 0.98:
        output *= 0.98 / peak
    pcm = (np.clip(output, -1.0, 1.0) * 32767).astype("<i2")
    import wave

    with wave.open(str(output_path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(sample_rate)
        file.writeframes(pcm.tobytes())


def mux_audio_video(
    video_path: str,
    audio_path: str | None,
    output_path: str,
    impact_audio_path: str | None = None,
) -> None:
    """Mux music and optional generated impact sounds into a video."""
    if not audio_path and not impact_audio_path:
        raise ValueError("At least one audio input is required for muxing")
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        video_path,
    ]
    audio_inputs: list[str] = []
    if audio_path:
        command.extend(["-stream_loop", "-1", "-i", audio_path])
        audio_inputs.append("1:a:0")
    if impact_audio_path:
        command.extend(["-i", impact_audio_path])
        audio_inputs.append(f"{len(audio_inputs) + 1}:a:0")
    if len(audio_inputs) == 1:
        command.extend(["-map", "0:v:0", "-map", audio_inputs[0]])
    else:
        filters = ";".join(
            f"[{stream}]volume={1.0 if index == 0 else 0.35}[a{index}]"
            for index, stream in enumerate(audio_inputs)
        )
        filters += ";" + "".join(f"[a{index}]" for index in range(len(audio_inputs)))
        filters += (
            f"amix=inputs={len(audio_inputs)}:duration=first:"
            "dropout_transition=0[aout]"
        )
        command.extend(
            [
                "-filter_complex",
                filters,
                "-map",
                "0:v:0",
                "-map",
                "[aout]",
            ]
        )
    command.extend(
        [
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            output_path,
        ]
    )
    subprocess.run(command, check=True)
