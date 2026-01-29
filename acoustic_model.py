"""Simple acoustic logging signal model for MAC-2 geometry.

This script models a Gaussian pulse emitted by a source and the received
signals at two receivers in a fluid-filled cased borehole. The model is a
first-order approximation focused on time-of-flight and geometric spreading
in the fluid. It is intentionally minimal and designed to be easy to extend
with additional wave paths (casing, formation, reflections).
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from math import exp
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class Geometry:
    borehole_diameter_m: float = 0.278
    casing_diameter_m: float = 0.245
    tool_diameter_m: float = 0.073
    source_to_rx1_m: float = 1.0
    rx1_to_rx2_m: float = 0.5


@dataclass(frozen=True)
class Medium:
    fluid_velocity_m_s: float = 1500.0
    casing_velocity_m_s: float = 5000.0
    formation_velocity_m_s: float = 3500.0
    fluid_attenuation_neper_m: float = 0.4
    casing_attenuation_neper_m: float = 0.15
    formation_attenuation_neper_m: float = 0.2


@dataclass(frozen=True)
class WavePath:
    label: str
    velocity_m_s: float
    attenuation_neper_m: float
    coupling: float


@dataclass(frozen=True)
class Source:
    frequency_hz: float = 22_000.0
    t0_s: float = 0.0005

    def pulse(self, t: float) -> float:
        """Gaussian pulse: 8000 * exp(-((t - T0)/(T0/2))^2)."""
        width = self.t0_s / 2.0
        return 8000.0 * exp(-((t - self.t0_s) / width) ** 2)


@dataclass(frozen=True)
class Simulation:
    duration_s: float = 0.01
    sample_rate_hz: float = 200_000.0

    def time_axis(self) -> List[float]:
        n = int(self.duration_s * self.sample_rate_hz)
        return [i / self.sample_rate_hz for i in range(n)]


def arrival_time(distance_m: float, velocity_m_s: float) -> float:
    return distance_m / velocity_m_s


def apply_attenuation(amplitude: float, distance_m: float, attenuation_neper_m: float) -> float:
    geometric = 1.0 / max(distance_m, 1e-6)
    loss = exp(-attenuation_neper_m * distance_m)
    return amplitude * geometric * loss


def synthesize_signal(
    times: Iterable[float],
    source: Source,
    travel_time_s: float,
    amplitude: float,
) -> List[float]:
    return [amplitude * source.pulse(t - travel_time_s) for t in times]


def build_paths(medium: Medium) -> Tuple[WavePath, WavePath, WavePath]:
    return (
        WavePath("fluid", medium.fluid_velocity_m_s, medium.fluid_attenuation_neper_m, 1.0),
        WavePath("casing", medium.casing_velocity_m_s, medium.casing_attenuation_neper_m, 0.35),
        WavePath("formation", medium.formation_velocity_m_s, medium.formation_attenuation_neper_m, 0.25),
    )


def parse_path(path_spec: str) -> WavePath:
    parts = [p.strip() for p in path_spec.split(",")]
    if len(parts) != 4:
        raise ValueError("Wave path must be label,velocity,attenuation,coupling")
    label, velocity, attenuation, coupling = parts
    return WavePath(
        label=label,
        velocity_m_s=float(velocity),
        attenuation_neper_m=float(attenuation),
        coupling=float(coupling),
    )


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def model_signals(
    geometry: Geometry,
    medium: Medium,
    source: Source,
    simulation: Simulation,
    paths: Iterable[WavePath],
) -> Tuple[List[float], List[float], List[float]]:
    times = simulation.time_axis()

    rx1_distance = geometry.source_to_rx1_m
    rx2_distance = geometry.source_to_rx1_m + geometry.rx1_to_rx2_m

    rx1_signal = [0.0 for _ in times]
    rx2_signal = [0.0 for _ in times]

    for path in paths:
        rx1_time = arrival_time(rx1_distance, path.velocity_m_s)
        rx2_time = arrival_time(rx2_distance, path.velocity_m_s)

        rx1_amp = apply_attenuation(path.coupling, rx1_distance, path.attenuation_neper_m)
        rx2_amp = apply_attenuation(path.coupling, rx2_distance, path.attenuation_neper_m)

        rx1_component = synthesize_signal(times, source, rx1_time, rx1_amp)
        rx2_component = synthesize_signal(times, source, rx2_time, rx2_amp)

        rx1_signal = [a + b for a, b in zip(rx1_signal, rx1_component)]
        rx2_signal = [a + b for a, b in zip(rx2_signal, rx2_component)]

    return times, rx1_signal, rx2_signal


def write_csv(path: str, times: Iterable[float], rx1: Iterable[float], rx2: Iterable[float]) -> None:
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time_s", "rx1", "rx2"])
        for t, r1, r2 in zip(times, rx1, rx2):
            writer.writerow([t, r1, r2])


def compute_peak(signal: Iterable[float]) -> Tuple[float, float]:
    peak_value = None
    peak_index = 0
    for index, value in enumerate(signal):
        if peak_value is None or abs(value) > abs(peak_value):
            peak_value = value
            peak_index = index
    if peak_value is None:
        return 0.0, 0.0
    return peak_value, peak_index


def plot_signals(path: str, times: List[float], rx1: List[float], rx2: List[float]) -> None:
    width = 1000
    height = 500
    padding = 50

    if not times:
        return

    min_time = min(times)
    max_time = max(times)
    max_amp = max(max(abs(v) for v in rx1), max(abs(v) for v in rx2), 1e-9)

    def scale_x(t: float) -> float:
        return padding + (t - min_time) / (max_time - min_time) * (width - 2 * padding)

    def scale_y(v: float) -> float:
        return padding + (height - 2 * padding) * (0.5 - 0.5 * v / max_amp)

    def polyline(signal: List[float]) -> str:
        points = " ".join(f"{scale_x(t):.2f},{scale_y(v):.2f}" for t, v in zip(times, signal))
        return points

    rx1_points = polyline(rx1)
    rx2_points = polyline(rx2)

    svg = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\">
  <rect width=\"100%\" height=\"100%\" fill=\"white\"/>
  <line x1=\"{padding}\" y1=\"{height - padding}\" x2=\"{width - padding}\" y2=\"{height - padding}\" stroke=\"#333\"/>
  <line x1=\"{padding}\" y1=\"{padding}\" x2=\"{padding}\" y2=\"{height - padding}\" stroke=\"#333\"/>
  <text x=\"{width / 2}\" y=\"{height - 10}\" text-anchor=\"middle\" font-size=\"14\">Time (s)</text>
  <text x=\"15\" y=\"{height / 2}\" text-anchor=\"middle\" font-size=\"14\" transform=\"rotate(-90 15 {height / 2})\">Amplitude</text>
  <text x=\"{width / 2}\" y=\"{padding / 2}\" text-anchor=\"middle\" font-size=\"16\">MAC-2 Acoustic Waveform (Physical Wave Paths)</text>
  <polyline fill=\"none\" stroke=\"#1f77b4\" stroke-width=\"1.5\" points=\"{rx1_points}\"/>
  <polyline fill=\"none\" stroke=\"#ff7f0e\" stroke-width=\"1.5\" points=\"{rx2_points}\"/>
  <rect x=\"{width - padding - 180}\" y=\"{padding}\" width=\"170\" height=\"45\" fill=\"white\" stroke=\"#333\"/>
  <line x1=\"{width - padding - 165}\" y1=\"{padding + 15}\" x2=\"{width - padding - 135}\" y2=\"{padding + 15}\" stroke=\"#1f77b4\" stroke-width=\"1.5\"/>
  <text x=\"{width - padding - 125}\" y=\"{padding + 20}\" font-size=\"12\">Receiver 1</text>
  <line x1=\"{width - padding - 165}\" y1=\"{padding + 32}\" x2=\"{width - padding - 135}\" y2=\"{padding + 32}\" stroke=\"#ff7f0e\" stroke-width=\"1.5\"/>
  <text x=\"{width - padding - 125}\" y=\"{padding + 37}\" font-size=\"12\">Receiver 2</text>
</svg>
"""

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(svg)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Model MAC-2 acoustic logging signals.")
    parser.add_argument("--config", type=Path, help="Optional JSON config file.")
    parser.add_argument("--duration", type=float, default=0.01, help="Simulation duration (s).")
    parser.add_argument("--sample-rate", type=float, default=200_000.0, help="Sample rate (Hz).")
    parser.add_argument("--fluid-velocity", type=float, default=1500.0, help="Fluid P-wave velocity (m/s).")
    parser.add_argument("--casing-velocity", type=float, default=5000.0, help="Casing wave velocity (m/s).")
    parser.add_argument("--formation-velocity", type=float, default=3500.0, help="Formation wave velocity (m/s).")
    parser.add_argument("--fluid-attenuation", type=float, default=0.4, help="Fluid attenuation (neper/m).")
    parser.add_argument("--casing-attenuation", type=float, default=0.15, help="Casing attenuation (neper/m).")
    parser.add_argument(
        "--formation-attenuation",
        type=float,
        default=0.2,
        help="Formation attenuation (neper/m).",
    )
    parser.add_argument("--t0", type=float, default=0.0005, help="Pulse T0 (s).")
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Custom wave path: label,velocity,attenuation,coupling (repeatable).",
    )
    parser.add_argument("--csv", default="signals.csv", help="Output CSV path.")
    parser.add_argument("--plot", default="", help="Optional plot output path (SVG).")
    parser.add_argument("--summary", action="store_true", help="Print a numeric summary.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = load_config(args.config) if args.config else {}
    geometry_cfg = config.get("geometry", {})
    medium_cfg = config.get("medium", {})
    source_cfg = config.get("source", {})
    simulation_cfg = config.get("simulation", {})

    geometry = Geometry(**{**geometry_cfg})
    medium = Medium(
        fluid_velocity_m_s=medium_cfg.get("fluid_velocity_m_s", args.fluid_velocity),
        casing_velocity_m_s=medium_cfg.get("casing_velocity_m_s", args.casing_velocity),
        formation_velocity_m_s=medium_cfg.get("formation_velocity_m_s", args.formation_velocity),
        fluid_attenuation_neper_m=medium_cfg.get("fluid_attenuation_neper_m", args.fluid_attenuation),
        casing_attenuation_neper_m=medium_cfg.get("casing_attenuation_neper_m", args.casing_attenuation),
        formation_attenuation_neper_m=medium_cfg.get(
            "formation_attenuation_neper_m", args.formation_attenuation
        ),
    )
    source = Source(t0_s=source_cfg.get("t0_s", args.t0))
    simulation = Simulation(
        duration_s=simulation_cfg.get("duration_s", args.duration),
        sample_rate_hz=simulation_cfg.get("sample_rate_hz", args.sample_rate),
    )

    if args.path:
        paths = [parse_path(path) for path in args.path]
    elif config.get("paths"):
        paths = [
            WavePath(
                label=path["label"],
                velocity_m_s=path["velocity_m_s"],
                attenuation_neper_m=path["attenuation_neper_m"],
                coupling=path["coupling"],
            )
            for path in config["paths"]
        ]
    else:
        paths = list(build_paths(medium))

    times, rx1_signal, rx2_signal = model_signals(geometry, medium, source, simulation, paths)
    write_csv(args.csv, times, rx1_signal, rx2_signal)

    if args.plot:
        plot_signals(args.plot, times, rx1_signal, rx2_signal)

    if args.summary:
        rx1_peak, rx1_index = compute_peak(rx1_signal)
        rx2_peak, rx2_index = compute_peak(rx2_signal)
        rx1_time = times[int(rx1_index)] if times else 0.0
        rx2_time = times[int(rx2_index)] if times else 0.0
        print("Summary:")
        print(f"  Receiver 1 peak: {rx1_peak:.6f} at {rx1_time:.6f} s")
        print(f"  Receiver 2 peak: {rx2_peak:.6f} at {rx2_time:.6f} s")

    print(f"Saved {args.csv} with {len(times)} samples.")


if __name__ == "__main__":
    main()
