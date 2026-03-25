# Lessons Learned: Nemma on UNIHIKER

## Platform and Runtime

- UNIHIKER firmware/runtime APIs are not always consistent across versions.
- Device discovery should be tolerant: probe multiple symbol names for each sensor/device.
- A desktop-compatible fallback loop is useful for testing UI/logic when hardware paths are unavailable.

## Sensor Integration

- Microphone access can come from different backends:
  - `pinpong.extension.unihiker` microphone path (preferred)
  - `unihiker.Audio` fallback path when extension mic is missing
- Light sensor values are useful for sleep/wake state transitions and need hysteresis to avoid flicker.
- Accelerometer deltas are better than raw values for shake/startle detection.

## State and Behavior Tuning

- Debouncing and dwell times make mood transitions feel intentional instead of noisy.
- Hysteresis and hold timers are essential for:
  - dance start/stop stability
  - light-based sleepy/wake transitions
- Sustained loudness/activity gating prevents normal conversation from constantly triggering dance.

## Input Handling

- Hard button input should be treated as hardware signals (raw + edge counting), not only GUI key callbacks.
- Mapping only button `A` to feed keeps behavior stable; reserving `B` avoids accidental regressions while leaving room for future features.
- Double-tap logic needs a short timing window plus fallback behavior for single taps.

## Audio Output

- Main app sound path is buzzer-based.
- In diagnostics, audio-file playback can be tested separately (WAV generation path), but production behavior should not depend on it.
- Trying multiple buzzer methods (`pitch`, `play`, `tone`, `freq`) improves compatibility.

## Diagnostics Workflow

- A dedicated `interaction_lab.py` significantly reduces debugging time before tuning game logic.
- Most useful live diagnostics:
  - hard button raw states and edge counters
  - soft button counters
  - mic value and source (`ext`/`audio`/`none`)
  - light sensor value
  - audio method used
  - manual probe snapshots for quick sanity checks

## UI and UX Iteration

- Small layout details matter in on-device diagnostics (button widths, text placement, readable status lines).
- Keeping only high-value diagnostics on screen avoids clutter and makes tests faster.
- Placing the stored probe snapshot below the soft button row makes it easier to verify manual probe actions.

## Project Hygiene

- Keep README synchronized with current behavior to avoid stale assumptions.
- Add comments only where behavior is intentionally reserved/disabled or non-obvious.
- Separate production app logic from diagnostics tooling to keep the main runtime clean.
