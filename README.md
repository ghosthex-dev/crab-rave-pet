# 🦀 Crab Rave Desktop Pet for Windows

An interactive, borderless, transparent, audio-reactive Windows desktop pet inspired by Noisestorm's iconic **"Crab Rave"** music video.

![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-blue)
![Python](https://img.shields.io/badge/Python-3.9+-yellow)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 🌟 Features

- **Borderless & Transparent Window:** Sits seamlessly on top of your desktop and taskbar with no window borders or background color.
- **Procedural 16-Bit Pixel Art:** Built-in retro pixel-art crab with zero image dependencies required.
- **Audio-Reactive (WASAPI Loopback):** Directly listens to what you hear through your **Headphones, Speakers, or Monitors** (Spotify, YouTube, games).
  - **Crawling Mode:** Wanders sideways along the bottom of your screen with an animated 4-frame tripod gait.
  - **Dancing Mode:** When music starts playing, it stops crawling and grooves to the beat with synchronized claw pumping.
  - **Frenzy Rave Mode:** On volume peaks and beat drops, the crab accelerates to double tempo, dons **8-bit meme sunglasses**, and emits neon music note particles (`♪`, `♫`, `★`, `✦`).
  - **Silence Return:** Automatically returns to crawling after 3 seconds of silence.
- **Mouse Controls:**
  - **Left-Click & Drag:** Move the crab anywhere on screen (triggers a flailing animation).
  - **Right-Click Menu:**
    - Toggle Force Dance Mode
    - Toggle Audio Reactive Mode
    - Adjust Audio Sensitivity (High, Normal, Low)
    - Select Output Device (Headphones, Speakers, etc.)
    - Reset Position to Screen Bottom
    - Exit
- **Custom Sprite Support:** Option to swap out canvas shapes for custom `.png` / `.gif` sprite sheets.

---

## 🚀 Download & Run (Standalone Portable EXE)

No Python installation required! 

1. Head over to the **[Releases](https://github.com/ghosthex-dev/crab-rave-pet/releases)** page.
2. Download **`CrabRavePet.exe`**.
3. Double-click and enjoy!

---

## 🛠️ Running from Source

If you want to run or modify the Python script directly:

### 1. Requirements
```bash
pip install soundcard numpy
```

### 2. Run
```bash
python crab_rave_pet.py
```

### 3. Build Portable EXE Yourself
```bash
pip install pyinstaller pillow soundcard numpy
python -m PyInstaller --noconsole --onefile --name "CrabRavePet" --icon "crab.ico" --collect-all soundcard crab_rave_pet.py
```

---

## 📜 License
MIT License
