# SonicVortex — Neon Music Ball Escape Video Studio

SonicVortex is a desktop studio for creating vertical, music-reactive neon videos. A ball ricochets through rotating rings, finds their gaps, and breaks through them while the visuals react to the soundtrack.

## Features

- **GPU rendering at 60 FPS** with ModernGL, OpenGL 3.3+, off-screen rendering, and a multi-pass neon Bloom effect.
- **Multiband audio analysis** for sub-bass, mid, and high frequencies, with smoothed per-frame energy and beat detection.
- **A 48-band spectrum visualizer** synchronized to the audio.
- **Four background modes:** solid color, transparent video, video background, and video visible through the ring/ball mask.
- **Transparent MOV export** using RGBA frames for compositing in video editors.
- **Procedural ASMR impact sounds** for bounces and ring breaks, mixed with the soundtrack when enabled.
- **A dark creator-studio interface** for audio, duration, ring count, themes, physics, compositing, watermark, and render progress.
- **Customizable neon themes**, ring dynamics, camera punch, particles, shockwaves, and a glowing comet trail.

## Installation & usage

### Requirements

- Python 3.10 or newer
- Windows, macOS, or Linux with an OpenGL 3.3-compatible graphics driver
- FFmpeg is provided through `imageio-ffmpeg`; no separate FFmpeg installation is normally required

### Setup

```bash
git clone https://github.com/loanelly/SonicVortex.git
cd SonicVortex
python -m venv .venv
```

Activate the virtual environment:

**Windows PowerShell**

```powershell
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
source .venv/bin/activate
```

Install dependencies and launch the studio:

```bash
pip install -r requirements.txt
python main.py
```

Choose a soundtrack in the studio, configure the visual style and export options, then start the render. If no audio file is selected, SonicVortex generates a test beat. The default export is `output.mp4`; transparent mode exports an alpha-channel `.mov`.

## Project structure

| File | Role |
| --- | --- |
| `main.py` | Runs the simulation, ring and ball physics, rendering loop, FFmpeg encoding, and audio/video export. |
| `gui.py` | Provides the Tkinter creator studio and collects render settings. |
| `renderer.py` | Implements ModernGL shaders, off-screen rendering, rings, particles, equalizer, trails, backgrounds, and Bloom. |
| `audio.py` | Loads and analyzes audio, detects beats, synthesizes optional impact sounds, and muxes the final video. |
| `config.py` | Holds video dimensions, simulation defaults, audio settings, themes, and background modes. |
| `requirements.txt` | Lists the Python dependencies. |

## Configuration

The default video is **1080 × 1920 at 60 FPS**. Studio controls can override ring count, visible rings, physics presets, audio sensitivity, colors, watermark, and duration. For additional defaults, edit `config.py`.

## License

No license has been selected for this project yet.
