import math
import os
import random
import time

import pygame
from pygame.locals import K_a, KEYDOWN, MOUSEBUTTONDOWN, MOUSEMOTION, QUIT

SCREEN_W = 240
SCREEN_H = 320
TOP_H = SCREEN_H
BOT_H = SCREEN_H - TOP_H

FPS = 30
SHOW_MODE_LABEL = True
MODE_LABEL_FONT_SIZE = 10
LIGHT_SLEEP_THRESHOLD = 32.0
LIGHT_WAKE_THRESHOLD = 40.0
LIGHT_SLEEP_HOLD_S = 2.2
DANCE_TRIGGER_MIC = 13.0
DANCE_TRIGGER_SPIKE = 1.4
DANCE_ACTIVITY_TRIGGER = 0.95
DANCE_ON_HOLD_S = 1.1
DANCE_CONVO_BLOCK_MIC = 18.0
DANCE_FRAME_MIN_MS = 120
DANCE_FRAME_MAX_MS = 150
DANCE_FILES = ("dance1.png", "dance2.png")
DANCE_SPRITE_SCALE = 1.05
DANCE_OFF_HYST = 0.8
DANCE_HOLD_S = 0.35
DANCE_ACTIVITY_ALPHA = 0.20
DEEP_SLEEP_AFTER_S = 4.0
NIGHT_BACKGROUND_FILE = "background_night.png"
SLEEPING_SPRITE_FILE = "nemma_sleeping.png"
SLEEPING_SPRITE_SCALE = 1.05
FOOD_FILE = "food.png"
FOOD_ICON_SCALE = 0.30
FOOD_SPAWN_MARGIN = 10
EAT_FILES = ("eat1.png", "eat2.png")
EAT_SPRITE_SCALE = 1.05
EAT_FRAME_MIN_MS = 110
EAT_FRAME_MAX_MS = 150
EAT_DURATION_S = 0.75
# Keep false for production so missing sensors fail "quiet" instead of generating fake values.
SIMULATE_IF_MISSING = False

STATE_IDLE = "IDLE"
STATE_CURIOUS = "CURIOUS"
STATE_STARTLED = "STARTLED"
STATE_SLEEPY = "SLEEPY"
STATE_HAPPY = "HAPPY"

STATE_MIN_DWELL = {
    STATE_IDLE: 1.0,
    STATE_CURIOUS: 1.0,
    STATE_STARTLED: 0.55,
    STATE_SLEEPY: 2.0,
    STATE_HAPPY: 1.3,
}

MOOD_PROFILE = {
    "clap": 4.0,
    "loud": 9.0,
    "shake": 0.55,
    "still_acc": 0.10,
    "still_mic": 18.0,
    "dark_in": 16.0,
    "dark_out": 26.0,
}

SPRITE_FILES = {
    STATE_IDLE: "nemma_idle.png",
    STATE_CURIOUS: "nemma_curious.png",
    STATE_HAPPY: "nemma_happy.png",
    STATE_STARTLED: "nemma_startled.png",
    STATE_SLEEPY: "nemma_sleepy.png",
}
BACKGROUND_FILE = "background.png"
ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def ema(prev, new, alpha):
    return prev + alpha * (new - prev)


def asset_path(name):
    p = os.path.join(ASSET_DIR, name)
    if os.path.exists(p):
        return p
    return name


class IO:
    def __init__(self):
        self.accel = None
        self.mic = None
        self.light = None
        self.temp = None
        self.audio = None
        self.buzzer = None
        self.button_a = None
        self.button_b = None
        self._stub_t = time.monotonic()
        self.last_audio_method = "none"
        self.cap_buttons = False
        self.cap_buzzer = False
        self.cap_mic = False
        self.cap_light = False
        self.cap_accel = False
        self.mic_source = "none"
        self._tone_active = False
        self._tone_end_t = 0.0

        self._init_backend()

    def _resolve_device(self, module, candidates):
        for name in candidates:
            dev = getattr(module, name, None)
            if dev is None:
                continue
            if callable(dev):
                try:
                    return dev()
                except Exception:
                    try:
                        return dev
                    except Exception:
                        continue
            return dev
        return None

    def _init_backend(self):
        try:
            from pinpong.board import Board  # type: ignore

            try:
                Board("UNIHIKER").begin()
            except Exception:
                Board().begin()
        except Exception:
            pass

        try:
            import pinpong.extension.unihiker as uni_ext  # type: ignore

            self.accel = self._resolve_device(uni_ext, ("accelerometer", "Accelerometer", "ACCELEROMETER", "accel"))
            self.mic = self._resolve_device(
                uni_ext,
                ("microphone", "Microphone", "MICROPHONE", "mic", "MIC", "sound", "sound_sensor", "noise"),
            )
            self.light = self._resolve_device(uni_ext, ("light", "Light", "LIGHT", "ambient_light", "light_sensor"))
            self.temp = self._resolve_device(uni_ext, ("temperature", "Temperature", "TEMP"))
            self.buzzer = self._resolve_device(uni_ext, ("buzzer", "Buzzer", "BUZZER"))
            self.button_a = self._resolve_device(uni_ext, ("button_a", "ButtonA", "BUTTON_A", "btn_a"))
            self.button_b = self._resolve_device(uni_ext, ("button_b", "ButtonB", "BUTTON_B", "btn_b"))

            self.cap_accel = self.accel is not None
            self.cap_mic = self.mic is not None
            self.cap_light = self.light is not None
            self.cap_buzzer = self.buzzer is not None
            self.cap_buttons = (self.button_a is not None) or (self.button_b is not None)
            if self.cap_mic:
                self.mic_source = "ext"
        except Exception:
            pass

        # Some firmware exposes microphone access through unihiker.Audio instead of pinpong extension.
        if self.mic is None:
            try:
                from unihiker import Audio as AudioClass  # type: ignore
            except Exception:
                try:
                    from unihiker.Audio import Audio as AudioClass  # type: ignore
                except Exception:
                    AudioClass = None
            if AudioClass is not None:
                try:
                    self.audio = AudioClass()
                except Exception:
                    self.audio = None
            if self.audio is not None:
                self.cap_mic = True
                self.mic_source = "audio"

    def _call(self, obj, names, default=0.0):
        if obj is None:
            return default
        for n in names:
            fn = getattr(obj, n, None)
            if callable(fn):
                try:
                    return fn()
                except Exception:
                    continue
        return default

    def read_btn(self, btn):
        if btn is None:
            return False
        if callable(btn):
            try:
                return bool(btn())
            except Exception:
                pass
        for n in ("is_pressed", "pressed", "value", "read", "status", "get_key", "key"):
            a = getattr(btn, n, None)
            if callable(a):
                try:
                    v = a()
                    if isinstance(v, str):
                        return v.strip().lower() in ("1", "true", "pressed", "down", "a", "b")
                    return bool(v)
                except Exception:
                    continue
            if isinstance(a, (bool, int)):
                return bool(a)
        return False

    def read_accel(self):
        if self.accel is None:
            if not SIMULATE_IF_MISSING:
                return (0.0, 0.0, 1.0)
            t = time.monotonic() - self._stub_t
            return (0.02 * math.sin(t), 0.02 * math.cos(t), 1.0)
        return (
            float(self._call(self.accel, ("get_x", "x", "read_x"), 0.0)),
            float(self._call(self.accel, ("get_y", "y", "read_y"), 0.0)),
            float(self._call(self.accel, ("get_z", "z", "read_z"), 1.0)),
        )

    def read_mic(self):
        if self.mic is None:
            if self.audio is not None:
                return float(
                    self._call(
                        self.audio,
                        (
                            "read",
                            "sound_level",
                            "value",
                            "get_value",
                            "get_loudness",
                            "loudness",
                            "volume",
                            "get_volume",
                            "amplitude",
                            "get_amplitude",
                            "db",
                            "get_db",
                        ),
                        0.0,
                    )
                )
            if not SIMULATE_IF_MISSING:
                return 0.0
            t = time.monotonic() - self._stub_t
            return 12.0 + (0.5 + 0.5 * math.sin(t * 3.0)) * 2.0
        return float(
            self._call(
                self.mic,
                ("read", "sound_level", "value", "get_value", "get_loudness", "loudness", "volume", "get_volume"),
                0.0,
            )
        )

    def read_light(self):
        if self.light is None:
            if not SIMULATE_IF_MISSING:
                return 100.0
            return 24.0
        return float(self._call(self.light, ("read", "get_value", "value", "lightness"), 100.0))

    def tone(self, f, d):
        if self.buzzer is None:
            self.last_audio_method = "no_buzzer"
            return

        pitch_fn = getattr(self.buzzer, "pitch", None)
        if callable(pitch_fn):
            try:
                pitch_fn(int(f))
                self._tone_active = True
                self._tone_end_t = time.monotonic() + max(0.01, float(d))
                self.last_audio_method = "buzzer.pitch(f)"
                return
            except Exception:
                pass

        for n in ("play", "tone", "freq"):
            fn = getattr(self.buzzer, n, None)
            if callable(fn):
                try:
                    fn(int(f), float(d))
                    self.last_audio_method = "buzzer.{}(f,d)".format(n)
                    return
                except Exception:
                    continue

        self.last_audio_method = "audio_failed"

    def audio_tick(self):
        # Non-blocking tone stop for pitch-based APIs.
        if (not self._tone_active) or (self.buzzer is None):
            return
        if time.monotonic() < self._tone_end_t:
            return
        for stop_name in ("stop", "off", "mute"):
            stop_fn = getattr(self.buzzer, stop_name, None)
            if callable(stop_fn):
                try:
                    stop_fn()
                except Exception:
                    pass
        self._tone_active = False


class SoundScheduler:
    def __init__(self, io):
        self.io = io
        self.queue = []
        self.last_t = -99.0
        self.min_gap = 0.03

    def schedule(self, pattern):
        # pattern: [(offset_s, freq, dur), ...]
        now = time.monotonic()
        for off, f, d in pattern:
            self.queue.append((now + float(off), int(f), float(d)))
        self.queue.sort(key=lambda x: x[0])

    def update(self):
        now = time.monotonic()
        if not self.queue:
            return
        if self.queue[0][0] > now:
            return
        if (now - self.last_t) < self.min_gap:
            return
        _, f, d = self.queue.pop(0)
        self.io.tone(f, d)
        self.last_t = now

    def cute(self, kind):
        patterns = {
            "tap": [(0.00, 1450, 0.02), (0.03, 1720, 0.02)],
            "pet": [(0.00, 1200, 0.02), (0.03, 1380, 0.02), (0.06, 1560, 0.02)],
            "feed": [(0.00, 980, 0.02), (0.03, 1240, 0.02), (0.06, 1560, 0.02), (0.09, 1380, 0.02)],
            "speak": [(0.00, 1320, 0.02), (0.03, 1620, 0.02), (0.06, 1420, 0.02)],
            "startle": [(0.00, 560, 0.03), (0.04, 420, 0.03), (0.08, 640, 0.02)],
            "curious": [(0.00, 880, 0.02), (0.03, 1040, 0.02), (0.06, 1180, 0.02)],
            "sleepy": [(0.00, 520, 0.03), (0.05, 470, 0.03)],
        }
        self.schedule(patterns.get(kind, patterns["tap"]))


class NemmaApp:
    def __init__(self):
        self.io = IO()
        self.sounds = SoundScheduler(self.io)

        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Nemma")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Consolas", 14)
        self.mode_font = pygame.font.SysFont("Consolas", MODE_LABEL_FONT_SIZE)

        self.state = STATE_IDLE
        self.state_t = time.monotonic()
        self.profile = MOOD_PROFILE

        self.x = SCREEN_W * 0.5
        self.y = TOP_H * 0.62
        self.tx = self.x
        self.ty = self.y

        self.feed_flash_until = 0.0
        self.last_nemma_tap_t = -99.0
        self.is_asleep = False
        self.sleepy_elapsed = 0.0
        self.wake_requested = False

        self.prev_t = time.monotonic()
        ax, ay, az = self.io.read_accel()
        self.prev_mag = math.sqrt(ax * ax + ay * ay + az * az)
        self.accel_delta = 0.0
        self.mic_ema = self.io.read_mic()
        self.prev_mic = self.mic_ema
        self.mic_activity = 0.0
        self.light_ema = self.io.read_light()
        self.light_now = self.light_ema
        self.dark_t = 0.0
        self.bright_t = 0.0
        self.still_t = 0.0
        self.last_clap_t = -99.0
        self.last_shake_t = -99.0

        self.clap_event = False
        self.shake_event = False
        self.loud_event = False

        self.btn_feed_latch = False
        self.raw_a = False
        self.prev_raw_a = False

        self.c_tap = 0
        self.c_pet = 0
        self.c_feed = 0
        self.c_clap = 0
        self.c_startle = 0

        self.btn_feed = pygame.Rect(SCREEN_W - 36, TOP_H + BOT_H - 34, 28, 28)
        self.food_sprite = self._load_single_sprite(FOOD_FILE)
        self.food_draw_sprite = self._build_food_draw_sprite()
        if self.food_draw_sprite is not None:
            self.btn_feed = self.food_draw_sprite.get_rect()
        self._randomize_food_position()
        self.dance_sprites = self._load_dance_sprites()
        self.eat_sprites = self._load_eat_sprites()
        self.dance_active = False
        self.dance_frame_idx = 0
        self.dance_next_swap_t = 0.0
        self.dance_off_since_t = 0.0
        self.dance_loud_t = 0.0
        self.eat_active = False
        self.eat_frame_idx = 0
        self.eat_next_swap_t = 0.0
        self.eat_end_t = 0.0

        self.background_top = self._load_background_top(BACKGROUND_FILE)
        self.background_night_top = self._load_background_top(NIGHT_BACKGROUND_FILE)
        self.sleeping_sprite = self._load_single_sprite(SLEEPING_SPRITE_FILE)
        self.sleeping_draw_sprite = self._build_sleeping_draw_sprite()
        self.sprites = self._load_sprites()
        self.dance_draw_sprites = self._build_dance_draw_sprites()
        self.eat_draw_sprites = self._build_eat_draw_sprites()

    def _load_background_top(self, background_file):
        bg_path = asset_path(background_file)
        if not os.path.exists(bg_path):
            return None
        try:
            bg = pygame.image.load(bg_path).convert()
            if (bg.get_width(), bg.get_height()) != (SCREEN_W, TOP_H):
                try:
                    bg = pygame.transform.smoothscale(bg, (SCREEN_W, TOP_H))
                except Exception:
                    bg = pygame.transform.scale(bg, (SCREEN_W, TOP_H))
            return bg
        except Exception as e:
            print("background load failed:", bg_path, e)
            return None

    def _load_single_sprite(self, sprite_file):
        sprite_path = asset_path(sprite_file)
        if not os.path.exists(sprite_path):
            print("sprite missing:", sprite_path)
            return None
        try:
            return pygame.image.load(sprite_path).convert_alpha()
        except Exception as e:
            print("sprite load failed:", sprite_path, e)
            return None

    def _load_sprites(self):
        sprites = {}
        idle_path = SPRITE_FILES[STATE_IDLE]
        idle_img = None

        for st, path in SPRITE_FILES.items():
            resolved = asset_path(path)
            if os.path.exists(resolved):
                try:
                    sprites[st] = pygame.image.load(resolved).convert_alpha()
                except Exception:
                    sprites[st] = None
            else:
                sprites[st] = None

        if sprites.get(STATE_IDLE) is not None:
            idle_img = sprites[STATE_IDLE]
        elif os.path.exists(asset_path("nemma.bmp")):
            try:
                idle_img = pygame.image.load(asset_path("nemma.bmp")).convert_alpha()
            except Exception:
                idle_img = None

        for st in SPRITE_FILES.keys():
            if sprites.get(st) is None:
                sprites[st] = idle_img
        return sprites

    def _load_dance_sprites(self):
        frames = []
        for path in DANCE_FILES:
            resolved = asset_path(path)
            if not os.path.exists(resolved):
                print("dance frame missing:", resolved)
                return []
            try:
                frames.append(pygame.image.load(resolved).convert_alpha())
            except Exception as e:
                print("dance frame load failed:", resolved, e)
                return []
        return frames

    def _build_dance_draw_sprites(self):
        if len(self.dance_sprites) != 2:
            return self.dance_sprites
        if abs(DANCE_SPRITE_SCALE - 1.0) < 1e-6:
            return self.dance_sprites
        scaled = []
        for img in self.dance_sprites:
            w = max(1, int(img.get_width() * DANCE_SPRITE_SCALE))
            h = max(1, int(img.get_height() * DANCE_SPRITE_SCALE))
            try:
                scaled_img = pygame.transform.smoothscale(img, (w, h))
            except Exception:
                scaled_img = pygame.transform.scale(img, (w, h))
            scaled.append(scaled_img)
        return scaled

    def _load_eat_sprites(self):
        frames = []
        for path in EAT_FILES:
            resolved = asset_path(path)
            if not os.path.exists(resolved):
                print("eat frame missing:", resolved)
                return []
            try:
                frames.append(pygame.image.load(resolved).convert_alpha())
            except Exception as e:
                print("eat frame load failed:", resolved, e)
                return []
        return frames

    def _build_eat_draw_sprites(self):
        if len(self.eat_sprites) != 2:
            return self.eat_sprites
        if abs(EAT_SPRITE_SCALE - 1.0) < 1e-6:
            return self.eat_sprites
        scaled = []
        for img in self.eat_sprites:
            w = max(1, int(img.get_width() * EAT_SPRITE_SCALE))
            h = max(1, int(img.get_height() * EAT_SPRITE_SCALE))
            try:
                scaled_img = pygame.transform.smoothscale(img, (w, h))
            except Exception:
                scaled_img = pygame.transform.scale(img, (w, h))
            scaled.append(scaled_img)
        return scaled

    def _build_food_draw_sprite(self):
        if self.food_sprite is None:
            return None
        if abs(FOOD_ICON_SCALE - 1.0) < 1e-6:
            return self.food_sprite
        w = max(1, int(self.food_sprite.get_width() * FOOD_ICON_SCALE))
        h = max(1, int(self.food_sprite.get_height() * FOOD_ICON_SCALE))
        try:
            return pygame.transform.smoothscale(self.food_sprite, (w, h))
        except Exception:
            return pygame.transform.scale(self.food_sprite, (w, h))

    def _build_sleeping_draw_sprite(self):
        if self.sleeping_sprite is None:
            return None
        if abs(SLEEPING_SPRITE_SCALE - 1.0) < 1e-6:
            return self.sleeping_sprite
        w = max(1, int(self.sleeping_sprite.get_width() * SLEEPING_SPRITE_SCALE))
        h = max(1, int(self.sleeping_sprite.get_height() * SLEEPING_SPRITE_SCALE))
        try:
            return pygame.transform.smoothscale(self.sleeping_sprite, (w, h))
        except Exception:
            return pygame.transform.scale(self.sleeping_sprite, (w, h))

    def _randomize_food_position(self):
        max_x = SCREEN_W - self.btn_feed.width - FOOD_SPAWN_MARGIN
        max_y = SCREEN_H - self.btn_feed.height - FOOD_SPAWN_MARGIN
        min_x = FOOD_SPAWN_MARGIN
        min_y = FOOD_SPAWN_MARGIN
        if max_x < min_x:
            self.btn_feed.x = max(0, SCREEN_W - self.btn_feed.width)
        else:
            self.btn_feed.x = random.randint(min_x, max_x)
        if max_y < min_y:
            self.btn_feed.y = max(0, SCREEN_H - self.btn_feed.height)
        else:
            self.btn_feed.y = random.randint(min_y, max_y)

    def _set_state(self, s):
        now = time.monotonic()
        if s == self.state:
            return
        self.state = s
        self.state_t = now
        if s == STATE_STARTLED:
            self.c_startle += 1
            self.sounds.cute("startle")
        elif s == STATE_CURIOUS:
            self.sounds.cute("curious")

    def _wake_from_sleep(self):
        self.is_asleep = False
        self.sleepy_elapsed = 0.0
        self.wake_requested = False
        self.dark_t = 0.0
        self.bright_t = 0.0
        self.dance_active = False
        self.dance_loud_t = 0.0
        self.eat_active = False
        self._set_state(STATE_IDLE)

    def _can_leave(self):
        return (time.monotonic() - self.state_t) >= STATE_MIN_DWELL[self.state]

    def _pet(self):
        self.c_pet += 1
        self.sounds.cute("pet")
        self._set_state(STATE_HAPPY)

    def _feed(self):
        self.c_feed += 1
        self.feed_flash_until = time.monotonic() + 0.7
        self.sounds.cute("feed")
        self._randomize_food_position()
        if len(self.eat_draw_sprites) == 2:
            now = time.monotonic()
            self.eat_active = True
            self.eat_frame_idx = 0
            self.eat_next_swap_t = now + (random.randint(EAT_FRAME_MIN_MS, EAT_FRAME_MAX_MS) / 1000.0)
            self.eat_end_t = now + EAT_DURATION_S
        self._set_state(STATE_HAPPY)

    def _on_nemma_tap(self):
        now = time.monotonic()
        self.c_tap += 1
        if (now - self.last_nemma_tap_t) <= 0.35:
            self.last_nemma_tap_t = -99.0
            self._feed()
        else:
            self.last_nemma_tap_t = now
            self.sounds.cute("tap")

    def _handle_click(self, x, y):
        self.c_tap += 1
        if self.btn_feed.collidepoint(x, y):
            if self.is_asleep:
                self.wake_requested = True
            self.btn_feed_latch = True
            return

        if y < TOP_H:
            self.tx = clamp(x, 24.0, SCREEN_W - 24.0)
            self.ty = clamp(y, 26.0, TOP_H - 20.0)
            dx = x - self.x
            dy = y - self.y
            if self.is_asleep and (dx * dx + dy * dy) <= (42.0 * 42.0):
                self.wake_requested = True
                return
            if (dx * dx + dy * dy) <= (42.0 * 42.0):
                self._pet()
                self._on_nemma_tap()

    def _update_inputs(self):
        for ev in pygame.event.get():
            if ev.type == QUIT:
                raise SystemExit
            if ev.type == KEYDOWN:
                if ev.key == K_a:
                    if self.is_asleep:
                        self.wake_requested = True
                    self.btn_feed_latch = True
            if ev.type == MOUSEBUTTONDOWN:
                x, y = ev.pos
                self._handle_click(x, y)
            if ev.type == MOUSEMOTION and ev.buttons[0]:
                x, y = ev.pos
                if y < TOP_H:
                    self.tx = clamp(x, 24.0, SCREEN_W - 24.0)
                    self.ty = clamp(y, 26.0, TOP_H - 20.0)

        # Hardware A is the only mapped hardware control right now.
        # Button B is intentionally reserved so we can add a second action later
        # without changing existing button-A behavior.
        self.raw_a = self.io.read_btn(self.io.button_a)
        if self.raw_a and (not self.prev_raw_a):
            if self.is_asleep:
                self.wake_requested = True
            # Feed on press edge only (not while held) to avoid repeated retriggers.
            self.btn_feed_latch = True
        self.prev_raw_a = self.raw_a

    def _update_logic(self):
        now = time.monotonic()
        dt = max(0.0, now - self.prev_t)
        self.prev_t = now

        if self.btn_feed_latch:
            self.btn_feed_latch = False
            self._feed()

        if self.last_nemma_tap_t > 0 and (now - self.last_nemma_tap_t) > 0.35:
            self.last_nemma_tap_t = -99.0
            self._pet()

        ax, ay, az = self.io.read_accel()
        mag = math.sqrt(ax * ax + ay * ay + az * az)
        dmag = abs(mag - self.prev_mag)
        self.prev_mag = mag
        self.accel_delta = ema(self.accel_delta, dmag, 0.22)

        mic = self.io.read_mic()
        self.mic_ema = ema(self.mic_ema, mic, 0.15)
        self.mic_activity = ema(self.mic_activity, abs(mic - self.prev_mic), DANCE_ACTIVITY_ALPHA)
        self.prev_mic = mic
        mic_spike = mic - self.mic_ema
        clap_th = max(self.profile["clap"], self.mic_ema * 0.10)
        loud_th = max(self.profile["loud"], self.mic_ema * 0.22)

        if self.is_asleep:
            if self.wake_requested or self.btn_feed_latch:
                self.btn_feed_latch = False
                self._wake_from_sleep()
            else:
                self.dance_active = False
                self.dance_frame_idx = 0
                self.dance_loud_t = 0.0
                self.eat_active = False
                self.sounds.update()
                return mic, mic_spike, clap_th

        light = self.io.read_light()
        self.light_now = light
        self.light_ema = ema(self.light_ema, light, 0.08)

        dance_ready = len(self.dance_sprites) == 2
        if dance_ready:
            # Require sustained loudness/activity to avoid conversation-triggered dancing.
            dance_candidate = (
                (mic >= DANCE_TRIGGER_MIC and mic_spike >= 1.0)
                or (self.mic_ema >= (DANCE_TRIGGER_MIC + 0.8) and self.mic_activity >= (DANCE_ACTIVITY_TRIGGER * 0.8))
                or (mic_spike >= DANCE_TRIGGER_SPIKE and self.mic_activity >= DANCE_ACTIVITY_TRIGGER)
            )
            if self.state == STATE_SLEEPY or self.dark_t >= (LIGHT_SLEEP_HOLD_S * 0.4) or self.light_ema < LIGHT_WAKE_THRESHOLD:
                dance_candidate = False
            if mic < DANCE_CONVO_BLOCK_MIC and self.mic_ema < DANCE_CONVO_BLOCK_MIC:
                dance_candidate = False
            if dance_candidate:
                self.dance_loud_t += dt
            else:
                self.dance_loud_t = max(0.0, self.dance_loud_t - dt * 2.2)
            dance_on = self.dance_loud_t >= DANCE_ON_HOLD_S
            dance_off_threshold = DANCE_TRIGGER_MIC - DANCE_OFF_HYST
            if dance_on:
                if not self.dance_active:
                    self.dance_active = True
                    self.dance_frame_idx = 0
                    self.dance_next_swap_t = now + (random.randint(DANCE_FRAME_MIN_MS, DANCE_FRAME_MAX_MS) / 1000.0)
                self.dance_off_since_t = now
            elif self.dance_active:
                # Keep dance briefly after audio falls to avoid flicker/missed visual feedback.
                if (
                    (mic > dance_off_threshold and mic_spike > -0.10)
                    or (self.mic_activity >= (DANCE_ACTIVITY_TRIGGER * 0.6))
                ):
                    self.dance_off_since_t = now
                elif (now - self.dance_off_since_t) >= DANCE_HOLD_S:
                    self.dance_active = False
                    self.dance_frame_idx = 0
                    self.dance_next_swap_t = now
            else:
                self.dance_active = False
        else:
            self.dance_active = False
            self.dance_loud_t = 0.0

        if self.dance_active and now >= self.dance_next_swap_t:
            self.dance_frame_idx = 1 - self.dance_frame_idx
            self.dance_next_swap_t = now + (random.randint(DANCE_FRAME_MIN_MS, DANCE_FRAME_MAX_MS) / 1000.0)

        if self.eat_active:
            if now >= self.eat_end_t:
                self.eat_active = False
                self.eat_frame_idx = 0
            elif now >= self.eat_next_swap_t:
                self.eat_frame_idx = 1 - self.eat_frame_idx
                self.eat_next_swap_t = now + (random.randint(EAT_FRAME_MIN_MS, EAT_FRAME_MAX_MS) / 1000.0)

        self.clap_event = False
        self.shake_event = False
        self.loud_event = False

        if self.accel_delta > self.profile["shake"] and (now - self.last_shake_t) > 0.45:
            self.last_shake_t = now
            self.shake_event = True
        if (mic_spike > clap_th or mic > (self.mic_ema * 1.22)) and (now - self.last_clap_t) > 0.25:
            self.last_clap_t = now
            self.clap_event = True
            self.c_clap += 1
        if mic_spike > loud_th or mic > (self.mic_ema + loud_th):
            self.loud_event = True

        still_now = (self.accel_delta < self.profile["still_acc"]) and (self.mic_ema < self.profile["still_mic"])
        if still_now:
            self.still_t += dt
        else:
            self.still_t = max(0.0, self.still_t - dt * 1.5)

        if light <= LIGHT_SLEEP_THRESHOLD:
            self.dark_t += dt
            self.bright_t = 0.0
        elif light >= LIGHT_WAKE_THRESHOLD:
            self.bright_t += dt
            self.dark_t = 0.0
        else:
            # Mid band keeps inertia and avoids flicker near thresholds.
            self.dark_t = max(0.0, self.dark_t - dt * 0.35)
            self.bright_t = max(0.0, self.bright_t - dt * 0.35)

        if self.state == STATE_SLEEPY:
            # Stay sleepy until we've had continuous bright light long enough.
            if self.bright_t >= LIGHT_SLEEP_HOLD_S:
                self._set_state(STATE_IDLE)
        elif self.dark_t >= LIGHT_SLEEP_HOLD_S:
            self._set_state(STATE_SLEEPY)
        elif self.shake_event or self.loud_event:
            self._set_state(STATE_STARTLED)
        elif self.clap_event and self._can_leave():
            self._set_state(STATE_CURIOUS)
        elif self.state == STATE_HAPPY and self._can_leave():
            self._set_state(STATE_IDLE)
        elif self.state == STATE_STARTLED and self._can_leave():
            self._set_state(STATE_IDLE)
        elif self.state == STATE_CURIOUS and self._can_leave() and (self.accel_delta < 0.2 and mic_spike < 4.0):
            self._set_state(STATE_IDLE)

        if self.state == STATE_SLEEPY:
            self.sleepy_elapsed += dt
            if self.sleepy_elapsed >= DEEP_SLEEP_AFTER_S:
                self.is_asleep = True
                self.dance_active = False
                self.dance_frame_idx = 0
                self.dance_next_swap_t = now
        else:
            self.sleepy_elapsed = 0.0

        if self.state == STATE_STARTLED:
            speed = 170.0
        elif self.state == STATE_SLEEPY:
            speed = 50.0
        elif self.state == STATE_HAPPY:
            speed = 120.0
        else:
            speed = 90.0

        dx = self.tx - self.x
        dy = self.ty - self.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 0.1:
            step = min(dist, speed * dt)
            self.x += dx * (step / dist)
            self.y += dy * (step / dist)

        self.sounds.update()

        return mic, mic_spike, clap_th

    def _draw(self, mic, mic_spike, clap_th):
        # These parameters are kept for optional debug overlays;
        # the current finalized UI doesn't render telemetry text.
        # top background
        top = (255, 226, 242)
        if self.state == STATE_STARTLED:
            top = (255, 196, 214)
        elif self.state == STATE_CURIOUS:
            top = (255, 214, 236)
        elif self.state == STATE_SLEEPY:
            top = (230, 205, 228)
        elif self.state == STATE_HAPPY:
            top = (255, 238, 245)
        if self.feed_flash_until > time.monotonic():
            top = (255, 240, 190)

        active_bg = self.background_night_top if self.is_asleep else self.background_top
        if active_bg is not None:
            self.screen.blit(active_bg, (0, 0))
        else:
            self.screen.fill(top, (0, 0, SCREEN_W, TOP_H))

        if self.is_asleep and self.sleeping_draw_sprite is not None:
            img = self.sleeping_draw_sprite
        elif self.eat_active and len(self.eat_draw_sprites) == 2:
            img = self.eat_draw_sprites[self.eat_frame_idx]
        elif self.dance_active and len(self.dance_draw_sprites) == 2:
            img = self.dance_draw_sprites[self.dance_frame_idx]
        else:
            img = self.sprites.get(self.state)
        if img is not None:
            rect = img.get_rect()
            rect.center = (int(self.x), int(self.y))
            self.screen.blit(img, rect)
        else:
            pygame.draw.circle(self.screen, (255, 159, 197), (int(self.x), int(self.y)), 26)

        # bottom panel
        self.screen.fill((31, 22, 33), (0, TOP_H, SCREEN_W, BOT_H))

        if self.food_draw_sprite is not None:
            self.screen.blit(self.food_draw_sprite, self.btn_feed)
        else:
            pygame.draw.rect(self.screen, (80, 53, 90), self.btn_feed, border_radius=6)
            feed_txt = self.mode_font.render("F", True, (255, 215, 239))
            self.screen.blit(feed_txt, (self.btn_feed.x + 9, self.btn_feed.y + 5))

        if SHOW_MODE_LABEL:
            l1 = self.mode_font.render("NEMMA | {}".format(self.state), True, (180, 145, 170))
            self.screen.blit(l1, (4, SCREEN_H - 12))

        pygame.display.flip()

    def run(self):
        print("Nemma pygame mode start")
        while True:
            self._update_inputs()
            mic, mic_spike, clap_th = self._update_logic()
            self.io.audio_tick()
            self._draw(mic, mic_spike, clap_th)
            self.clock.tick(FPS)


def main():
    random.seed(int(time.monotonic() * 1000) & 0xFFFFFFFF)
    app = NemmaApp()
    app.run()


if __name__ == "__main__":
    main()
