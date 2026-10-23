"""
Crab Rave Desktop Pet for Windows (WASAPI Loopback Output Audio)
================================================================================
A transparent, borderless, audio-reactive desktop pet inspired by the iconic
"Crab Rave" music video.

Requirements:
    pip install soundcard numpy

Why soundcard?
    Windows separates devices into Outputs (Headphones/Speakers) and Inputs (Mics).
    soundcard uses Windows WASAPI Loopback to directly capture whatever is playing
    through your active Headphones or Speakers without needing 'Stereo Mix' or mics.
================================================================================
"""

import math
import os
import random
import sys
import threading
import time
import tkinter as tk

# PyInstaller safety: Redirect stdout/stderr if running in windowless mode
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

def resource_path(relative_path):
    """Resolves path for single-file PyInstaller builds or local dev."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

# Audio Engine Imports
# 1. Primary: soundcard (WASAPI Loopback for real Headphones & Speakers)
# 2. Secondary: sounddevice (Fallback for inputs or Stereo Mix)
HAVE_SOUNDCARD = False
HAVE_SOUNDDEVICE = False

try:
    import numpy as np
    try:
        import soundcard as sc
        HAVE_SOUNDCARD = True
    except ImportError:
        pass

    try:
        import sounddevice as sd
        HAVE_SOUNDDEVICE = True
    except ImportError:
        pass
except ImportError:
    pass

if not HAVE_SOUNDCARD:
    print("\n[Crab Pet Notice] 'soundcard' is recommended to capture Headphones/Speakers.")
    print("Install it with:  pip install soundcard numpy\n")


# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================
CANVAS_WIDTH = 180           # Canvas width in pixels
CANVAS_HEIGHT = 160          # Canvas height in pixels
TRANS_COLOR = "#010101"      # Windows chroma-key transparency color

# Audio Detection Sensitivity
DEFAULT_THRESHOLD = 0.015    # RMS volume to trigger dancing
DEFAULT_PEAK = 0.065         # RMS volume to trigger frenzy rave mode
SILENCE_TIMEOUT = 3.0        # Seconds of silence before returning to crawl

# Animation Timers (in milliseconds)
CRAWL_TICK_MS = 140          # Crawl frame step speed
DANCE_TICK_MS = 120          # Normal dance frame step speed
FRENZY_TICK_MS = 65          # Rave frenzy dance speed (double tempo!)


# ==============================================================================
# 1. AUDIO MONITOR (WASAPI Loopback for Speakers / Headphones)
# ==============================================================================
class AudioMonitor:
    """
    Taps directly into Windows default or chosen Speaker/Headphone output
    using WASAPI Loopback so it reacts to what the user actually hears.
    """
    def __init__(self, threshold=DEFAULT_THRESHOLD, peak_threshold=DEFAULT_PEAK):
        self.threshold = threshold
        self.peak_threshold = peak_threshold
        self.smoothed_vol = 0.0
        self.is_loud = False
        self.is_peak = False
        self.last_loud_time = 0.0
        self.running = True
        self.worker_thread = None
        self.active_device_id = None
        self.active_device_name = "None"
        self.lock = threading.Lock()

        self._init_audio()

    def _init_audio(self):
        if HAVE_SOUNDCARD:
            try:
                def_spk = sc.default_speaker()
                self.active_device_id = str(def_spk.id)
                self.active_device_name = def_spk.name
                self._start_soundcard_worker(self.active_device_id)
                print(f"[Audio] Hooked into Output Device: {self.active_device_name}")
                return
            except Exception as e:
                print(f"[Audio] soundcard init failed: {e}")

        # Fallback to sounddevice if soundcard is unavailable
        if HAVE_SOUNDDEVICE:
            try:
                def_in = sd.default.device[0]
                dev_info = sd.query_devices(def_in)
                self.active_device_id = def_in
                self.active_device_name = dev_info["name"]
                self._start_sounddevice_worker(def_in)
                print(f"[Audio] Fallback to input device: {self.active_device_name}")
            except Exception as e:
                print(f"[Audio] sounddevice fallback failed: {e}")

    def get_output_devices(self):
        """Returns all real Windows Output (Speaker/Headphone) devices."""
        if HAVE_SOUNDCARD:
            try:
                def_spk = sc.default_speaker()
                devices = []
                for spk in sc.all_speakers():
                    is_def = (spk.id == def_spk.id)
                    prefix = "★ [Default] " if is_def else ""
                    devices.append((str(spk.id), f"{prefix}{spk.name}"))
                return devices
            except Exception:
                return []
        elif HAVE_SOUNDDEVICE:
            try:
                return [(i, d["name"]) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
            except Exception:
                return []
        return []

    def switch_device(self, new_device_id):
        """Switches the monitored audio output device."""
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)

        self.running = True
        self.active_device_id = new_device_id
        if HAVE_SOUNDCARD:
            self._start_soundcard_worker(new_device_id)
        elif HAVE_SOUNDDEVICE:
            self._start_sounddevice_worker(new_device_id)

    def _start_soundcard_worker(self, spk_id):
        self.worker_thread = threading.Thread(
            target=self._soundcard_loop,
            args=(spk_id,),
            daemon=True
        )
        self.worker_thread.start()

    def _soundcard_loop(self, spk_id):
        """Captures audio directly from speakers/headphones via WASAPI loopback."""
        try:
            mic = sc.get_microphone(id=spk_id, include_loopback=True)
            # 48000 Hz, 1024 sample block (~21ms per buffer, near zero latency)
            with mic.recorder(samplerate=48000, blocksize=1024) as rec:
                while self.running:
                    data = rec.record(numframes=1024)
                    rms = float(np.sqrt(np.mean(data ** 2)))
                    peak = float(np.max(np.abs(data)))
                    self._update_volume(rms, peak)
        except Exception as e:
            print(f"[Audio Worker] Loopback stream notice: {e}")

    def _start_sounddevice_worker(self, dev_id):
        def callback(indata, frames, time_info, status):
            if not self.running:
                return
            rms = float(np.sqrt(np.mean(indata ** 2)))
            peak = float(np.max(np.abs(indata)))
            self._update_volume(rms, peak)

        try:
            self.sd_stream = sd.InputStream(
                device=dev_id, channels=1, samplerate=44100,
                blocksize=1024, callback=callback
            )
            self.sd_stream.start()
        except Exception as e:
            print(f"[Audio] sounddevice stream error: {e}")

    def _update_volume(self, rms, peak):
        with self.lock:
            # Exponential smoothing for fluid threshold detection
            self.smoothed_vol = self.smoothed_vol * 0.65 + rms * 0.35
            now = time.time()

            if self.smoothed_vol >= self.threshold or peak >= self.peak_threshold:
                self.last_loud_time = now
                self.is_loud = True
                self.is_peak = (peak >= self.peak_threshold or self.smoothed_vol >= self.peak_threshold)
            else:
                if now - self.last_loud_time >= SILENCE_TIMEOUT:
                    self.is_loud = False
                    self.is_peak = False

    def get_status(self):
        with self.lock:
            return self.is_loud, self.is_peak, self.smoothed_vol

    def stop(self):
        self.running = False
        if hasattr(self, "sd_stream") and self.sd_stream:
            try:
                self.sd_stream.stop()
                self.sd_stream.close()
            except Exception:
                pass


# ==============================================================================
# 2. PROCEDURAL PIXEL-ART CRAB RENDERER (Crab Rave Visuals)
# ==============================================================================
class ProceduralCrabRenderer:
    """Renders pixel-art Crab Rave crab with smooth animations & rave accessories."""
    def __init__(self, canvas):
        self.canvas = canvas
        self.particles = []

    def draw(self, state, frame_idx, crawl_dir=1, is_frenzy=False):
        self.canvas.delete("all")
        cx = CANVAS_WIDTH // 2
        cy = CANVAS_HEIGHT // 2 + 5

        # Vertical / horizontal bobbing offsets depending on state
        if state == "dance":
            step = frame_idx % 6
            # 0: tilt left, 1: crouch, 2: tilt right, 3: crouch, 4: sky jump, 5: snap
            offsets = [(-4, 0), (0, 4), (4, 0), (0, 4), (0, -7), (0, 2)]
            ox, oy = offsets[step]
            cx += ox
            cy += oy
        elif state == "crawl":
            cy += (1 if frame_idx % 2 == 1 else -1)
        elif state == "dragged":
            cy -= 4

        # 1. Eyestalks & Eyes (Behind upper shell)
        eye_y_boost = -6 if (state == "dance" and frame_idx % 6 == 4) else 0
        self._draw_eyes(cx, cy + eye_y_boost, state, frame_idx, crawl_dir)

        # 2. Back and Middle Legs (Behind shell)
        self._draw_legs(cx, cy, state, frame_idx, is_front=False)

        # 3. Claws and Arms (The iconic Crab Rave chelae)
        self._draw_claws(cx, cy, state, frame_idx)

        # 4. Main Carapace (Shell)
        self._draw_shell(cx, cy)

        # 5. Front Walking Legs
        self._draw_legs(cx, cy, state, frame_idx, is_front=True)

        # 6. Frenzy Rave Extras (8-bit sunglasses & floating rave particles)
        if is_frenzy:
            self._draw_sunglasses(cx, cy + eye_y_boost)
            self._draw_particles(cx, cy)

    def _draw_shell(self, cx, cy):
        shell_blocks = [
            (-22, -14, 44, 4,  "#FF7A30", "#2B0A00"),  # Top highlight curve
            (-28, -10, 56, 6,  "#FF5722", "#2B0A00"),
            (-32,  -4, 64, 8,  "#FF4500", "#2B0A00"),  # Main wide carapace
            (-32,   4, 64, 8,  "#FF4500", "#2B0A00"),
            (-28,  12, 56, 6,  "#D84315", "#2B0A00"),  # Underside shadow
            (-20,  18, 40, 4,  "#BF360C", "#2B0A00"),
        ]
        for ox, oy, w, h, fill, out in shell_blocks:
            self.canvas.create_rectangle(cx + ox, cy + oy, cx + ox + w, cy + oy + h,
                                         fill=fill, outline=out, width=1.5)
        self.canvas.create_rectangle(cx - 12, cy - 2, cx - 7, cy + 2, fill="#FFAB91", outline="")
        self.canvas.create_rectangle(cx + 7, cy - 2, cx + 12, cy + 2, fill="#FFAB91", outline="")

    def _draw_eyes(self, cx, cy, state, frame_idx, crawl_dir):
        for side in (-1, 1):
            sx = cx + side * 15
            self.canvas.create_rectangle(sx - 3, cy - 22, sx + 3, cy - 12,
                                         fill="#E64A19", outline="#2B0A00", width=1.5)
            self.canvas.create_rectangle(sx - 7, cy - 35, sx + 7, cy - 21,
                                         fill="#FFFFFF", outline="#2B0A00", width=1.5)
            px_off = 0
            py_off = 0
            if state == "crawl":
                px_off = 2 * crawl_dir
            elif state == "dance":
                step = frame_idx % 6
                if step == 0:   px_off = -2
                elif step == 2: px_off = 2
                elif step == 4: py_off = -3
            elif state == "dragged":
                py_off = -2

            self.canvas.create_rectangle(sx - 3 + px_off, cy - 31 + py_off,
                                         sx + 2 + px_off, cy - 24 + py_off, fill="#111111", outline="")
            self.canvas.create_rectangle(sx - 3 + px_off, cy - 31 + py_off,
                                         sx - 1 + px_off, cy - 29 + py_off, fill="#FFFFFF", outline="")

    def _draw_sunglasses(self, cx, cy):
        self.canvas.create_rectangle(cx - 26, cy - 33, cx + 26, cy - 23,
                                     fill="#111111", outline="#00E5FF", width=1.5)
        self.canvas.create_line(cx - 24, cy - 31, cx - 6, cy - 31, fill="#FF007F", width=2)
        self.canvas.create_line(cx + 6, cy - 31, cx + 24, cy - 31, fill="#00E5FF", width=2)

    def _draw_legs(self, cx, cy, state, frame_idx, is_front=False):
        legs = [(-1, 0, -25, 0), (1, 0, 25, 0)] if is_front else [
            (-1, 1, -28, 8), (1, 1, 28, 8),
            (-1, 2, -24, 16), (1, 2, 24, 16)
        ]

        for side, leg_idx, bx, by in legs:
            base_x = cx + bx
            base_y = cy + by
            lift = 0
            shift = 0

            if state == "crawl":
                if (frame_idx + leg_idx) % 2 == 1:
                    lift = -6
                    shift = 4 * side
            elif state == "dance":
                lift = -4 if (frame_idx % 2 == leg_idx % 2) else 2
                shift = (3 if frame_idx % 4 < 2 else -3) * side
            elif state == "dragged":
                lift = -10 if (frame_idx % 2 == leg_idx % 2) else 5
                shift = 6 * side

            knee_x = base_x + side * (15 + shift)
            knee_y = base_y - 6 + lift
            foot_x = knee_x + side * 11
            foot_y = base_y + 17 + lift // 2

            self.canvas.create_line(base_x, base_y, knee_x, knee_y, fill="#FF5722", width=5, capstyle=tk.ROUND)
            self.canvas.create_line(knee_x, knee_y, foot_x, foot_y, fill="#D84315", width=4, capstyle=tk.ROUND)

    def _draw_claws(self, cx, cy, state, frame_idx):
        l_snap, r_snap = False, False
        l_x, l_y = cx - 48, cy - 18
        r_x, r_y = cx + 48, cy - 18

        if state == "dance":
            step = frame_idx % 6
            if step == 0:
                l_x, l_y = cx - 40, cy - 50
                r_x, r_y = cx + 44, cy + 4
                l_snap = True
            elif step == 1:
                l_x, l_y = cx - 46, cy - 22
                r_x, r_y = cx + 46, cy - 12
            elif step == 2:
                l_x, l_y = cx - 44, cy + 4
                r_x, r_y = cx + 40, cy - 50
                r_snap = True
            elif step == 3:
                l_x, l_y = cx - 46, cy - 12
                r_x, r_y = cx + 46, cy - 22
            elif step == 4:
                # DOUBLE CLAW RAVE PUMP TO THE SKY!
                l_x, l_y = cx - 40, cy - 56
                r_x, r_y = cx + 40, cy - 56
                l_snap, r_snap = True, True
            elif step == 5:
                # Double snap down
                l_x, l_y = cx - 48, cy - 24
                r_x, r_y = cx + 48, cy - 24
                l_snap, r_snap = True, True
        elif state == "dragged":
            flail = 10 if frame_idx % 2 == 0 else -10
            l_x, l_y = cx - 50, cy - 36 + flail
            r_x, r_y = cx + 50, cy - 36 - flail
            l_snap, r_snap = True, True

        self._draw_single_claw(cx - 22, cy - 8, l_x, l_y, is_left=True, is_open=l_snap)
        self._draw_single_claw(cx + 22, cy - 8, r_x, r_y, is_left=False, is_open=r_snap)

    def _draw_single_claw(self, arm_bx, arm_by, wx, wy, is_left, is_open):
        elbow_x = (arm_bx + wx) // 2 + (-8 if is_left else 8)
        elbow_y = min(arm_by, wy) + 4
        self.canvas.create_line(arm_bx, arm_by, elbow_x, elbow_y, fill="#FF5722", width=6, capstyle=tk.ROUND)
        self.canvas.create_line(elbow_x, elbow_y, wx, wy, fill="#FF5722", width=6, capstyle=tk.ROUND)
        self.canvas.create_oval(wx - 9, wy - 9, wx + 9, wy + 9, fill="#FF3D00", outline="#2B0A00", width=1.5)

        sign = -1 if is_left else 1
        ang = 0.58 if is_open else 0.24
        t_x = wx + sign * int(17 * math.cos(ang))
        t_y = wy - int(17 * math.sin(ang))
        self.canvas.create_polygon(wx, wy - 4, t_x, t_y, wx + sign * 6, wy - 2,
                                    fill="#FF7A30", outline="#2B0A00", width=1.5)
        b_x = wx + sign * int(15 * math.cos(-ang))
        b_y = wy - int(15 * math.sin(-ang))
        self.canvas.create_polygon(wx, wy + 4, b_x, b_y, wx + sign * 6, wy + 2,
                                    fill="#FF7A30", outline="#2B0A00", width=1.5)

    def _draw_particles(self, cx, cy):
        if len(self.particles) < 7:
            symbols = ["♪", "♫", "★", "✦", "♥"]
            colors = ["#00E5FF", "#FF007F", "#FFEB3B", "#76FF03"]
            self.particles.append({
                "x": cx + random.randint(-45, 45),
                "y": cy - random.randint(35, 55),
                "char": random.choice(symbols),
                "color": random.choice(colors),
                "life": 12
            })
        for p in self.particles[:]:
            self.canvas.create_text(p["x"], p["y"], text=p["char"], fill=p["color"],
                                    font=("Segoe UI Symbol", 11, "bold"))
            p["y"] -= 3
            p["life"] -= 1
            if p["life"] <= 0:
                self.particles.remove(p)


# ==============================================================================
# 3. CUSTOM SPRITE SHEET / IMAGE LOADER (OPTIONAL EXTENSION)
# ==============================================================================
# Set USE_CUSTOM_SPRITES = True to load external .png or .gif frames instead of
# drawing with the procedural canvas shapes above.
USE_CUSTOM_SPRITES = False

class CustomSpriteRenderer:
    """
    Drop your own sprite files into a 'sprites/' folder next to this script:
        sprites/crawl_0.png, crawl_1.png, crawl_2.png, crawl_3.png
        sprites/dance_0.png, dance_1.png, dance_2.png, dance_3.png, dance_4.png, dance_5.png
        sprites/dragged.png
    """
    def __init__(self, canvas):
        self.canvas = canvas
        self.sprites = {}
        self._load_all_sprites()

    def _load_all_sprites(self):
        sprite_dir = resource_path("sprites")
        if not os.path.isdir(sprite_dir):
            return

        def load_frame(key, filename):
            path = os.path.join(sprite_dir, filename)
            if os.path.exists(path):
                try:
                    self.sprites[key] = tk.PhotoImage(file=path)
                except Exception as e:
                    print(f"[Sprites] Error loading {filename}: {e}")

        for i in range(4):
            load_frame(f"crawl_{i}", f"crawl_{i}.png")
        for i in range(6):
            load_frame(f"dance_{i}", f"dance_{i}.png")
        load_frame("dragged_0", "dragged.png")

    def draw(self, state, frame_idx, crawl_dir=1, is_frenzy=False):
        self.canvas.delete("all")
        key = f"{state}_{frame_idx}"
        img = self.sprites.get(key) or self.sprites.get(f"{state}_0")
        if img:
            self.canvas.create_image(CANVAS_WIDTH // 2, CANVAS_HEIGHT // 2, image=img)
        else:
            self.canvas.create_text(CANVAS_WIDTH // 2, CANVAS_HEIGHT // 2,
                                    text="[Sprite Missing]", fill="#FF5722")


# ==============================================================================
# 4. MAIN APPLICATION & WINDOW CONTROLLER
# ==============================================================================
class CrabPet:
    def __init__(self):
        self.root = tk.Tk()

        # Window styling: borderless, topmost, transparent
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-transparentcolor", TRANS_COLOR)
        self.root.config(bg=TRANS_COLOR)

        self.canvas = tk.Canvas(
            self.root, width=CANVAS_WIDTH, height=CANVAS_HEIGHT,
            bg=TRANS_COLOR, highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)

        # Place at screen bottom above taskbar
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.pos_x = screen_w // 2 - CANVAS_WIDTH // 2
        self.pos_y = screen_h - CANVAS_HEIGHT - 45
        self.root.geometry(f"{CANVAS_WIDTH}x{CANVAS_HEIGHT}+{self.pos_x}+{self.pos_y}")

        # State Variables
        self.state = "crawl"
        self.frame_idx = 0
        self.crawl_direction = 1
        self.crawl_speed = 3
        self.is_dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.force_dance = False
        self.audio_reactive_enabled = True

        self.next_action_time = time.time() + random.uniform(3.0, 6.0)
        self.is_idling = False

        if USE_CUSTOM_SPRITES:
            self.renderer = CustomSpriteRenderer(self.canvas)
        else:
            self.renderer = ProceduralCrabRenderer(self.canvas)

        self.audio = AudioMonitor()

        # Bind Mouse Interactions
        self.canvas.bind("<Button-1>", self._on_left_click)
        self.canvas.bind("<B1-Motion>", self._on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_left_release)
        self.canvas.bind("<Button-3>", self._show_context_menu)

        self._build_context_menu()

        self.is_running = True
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)
        self._animation_loop()

    def _build_context_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0)

        self.force_dance_var = tk.BooleanVar(value=False)
        self.menu.add_checkbutton(
            label="Force Dance Mode",
            variable=self.force_dance_var,
            command=self._toggle_force_dance
        )

        self.audio_reactive_var = tk.BooleanVar(value=True)
        self.menu.add_checkbutton(
            label="Audio Reactive Mode",
            variable=self.audio_reactive_var,
            command=self._toggle_audio_reactive
        )

        # Sensitivity Submenu
        self.sensitivity_var = tk.StringVar(value="normal")
        sens_menu = tk.Menu(self.menu, tearoff=0)
        sens_menu.add_radiobutton(label="High Sensitivity (Quiet music)", value="high",
                                  variable=self.sensitivity_var, command=self._update_sensitivity)
        sens_menu.add_radiobutton(label="Normal Sensitivity (Standard)", value="normal",
                                  variable=self.sensitivity_var, command=self._update_sensitivity)
        sens_menu.add_radiobutton(label="Low Sensitivity (Loud music / Drops)", value="low",
                                  variable=self.sensitivity_var, command=self._update_sensitivity)
        self.menu.add_cascade(label="Audio Sensitivity", menu=sens_menu)

        # Output Devices Submenu (Headphones / Speakers)
        self.device_var = tk.StringVar(value=str(self.audio.active_device_id))
        dev_menu = tk.Menu(self.menu, tearoff=0)
        devices = self.audio.get_output_devices()
        if devices:
            for dev_id, dev_name in devices:
                short_name = dev_name[:34] + ("..." if len(dev_name) > 34 else "")
                dev_menu.add_radiobutton(
                    label=short_name,
                    value=str(dev_id),
                    variable=self.device_var,
                    command=lambda d_id=dev_id: self.audio.switch_device(d_id)
                )
        else:
            dev_menu.add_command(label="(No Output Devices Found)", state="disabled")
        self.menu.add_cascade(label="🎧 Audio Output (Headphones/Speakers)", menu=dev_menu)

        self.menu.add_separator()
        self.menu.add_command(label="Reset Position to Bottom", command=self._reset_position)
        self.menu.add_command(label="Exit", command=self.exit_app)

    def _show_context_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _toggle_force_dance(self):
        self.force_dance = self.force_dance_var.get()

    def _toggle_audio_reactive(self):
        self.audio_reactive_enabled = self.audio_reactive_var.get()

    def _update_sensitivity(self):
        mode = self.sensitivity_var.get()
        if mode == "high":
            self.audio.threshold = 0.008
            self.audio.peak_threshold = 0.035
        elif mode == "low":
            self.audio.threshold = 0.035
            self.audio.peak_threshold = 0.100
        else:  # normal
            self.audio.threshold = DEFAULT_THRESHOLD
            self.audio.peak_threshold = DEFAULT_PEAK

    def _reset_position(self):
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.pos_x = screen_w // 2 - CANVAS_WIDTH // 2
        self.pos_y = screen_h - CANVAS_HEIGHT - 45
        self.root.geometry(f"+{self.pos_x}+{self.pos_y}")

    def _on_left_click(self, event):
        self.is_dragging = True
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def _on_drag_motion(self, event):
        if self.is_dragging:
            self.pos_x = self.root.winfo_x() + (event.x - self.drag_start_x)
            self.pos_y = self.root.winfo_y() + (event.y - self.drag_start_y)
            self.root.geometry(f"+{self.pos_x}+{self.pos_y}")

    def _on_left_release(self, event):
        self.is_dragging = False

    def _animation_loop(self):
        if not self.is_running:
            return

        now = time.time()
        is_loud, is_peak, vol = self.audio.get_status()
        is_frenzy = False
        tick_delay = CRAWL_TICK_MS

        if self.is_dragging:
            self.state = "dragged"
            tick_delay = 100
        elif self.force_dance or (self.audio_reactive_enabled and is_loud):
            self.state = "dance"
            is_frenzy = is_peak
            tick_delay = FRENZY_TICK_MS if is_frenzy else DANCE_TICK_MS
        else:
            self.state = "crawl"
            tick_delay = CRAWL_TICK_MS

        if self.state == "crawl" and not self.is_dragging:
            if now >= self.next_action_time:
                self.next_action_time = now + random.uniform(3.5, 7.0)
                action = random.choice(["crawl_right", "crawl_left", "idle"])
                if action == "idle":
                    self.is_idling = True
                else:
                    self.is_idling = False
                    self.crawl_direction = 1 if action == "crawl_right" else -1

            if not self.is_idling:
                screen_w = self.root.winfo_screenwidth()
                self.pos_x += self.crawl_direction * self.crawl_speed
                if self.pos_x > screen_w - CANVAS_WIDTH - 10:
                    self.pos_x = screen_w - CANVAS_WIDTH - 10
                    self.crawl_direction = -1
                elif self.pos_x < 10:
                    self.pos_x = 10
                    self.crawl_direction = 1
                self.root.geometry(f"+{self.pos_x}+{self.pos_y}")

        num_frames = 6 if self.state == "dance" else 4
        self.frame_idx = (self.frame_idx + 1) % num_frames

        self.renderer.draw(
            state=self.state,
            frame_idx=self.frame_idx,
            crawl_dir=self.crawl_direction,
            is_frenzy=is_frenzy
        )

        self.root.after(tick_delay, self._animation_loop)

    def exit_app(self):
        self.is_running = False
        self.audio.stop()
        try:
            self.root.destroy()
        except Exception:
            pass
        sys.exit(0)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    pet = CrabPet()
    pet.run()
