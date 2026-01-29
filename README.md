# MAC-2 Acoustic Logging Model (Simplified)

This repository provides a minimal, reproducible model of the acoustic signal
for a MAC-2 style logging tool in a cased borehole filled with technical water.
It focuses on time-of-flight and geometric spreading in the fluid column.

## Geometry & Parameters

- Borehole diameter: 278 mm
- Casing diameter: 245 mm
- Tool diameter: 73 mm
- Source to receiver 1: 1.0 m
- Receiver 1 to receiver 2: 0.5 m
- Source frequency: 22 kHz (informational)
- Source pulse: `8000 * exp(-((t - T0)/(T0/2))^2)`

The tool is centered in the borehole and modeled as a three-element
configuration (source + two receivers).

## Model assumptions

- Only the **direct fluid wave** is modeled.
- The fluid P-wave velocity and attenuation are configurable.
- Amplitude includes geometric spreading (`1/r`) and exponential attenuation.

You can extend the model with additional wave modes (casing, formation,
reflections) by adding more arrivals to `model_signals()`.

## Usage

```bash
python acoustic_model.py --csv signals.csv
```

Optional parameters:

```bash
python acoustic_model.py \
  --duration 0.01 \
  --sample-rate 200000 \
  --fluid-velocity 1500 \
  --attenuation 0.4 \
  --t0 0.0005 \
  --csv signals.csv \
  --plot waveform.svg \
  --summary
```

The output CSV has columns `time_s`, `rx1`, `rx2`.

Sample output artifacts (CSV + SVG waveform + run summary) are stored in `outputs/`.
