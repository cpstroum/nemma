import math
import struct
import time
import wave

VERSION = "LAB_v2_2026-03-24"

# Try imports in tolerant order.
GUI = None
Board = None
uni_ext = None
AudioClass = None

try:
    from pinpong.board import Board  # type: ignore
except Exception:
    Board = None

try:
    import pinpong.extension.unihiker as uni_ext  # type: ignore
except Exception:
    uni_ext = None

try:
    from unihiker import GUI as GUI1  # type: ignore

    GUI = GUI1
except Exception:
    try:
        from unihiker.GUI import GUI as GUI2  # type: ignore

        GUI = GUI2
    except Exception:
        try:
            from pinpong.extension.unihiker import GUI as GUI3  # type: ignore

            GUI = GUI3
        except Exception:
            GUI = None

try:
    from unihiker import Audio as Audio1  # type: ignore

    AudioClass = Audio1
except Exception:
    try:
        from unihiker.Audio import Audio as Audio2  # type: ignore

        AudioClass = Audio2
    except Exception:
        AudioClass = None


def resolve_device(module, candidates):
    if module is None:
        return None
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


def call_first(obj, names, default=0.0):
    if obj is None:
        return default
    for name in names:
        fn = getattr(obj, name, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                continue
    return default


if Board is not None:
    try:
        Board("UNIHIKER").begin()
    except Exception:
        try:
            Board().begin()
        except Exception:
            pass

gui = GUI() if GUI else None
audio = AudioClass() if AudioClass else None

button_a = resolve_device(uni_ext, ("button_a", "ButtonA", "BUTTON_A", "btn_a"))
button_b = resolve_device(uni_ext, ("button_b", "ButtonB", "BUTTON_B", "btn_b"))
buzzer = resolve_device(uni_ext, ("buzzer", "Buzzer", "BUZZER"))
mic = resolve_device(
    uni_ext,
    ("microphone", "Microphone", "MICROPHONE", "mic", "MIC", "sound", "sound_sensor", "noise"),
)
light = resolve_device(uni_ext, ("light", "Light", "LIGHT", "ambient_light", "light_sensor"))
accel = resolve_device(uni_ext, ("accelerometer", "Accelerometer", "ACCELEROMETER", "accel"))

mic_source = "none"
if mic is not None:
    mic_source = "ext"
elif audio is not None:
    mic_source = "audio"


def read_btn(btn):
    if btn is None:
        return False
    if callable(btn):
        try:
            return bool(btn())
        except Exception:
            pass
    for name in ("is_pressed", "pressed", "value", "read", "status", "get_key", "key"):
        attr = getattr(btn, name, None)
        if callable(attr):
            try:
                value = attr()
                if isinstance(value, str):
                    return value.strip().lower() in ("1", "true", "pressed", "down", "a", "b")
                return bool(value)
            except Exception:
                continue
        if isinstance(attr, (bool, int)):
            return bool(attr)
    return False


def read_mic():
    if mic is not None:
        return float(
            call_first(
                mic,
                ("read", "sound_level", "value", "get_value", "get_loudness", "loudness", "volume", "get_volume"),
                0.0,
            )
        )
    if audio is not None:
        return float(
            call_first(
                audio,
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
    return 0.0


def read_light():
    if light is None:
        return -1.0
    return float(call_first(light, ("read", "get_value", "value", "lightness"), -1.0))


def read_accel():
    if accel is None:
        return 0.0, 0.0, 0.0
    return (
        float(call_first(accel, ("get_x", "x", "read_x"), 0.0)),
        float(call_first(accel, ("get_y", "y", "read_y"), 0.0)),
        float(call_first(accel, ("get_z", "z", "read_z"), 0.0)),
    )


def tone_buzzer(freq, dur):
    if buzzer is None:
        return False, "no_buzzer"

    # Documented APIs first: buzzer.pitch(...) and buzzer.play(song, mode).
    pitch_fn = getattr(buzzer, "pitch", None)
    if callable(pitch_fn):
        try:
            # Common form from docs examples.
            pitch_fn(int(freq), 4)
            return True, "buzzer.pitch(f,4)"
        except Exception:
            pass
        try:
            pitch_fn(int(freq))
            time.sleep(dur)
            stop_fn = getattr(buzzer, "stop", None)
            if callable(stop_fn):
                try:
                    stop_fn()
                except Exception:
                    pass
            return True, "buzzer.pitch(f)"
        except Exception:
            pass

    play_fn = getattr(buzzer, "play", None)
    if callable(play_fn):
        for song_name in ("BA_DING", "RINGTONE", "POWER_UP"):
            song = getattr(buzzer, song_name, None)
            once = getattr(buzzer, "Once", None)
            if song is not None and once is not None:
                try:
                    play_fn(song, once)
                    return True, "buzzer.play({})".format(song_name)
                except Exception:
                    pass

    for name in ("play", "tone", "freq"):
        fn = getattr(buzzer, name, None)
        if callable(fn):
            try:
                fn(int(freq), float(dur))
                return True, "buzzer.{}(f,d)".format(name)
            except Exception:
                pass
            try:
                fn(int(freq))
                time.sleep(dur)
                for stop_name in ("stop", "off", "mute"):
                    stop_fn = getattr(buzzer, stop_name, None)
                    if callable(stop_fn):
                        try:
                            stop_fn()
                        except Exception:
                            pass
                return True, "buzzer.{}(f)+stop".format(name)
            except Exception:
                pass
    return False, "buzzer_failed"


def tone_wav_path(freq=880, dur=0.2):
    path = "lab_tone.wav"
    sample_rate = 16000
    frame_count = max(1, int(sample_rate * dur))
    amp = 12000
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(frame_count):
            sample = int(amp * math.sin(2.0 * math.pi * float(freq) * (i / float(sample_rate))))
            wf.writeframes(struct.pack("<h", sample))
    return path


def tone_audio(freq, dur):
    if audio is None:
        return False, "no_audio"
    path = tone_wav_path(freq, dur)
    for name in ("play", "start_play", "play_file"):
        fn = getattr(audio, name, None)
        if callable(fn):
            try:
                fn(path)
                return True, "audio.{}".format(name)
            except Exception:
                pass
    pb = getattr(audio, "playback", None)
    if pb is not None:
        for name in ("play", "start"):
            fn = getattr(pb, name, None)
            if callable(fn):
                try:
                    fn(path)
                    return True, "audio.playback.{}".format(name)
                except Exception:
                    pass
    return False, "audio_failed"


# state
cnt_a = 0
cnt_b = 0
cnt_soft_a = 0
cnt_soft_b = 0
cnt_soft_audio = 0
cnt_soft_probe = 0
raw_a = False
raw_b = False
prev_a = False
prev_b = False
last_audio = "none"
audio_mode = 0
last_probe = "none"

print("{} start".format(VERSION))
print(
    "gui={} pinpong={} btnA={} btnB={} buzzer={} mic={} light={} accel={} audio={} micSrc={}".format(
        int(gui is not None),
        int(uni_ext is not None),
        int(button_a is not None),
        int(button_b is not None),
        int(buzzer is not None),
        int(mic is not None),
        int(light is not None),
        int(accel is not None),
        int(audio is not None),
        mic_source,
    )
)

if gui is None:
    while True:
        raw_a = read_btn(button_a)
        raw_b = read_btn(button_b)
        if raw_a and not prev_a:
            cnt_a += 1
        if raw_b and not prev_b:
            cnt_b += 1
        prev_a = raw_a
        prev_b = raw_b

        mic_v = read_mic()
        light_v = read_light()
        ax, ay, az = read_accel()
        print(
            "rawA={} rawB={} edgeA={} edgeB={} mic={:.1f} light={:.1f} accel=({:.2f},{:.2f},{:.2f})".format(
                int(raw_a), int(raw_b), cnt_a, cnt_b, mic_v, light_v, ax, ay, az
            )
        )
        time.sleep(0.25)

# UI mode
if hasattr(gui, "clear"):
    gui.clear()


def gcall(name, **kwargs):
    fn = getattr(gui, name, None)
    if callable(fn):
        try:
            return fn(**kwargs)
        except Exception:
            return None
    return None


def cfg(obj, **kwargs):
    if obj is None:
        return
    fn = getattr(obj, "config", None)
    if callable(fn):
        try:
            fn(**kwargs)
        except Exception:
            pass


gcall("draw_rect", x=0, y=0, w=240, h=320, color="#101015", fill=True)

t1 = gcall("draw_text", x=8, y=8, text=VERSION, color="#a8ffcf", font_size=12)
t2 = gcall("draw_text", x=8, y=28, text="init", color="#ffd8ee", font_size=10)
t3 = gcall("draw_text", x=8, y=44, text="init", color="#ffd8ee", font_size=10)
t4 = gcall("draw_text", x=8, y=164, text="init", color="#ffd8ee", font_size=10)
t5 = gcall("draw_text", x=8, y=60, text="init", color="#ffd8ee", font_size=10)
t6 = gcall("draw_text", x=8, y=76, text="init", color="#ffd8ee", font_size=10)
t7 = gcall("draw_text", x=8, y=92, text="init", color="#ffd8ee", font_size=10)

# soft buttons
def on_soft_a():
    global cnt_soft_a
    cnt_soft_a += 1


def on_soft_b():
    global cnt_soft_b
    cnt_soft_b += 1


def on_soft_audio():
    global cnt_soft_audio, last_audio, audio_mode
    cnt_soft_audio += 1
    if audio_mode == 0:
        ok, msg = tone_buzzer(880, 0.2)
        last_audio = msg if ok else msg
    elif audio_mode == 1:
        ok, msg = tone_audio(880, 0.2)
        last_audio = msg if ok else msg
    else:
        ok1, msg1 = tone_buzzer(1200, 0.12)
        if ok1:
            last_audio = msg1
        else:
            _, msg2 = tone_audio(1200, 0.12)
            last_audio = msg2
    audio_mode = (audio_mode + 1) % 3


def on_soft_probe():
    global cnt_soft_probe, last_probe
    cnt_soft_probe += 1
    light_v = read_light()
    mic_v = read_mic()
    ax, ay, az = read_accel()
    last_probe = "mic={:.1f} light={:.1f} a=({:.2f},{:.2f},{:.2f})".format(mic_v, light_v, ax, ay, az)


b1 = gcall("add_button", x=8, y=132, w=28, h=28, text="A", onclick=on_soft_a)
b2 = gcall("add_button", x=40, y=132, w=28, h=28, text="B", onclick=on_soft_b)
b3 = gcall("add_button", x=72, y=132, w=78, h=28, text="AUD", onclick=on_soft_audio)
b4 = gcall("add_button", x=154, y=132, w=78, h=28, text="PROBE", onclick=on_soft_probe)


# key callbacks
def on_key(*args):
    global cnt_a, cnt_b
    if not args:
        return
    key_text = str(args[0]).lower()
    if "a" in key_text:
        cnt_a += 1
    if "b" in key_text:
        cnt_b += 1


for cb_name in ("on_key_click", "on_key_press", "on_key_down"):
    cb = getattr(gui, cb_name, None)
    if callable(cb):
        try:
            cb(on_key)
        except Exception:
            pass

while True:
    raw_a = read_btn(button_a)
    raw_b = read_btn(button_b)
    if raw_a and not prev_a:
        cnt_a += 1
    if raw_b and not prev_b:
        cnt_b += 1
    prev_a = raw_a
    prev_b = raw_b

    mic_v = read_mic()
    light_v = read_light()
    ax, ay, az = read_accel()

    cfg(
        t2,
        text="rawA={} rawB={} edgeA={} edgeB={}".format(int(raw_a), int(raw_b), cnt_a, cnt_b),
    )
    cfg(
        t3,
        text="softA={} softB={} softAUD={} probe={}".format(cnt_soft_a, cnt_soft_b, cnt_soft_audio, cnt_soft_probe),
    )
    cfg(t4, text=last_probe)
    cfg(t5, text="audio={} mode={}".format(last_audio, audio_mode))
    cfg(t6, text="mic={:.1f} src={}".format(mic_v, mic_source))
    cfg(t7, text="light={:.1f} accel=({:.2f},{:.2f},{:.2f})".format(light_v, ax, ay, az))

    time.sleep(0.05)
