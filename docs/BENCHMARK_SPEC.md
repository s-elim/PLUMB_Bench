# PLUMB-Bench Specification

This document specifies the tasks, success checks, distribution shifts, mid-execution events, evaluation protocol,
and data format of **PLUMB-Bench**, as described in the paper and implemented in `afford_pro` (MuJoCo 3.5.0). Every
reference number below is taken from the evidence files in `docs/roadmap/evidence/`.

## 1. Task and environment

A task is a tuple κ = (ℓ, e, G, ≺) of an instruction ℓ, an environment e = (W, O, ρ₀, Φ), goals G = (g₁, …, g_k),
and a partial order ≺ on the goals. The environment consists of a workcell W, the objects and mechanisms O, an
initial-state distribution ρ₀, and the sliding friction and masses Φ of the moved objects. Each task defines an MDP
on a simulated Franka Panda.

| Item | Specification |
| :--- | :--- |
| Action | (Δp, Δθ, a_grip) ∈ [−1, 1]⁷: a TCP increment of at most 2.5 cm per step, tracked at 20 Hz by damped-least-squares IK with gravity-compensated joint servos; a yaw increment with the hand pointing down; a per-finger opening of a force-limited parallel jaw (about 35 N per finger) |
| Observations | workcell RGB (640×660), wrist RGB (300×420), optional metric depth, proprioception; a privileged low-dimensional view adds the poses of the moved bodies |
| Dynamics | deterministic; randomness enters only through ρ₀ and the perturbation sampler, both seeded per episode |
| Reward | sparse |
| Step budget | H = 400 + 250 (k − 1), i.e. 400–1,650 steps |
| API | `afford_pro.make(task_id)`; Gymnasium-style `reset(seed=...)` and `step(action)`; `env.language_instruction` |

## 2. Goal predicates and success

Each goal is a predicate on the simulator state.

| Predicate | Holds when |
| :--- | :--- |
| `On(b, t)` | body b is released (no finger contact), supported by a non-robot body, at rest (‖v‖ < 0.02 m/s, ‖ω‖ < 0.2 rad/s), tilted at most ε_θ, has been lifted at least 2 cm, and rests within ε_xy of its goal pose at target t: a named point (a bore, a slot, a rack hole), a region (a bin, a marked square) that the footprint of b must lie inside, or another body (stacking) |
| `Pressed(u)` | latching button u is past its latch depth |
| `Closed(s)` | drawer or vise jaw s is within 4 mm of its end |
| `Slid(b, t)` | body b was moved to t without being lifted more than 1 cm (wiping) |
| `HeldOver(b, t, c)` | grasped body b is held with clearance c above t |
| `GripperAbove`, `Touching` | a hover or a touch held for consecutive steps |
| `Lifted(b, h)` | grasped body b is raised by h |

**Ordering.** A goal counts as reached only when it becomes true after every goal ordered before it, so a button
pressed too early or a part already in place does not count. A goal that is only a waypoint (a mug brewed on the drip
tray before it is served) must be reached but need not hold at the end. An episode succeeds at the first step at which
every goal has been reached and every non-waypoint goal holds:

J(π; κ) = Pr over s₀ ~ ρ₀ and τ ~ π of [ there is t ≤ H with s_t ⊨ g₁ ∧ … ∧ g_k in order ].

## 3. Attainable goals and tolerances

Goal poses are not specified by hand. When a task is built, every goal body is lowered into its target and simulated
to rest; the settled pose becomes the goal pose, and a pose that drifts more than 5 mm while settling rejects the
task. There is no attachment, snapping, or teleport, so a body that slides, tips, or binds on a rim fails exactly as
it would physically.

| Goal type | (ε_xy, ε_θ) |
| :--- | :--- |
| point and stacking targets on precision workcells (jig, electronics, laboratory) | 2 mm, 5° |
| point and stacking targets on the other workcells | 8 mm, 15° |
| two loose fits (a bearing ring over a shaft, a centrifuge lid) | 6 mm |
| region targets | the room left for the footprint inside the region |

A static check verifies, before any simulation, that every name in every goal and start exists in its workcell and
that every ordering refers to existing goals. Starts are rejection-sampled: moved objects rest apart and flat in their
start regions with no fixture overhead and a collision-free top-down grasp, and no goal without predecessors may hold
at reset.

## 4. Task set

210 tasks in seven domains of 30, over six workcells (an assembly jig with a vise and a parts pallet, an electronics
bench, a burger station with a grill, an espresso station, a sorting table with bins and a drawer, and a laboratory
bench with racks, a centrifuge, and a pipette), with 27 object types, 6 latching buttons, a drawer, and a vise jaw.

| Domain | Workcells | Goal predicates | Goals per task | Tolerance (mm / °) |
| :--- | :--- | :--- | :-: | :-: |
| D1 Industrial | assembly jig, electronics | On, Pressed, Closed, Lifted, GripperAbove | 1 | 2 / 5 |
| D2 Culinary | burger, espresso | On, Pressed, Slid, Touching | 1 | 8 / 15 |
| D3 Domestic | sorting table | On, Closed, Slid, Touching | 1–2 | 8 / 15 |
| D4 Laboratory | laboratory bench | On, HeldOver, Touching, Pressed, Lifted, GripperAbove, Slid | 1 | 2 / 5 |
| D5 Long-horizon | five workcells | On, Pressed, HeldOver, Slid, Closed | 2–5 | 2–8 / 5–15 |
| D6 Precision chain | jig, electronics, lab | On, Pressed, HeldOver, GripperAbove, Closed, Touching | 2–4 | 2 / 5 |
| D7 Service chain | burger, espresso, sorting | On, Pressed, Closed, Slid | 2–6 | 8 / 15 |

- **343 goals**: On 262, Pressed 29, HeldOver 11, Slid 11, Closed 11, Touching 10, GripperAbove 6, Lifted 3.
- **Goals per task**: 1 goal: 119 tasks; 2: 58; 3: 27; 4: 4; 5: 1; 6: 1.
- **Placement goals**: 134 point or stacking targets (69 at 2 mm, 14 at 6 mm, 51 at 8 mm) and 128 region targets.
- Every instruction comes with step-by-step variants derived from its goals.

## 5. Static distribution shift

Suites are paired on seeds, so a change in success measures the shift rather than a new scene. Every shifted
parameter is restored before the next sample.

| Level | `--suites` name | Parameters |
| :--- | :--- | :--- |
| L1 Nominal | `nominal` | each moved object starts uniformly in its own region (half-widths 2–40 mm, yaw up to ±10°–±45°), in one of two receptacles, or pre-assembled; the initial TCP is jittered by ±1.5 cm per horizontal axis |
| L2 Spatial | `p2_spatial` | region starts move by a radius U(7, 12) cm in a random direction, outside the L1 support, with yaw magnitude U(45°, 90°) |
| L3 Visual | `p3_visual` | light intensities scaled by U(0.5, 1.5) and light positions jittered by ±0.5 m |
| Color | `p1_object` | colors of the moved objects scaled by ±25% |
| L4 Physical | `p4_physical` | sliding friction μ ~ U(0.12, 0.25) on every moved object and both finger pads; mass and rotational inertia scaled by U(1.8, 2.5); layout and appearance unchanged |
| L5 Compound | `combined_ood` | L2, L3, L4, and color shifts sampled jointly |

**Pairing.** A seed gives the identical start layout in L1, L3, and Color, and in L4 for 98.7% of seeds; L5 matches
L2 within 1 mm for 97.0% (changed friction and mass occasionally make the physical start check redraw a start).

**Contact model.** Finger pads use stiff contacts with torsional friction and elliptic friction cones, and collisions
use MuJoCo's native convex collision with multi-point contact.

## 6. Matched mid-execution events

An event case pairs a **Base** rollout with a **Dynamic** rollout that share the task, seed, initial state, and
executed action prefix and differ by one event (following LIBERO-MAX).

- **Event body**: the first moved body that starts free in a region.
- **Trigger t\***: the first step at which the hand arrives above the event body (within 3 cm horizontally and 15 cm
  above it, not yet grasped) in the Base rollout.
- **Event**: the Dynamic rollout replays the Base actions up to t\*, displaces the body by 3 cm along +x, −x, +y, or
  −y at rest, and hands control back to the policy.
- **Validity**: the body must land on a support within 3 mm of the height of its original one and penetrate nothing
  by more than 1 mm.
- **Outcomes**: preserved success (1, 1), regression (1, 0), recovery (0, 1), persistent failure (0, 0).
- **Metrics**: the paired change ΔSR = SR_Dynamic − SR_Base and the conditional regression rate
  CRR = n₁₀ / (n₁₁ + n₁₀).

The reference set has **921 matched pairs on 154 tasks** (every task with a free-standing event body; 2 seeds and up
to 4 directions per task). It is produced by `scripts/diagnostic_probes.py events`.

## 7. Evaluation protocol

- **Training data**: 50 oracle demonstrations per task.
- **Evaluation**: 50 episodes per task and condition, plus the 921 event pairs.
- **Seeds**: evaluation episode seeds are `seed_base + 1000 · task_number + j` (j < episodes, default
  `seed_base` 200,000); generation seeds are `42 + 1000 · task_number + k` (k < 400). Within each task the two are
  disjoint, and the same seeds are used in every suite.
- **Metrics**: success rate with 95% task-bootstrap intervals (Wilson intervals are also reported), goal completion
  (the fraction of a task's goals reached), the physical robustness index PRI = SR(shifted) / SR(L1), ΔSR and CRR for
  events, and the peak contact force on the robot as logged telemetry. Contact force is not part of success.
- **Tool**: `scripts/evaluate_policy_suite.py` (`--checkpoint` for a trained policy, `--policy oracle|random|null`
  for the references) writes `episodes.csv`, `summary.json`, and provenance including the checkpoint hash.

## 8. Reference ceilings and floors

A single privileged closed-loop oracle solves all 210 tasks through the same controller and action space as a learned
policy. It reads poses that policies do not observe, so its success bounds solvability rather than predicting learned
performance.

| Condition | Oracle success (%) | Random | Null |
| :--- | :-: | :-: | :-: |
| L1 Nominal | 99.9 [99.7, 100.0] | 0 / 630 | 0 / 210 |
| L3 Visual | 99.9 [99.7, 100.0] | 0 / 630 | 0 / 210 |
| Color | 99.9 [99.7, 100.0] | 0 / 630 | 0 / 210 |
| L4 Physical | 98.9 [98.1, 99.5] | 0 / 630 | 0 / 210 |
| L2 Spatial | 97.7 [96.4, 98.9] | 0 / 630 | 0 / 210 |
| L5 Compound | 95.6 [94.0, 97.1] | 0 / 630 | 0 / 210 |

5 oracle episodes per task and condition (6,300 in total); every domain is at 89.3% or above in every condition.
On the 921 event pairs the oracle has a Dynamic success rate of 97.5% (CRR 2.4%).

## 9. Data format

The oracle generates demonstrations in robomimic HDF5 with both cameras, proprioception, the full simulator state at
every step, the instruction, and provenance (code version, simulator version, command, attempted and rejected seeds).
Files are written atomically and validated episode by episode (`scripts/validate_datasets.py`); replaying the recorded
actions of sampled demonstrations reproduces their recorded states exactly. `scripts/convert_to_rlds.py` and
`scripts/convert_to_lerobot.py` export RLDS and LeRobot datasets.

## 10. Not part of the benchmark

- The earlier single-body task set (`task_set="legacy"`) is deprecated and kept only to read and replay its files.
- `benchmark/manifests/`, `benchmark/lite/`, `afford_pro/dynamic_suite.py`, and `scripts/evaluate_paired_dynamic.py`
  belong to that task set. The event protocol of Sec. 6 is implemented in `scripts/diagnostic_probes.py events`.
- The earlier "compliant dynamic success" score (a 150 N contact-force limit and actuator torque limits) is not used;
  contact force is reported only as telemetry (Sec. 7).
