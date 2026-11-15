# Phase 1: ascent to LKO and circularisation

Course: TM-4 (rocket equation, staging), TM-5 (fitted atmosphere), TM-6 (gravity turn, loss ledger), TM-7 (engines vs
pressure, cutoff on a target), TM-9/10 (circularisation PAD, burn time, centred finite burn).

## Plan (`planner/ascent.js`)
- Vehicle from the survey as five burn phases (three asparagus booster pairs, Mainsail core, Poodle), mixture Isp.
- Program search over kick time/angle, scored on the worst case over drag CdA × 0.5…2 (Kerbal X CdA unknown; 5 m²).
- Chosen: vertical to 4 s, kick 12° (ramped over 4 s), gravity turn along the air-relative velocity, cutoff when the
  apoapsis reaches 80 km, coast, circularise at apoapsis.
- TM-6's closed-loop terminal guidance was tried first and rejected (gap G1).

## Prediction vs KSP
| Quantity | Planner | KSP |
|---|---|---|
| booster pair 1 / 2 / 3 burnout | 13.3 / 29.0 / 48.1 s | ≈ 13 / 30 / 49 s (staging log) |
| cutoff | 99.7 s, 36.4 km | 91.5 s, 35.0 km, 1 224 m/s, 54.49 t |
| max Q | 34.4 kPa at 6.6 km | 37.0 kPa at 8.6 km |
| circularisation Δv | 935 m/s | PAD 1 204 m/s (from the real cutoff state) |
| burn time | — | PAD 36.1 s, flown 37.9 s (last 0.5 s throttled down) |
| parking orbit | 80 × 80 km | 80.24 × 78.22 km, e 0.0015, i 0.19° |
| Δv left (vac) | 3 414 m/s (worst 3 325) | ≈ 3 370 m/s (from the mass, 36.67 t) |

The split between ascent and circularisation differs (earlier cutoff in KSP, hence a slower apoapsis and a bigger
circularisation), but the total matches within ~1.5 %. Pass (criterion: Δv ±5 %).

## Notes
- Attitude error at ignition 0.29°.
- kRPC quirk: the surface-velocity reference frame is singular at rest (drag read in the body frame instead).
- kRPC 0.7: `AutoPilot.engage()` is gone; `engaged` is a property.
