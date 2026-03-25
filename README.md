# Nemma (UNIHIKER)

Nemma is a UNIHIKER-first virtual creature app with a pygame-compatible desktop fallback for local testing.

## Main Files

- `unihiker_code.py`: primary app runtime
- `interaction_lab.py`: hardware/audio diagnostics helper
- Sprite/background assets: `nemma_*.png`, `dance*.png`, `eat*.png`, `background*.png`, `food.png`

## Current Behavior

- States: `IDLE`, `CURIOUS`, `HAPPY`, `STARTLED`, `SLEEPY`
- Sleep flow:
  - Low light over time pushes Nemma into `SLEEPY`
  - Extended sleepy duration enters deep sleep
  - Feed input/tap can request wake
- Reactions:
  - Sudden loud/sharp audio can trigger startled/curious behavior
  - Strong sustained loudness can trigger dance animation
- Feeding:
  - Feed action triggers happy state
  - Optional two-frame eat animation plays when feed sprites are present

## Controls

- Tap/click top area: move target position
- Tap/click Nemma: pet interaction (double-tap quickly to feed)
- Feed button (food icon): feed action
- Hardware button A: feed action
- Hardware button B: intentionally reserved (currently unmapped)

## Runtime Notes

- `SIMULATE_IF_MISSING = False` in `unihiker_code.py`:
  - Missing sensors do not emit fake values in production mode
- Mic backend probing order:
  - `pinpong.extension.unihiker` first
  - `unihiker.Audio` fallback if extension mic is unavailable

## Running

1. Ensure Python and `pygame` are installed.
2. Place all files/assets in the same directory.
3. Run:
   - `python unihiker_code.py`
   - `python interaction_lab.py` (optional diagnostics)

## Tuning

Tune behavior constants near the top of `unihiker_code.py`:

- Sleep/light thresholds and hold times
- Dance trigger thresholds and hold/hysteresis
- Eat/dance frame timing
- Mood profile thresholds (`MOOD_PROFILE`)
