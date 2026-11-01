"""Diagnostic probes of the AFFORD-Bench tasks with the privileged oracle (benchmark analysis, Sec. VI of the paper).

Probes over all 210 tasks, with seed blocks disjoint from data generation, task validation and evaluation (the
blocks of different probes may share seed values only on different tasks):

replay        Open-loop replay of a nominal oracle episode (the trajectory a perfect memorizer would reproduce). On the
              same seed: nominal (exact reproduction) and the physical suite (same layout, friction and mass changed).
              On another seed of the same task: nominal (new layout within the nominal start distribution) and the
              spatial suite. The closed-loop oracle runs on the same seeds and suites as the paired ceiling.
localization  The oracle's estimate of every placement goal is offset horizontally by eps (direction fixed per episode
              and goal, the same at every eps, layouts paired across eps): success against goal-localization error.
events        Matched Base/Dynamic pairs. The Dynamic arm replays the Base arm's executed actions exactly up to the step
              at which the hand first arrives above the event body (the first body the task moves that starts free in
              a region), which is then displaced 3 cm (+x, -x, +y, -y) onto the support there, at rest; the
              closed-loop oracle or the open-loop continuation of the Base actions finishes the episode within the
              task's step budget. A null event (same prefix, fresh oracle, no displacement) isolates the restart.
pairing       Start-layout equality across the suites that share layouts (L1, Color, L3, L4; L2, L5).

Every rollout logs the peak net contact force that the scene exerts on the robot (all contacts, held bodies included)
and the peak arm servo torque relative to the Panda joint limits.

    python -I scripts/diagnostic_probes.py replay --workers 20 --out docs/roadmap/evidence/probe_replay_<date>.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Callable

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPLAY_BLOCK = 1_100_000   # seeds: BLOCK + 1000 * task_number + j (layout A) and + 500 + j (layout B)
LOC_BLOCK = 1_200_000
EVENT_BLOCK = 1_300_000
OTHER_LAYOUT = 500

LOC_ERRORS_MM = (0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0)
EVENT_SHIFT = 0.03                      # m
EVENT_DIRECTIONS = {"+x": (1.0, 0.0), "-x": (-1.0, 0.0), "+y": (0.0, 1.0), "-y": (0.0, -1.0)}
TRIGGER_XY = 0.03                       # hand within this horizontal distance of the event body (m) ...
TRIGGER_DZ = 0.15                       # ... and at most this far above its origin, body not yet held
MAX_SUPPORT_CHANGE = 0.003              # a displaced body must land on a surface within this height of its old one (m)
MAX_PENETRATION = 0.001                 # and must not penetrate anything by more than this (m)
TABLE_MARGIN = 0.02
TAU_MAX = np.array([87.0, 87.0, 87.0, 87.0, 12.0, 12.0, 12.0])  # Panda joint torque limits (N m)


# ----------------------------------------------------------------------------- Telemetry
class Telemetry:
    """Peak net contact force on the robot and peak servo torque ratio, sampled after every control step."""

    def __init__(self, env: Any):
        self.env = env
        self.clear()
        original = env._after_step

        def hooked() -> None:
            original()
            self._sample()

        env._after_step = hooked  # instance attribute shadows the class hook; physics is untouched

    def clear(self) -> None:
        self.peak_force = 0.0
        self.peak_tau_ratio = 0.0

    def _sample(self) -> None:
        self.peak_force = max(self.peak_force, self.env.robot_scene_force(set()))
        ratio = float(np.max(np.abs(self.env.actuator_torques) / TAU_MAX))
        self.peak_tau_ratio = max(self.peak_tau_ratio, ratio)

    def record(self) -> dict[str, float]:
        return {"peak_force_n": round(self.peak_force, 2), "peak_tau_ratio": round(self.peak_tau_ratio, 4)}


# ----------------------------------------------------------------------------- Rollout helpers
def _env(spec: Any, suite: str, biased: bool = False) -> Any:
    from afford_pro.bench.env import GoalFrankaEnv

    cls = _biased_env_class() if biased else GoalFrankaEnv
    return cls(spec, perturbation_mode=suite)


_BIASED: list[type] = []


def _biased_env_class() -> type:
    """GoalFrankaEnv whose placement goal, as the oracle reads it (`goal_position`), is offset by `goal_bias`."""
    if not _BIASED:
        from afford_pro.bench.env import GoalFrankaEnv

        class BiasedGoalEnv(GoalFrankaEnv):
            goal_bias: dict[int, np.ndarray] = {}

            @property
            def goal_position(self) -> np.ndarray:  # read only by the oracle's placement routine
                pos = super().goal_position
                bias = self.goal_bias.get(self.focused_goal)
                return pos if bias is None else pos + bias

        _BIASED.append(BiasedGoalEnv)
    return _BIASED[0]


def _oracle_episode(env: Any, tel: Telemetry, seed: int) -> tuple[list[np.ndarray], dict]:
    from afford_pro.bench.oracle import GoalOracle

    tel.clear()
    actions, _, _, dones = GoalOracle(env).generate_episode(seed=seed)
    success = bool(dones and dones[-1]) and len(actions) <= env.max_episode_steps
    return actions, {"success": success, "steps": len(actions), **_progress(env), **tel.record()}


def _progress(env: Any) -> dict:
    return {"goals_reached": len(env.first_true), "goals": len(env.task_spec.goals)}


def _hold_action(actions: list[np.ndarray]) -> np.ndarray:
    hold = np.zeros(7, dtype=np.float32)
    hold[6] = actions[-1][6] if actions else 1.0
    return hold


def _replay(env: Any, tel: Telemetry, seed: int, actions: list[np.ndarray], start: int = 0,
            reset: bool = True) -> dict:
    """From the current step (0 after a reset, or the step a replayed prefix reached), execute the recorded action of
    that step open loop, then hold still with the last gripper command, until success or the step budget."""
    if reset:
        env.reset(seed=seed)
        tel.clear()
    budget = env.max_episode_steps
    hold = _hold_action(actions)
    step = env.current_step
    while step < budget:
        action = actions[step] if start <= step < len(actions) else hold
        _, _, terminated, _, _ = env.step(action)
        step = env.current_step
        if terminated:
            return {"success": True, "steps": step, **_progress(env), **tel.record()}
    return {"success": False, "steps": step, **_progress(env), **tel.record()}


def _domain(number: int) -> str:
    return f"D{(number - 1) // 30 + 1}"


def _tolerances(env: Any) -> list[float]:
    from afford_pro.bench.spec import On

    return [round(float(env.on_tolerances(g)[0]) * 1e3, 2) for g in env.task_spec.goals if isinstance(g, On)]


def _task(number: int) -> Any:
    from afford_pro.bench.tasks import TASK_BY_NUMBER

    return TASK_BY_NUMBER[number]


def _run_task(number: int, body: Callable[[Any, dict], None]) -> dict:
    from afford_pro.envs.headless import headless

    spec = _task(number)
    row: dict = {"number": number, "task_id": spec.task_id, "domain": _domain(number), "goals": len(spec.goals)}
    t0 = time.time()
    try:
        with headless():
            body(spec, row)
    except Exception as exc:  # a crash is recorded per task, not hidden and not fatal to the run
        row["error"] = f"{type(exc).__name__}: {exc}"
    row["seconds"] = round(time.time() - t0, 1)
    return row


# ----------------------------------------------------------------------------- Probe: replay
def replay_task(args: tuple[int, int]) -> dict:
    number, pairs = args

    def body(spec: Any, row: dict) -> None:
        envs = {s: _env(spec, s) for s in ("nominal", "p4_physical", "p2_spatial")}
        tels = {s: Telemetry(e) for s, e in envs.items()}
        row["budget"] = envs["nominal"].max_episode_steps
        row["tol_mm"] = _tolerances(envs["nominal"])
        pairs_out = []
        for j in range(pairs):
            seed_a = REPLAY_BLOCK + 1000 * number + j
            seed_b = seed_a + OTHER_LAYOUT
            actions, source = _oracle_episode(envs["nominal"], tels["nominal"], seed_a)
            rec: dict = {"seed_a": seed_a, "seed_b": seed_b, "source": source}
            if source["success"]:
                rec["replay"] = {
                    "same_nominal": _replay(envs["nominal"], tels["nominal"], seed_a, actions),
                    "same_physical": _replay(envs["p4_physical"], tels["p4_physical"], seed_a, actions),
                    "other_nominal": _replay(envs["nominal"], tels["nominal"], seed_b, actions),
                    "other_spatial": _replay(envs["p2_spatial"], tels["p2_spatial"], seed_b, actions),
                }
                rec["oracle"] = {
                    "same_physical": _oracle_episode(envs["p4_physical"], tels["p4_physical"], seed_a)[1],
                    "other_nominal": _oracle_episode(envs["nominal"], tels["nominal"], seed_b)[1],
                    "other_spatial": _oracle_episode(envs["p2_spatial"], tels["p2_spatial"], seed_b)[1],
                }
            pairs_out.append(rec)
        row["pairs"] = pairs_out
        for e in envs.values():
            e.close()

    return _run_task(number, body)


# ----------------------------------------------------------------------------- Probe: localization error
def localization_task(args: tuple[int, int]) -> dict:
    number, episodes = args
    from afford_pro.bench.spec import On

    def body(spec: Any, row: dict) -> None:
        on_goals = [i for i, g in enumerate(spec.goals) if isinstance(g, On)]
        row["on_goals"] = len(on_goals)
        if not on_goals:
            return
        env = _env(spec, "nominal", biased=True)
        tel = Telemetry(env)
        row["tol_mm"] = _tolerances(env)
        out = []
        for j in range(episodes):
            seed = LOC_BLOCK + 1000 * number + j
            rng = np.random.default_rng([LOC_BLOCK, number, j])
            angles = {i: float(rng.uniform(0.0, 2.0 * np.pi)) for i in on_goals}
            for eps_mm in LOC_ERRORS_MM:
                eps = eps_mm * 1e-3
                env.goal_bias = {i: np.array([eps * np.cos(a), eps * np.sin(a), 0.0]) for i, a in angles.items()}
                _, result = _oracle_episode(env, tel, seed)
                out.append({"seed": seed, "eps_mm": eps_mm, **result})
        env.goal_bias = {}
        row["episodes"] = out
        env.close()

    return _run_task(number, body)


# ----------------------------------------------------------------------------- Probe: mid-execution events
def _event_body(env: Any) -> str | None:
    from afford_pro.bench.spec import Region

    for body in env.task_spec.bodies_moved():
        if isinstance(env.start_of(body), Region):
            return body
    return None


def _trigger_reached(env: Any, body: str) -> bool:
    bid = env.body_ids[body]
    pos, tcp = env.data.xpos[bid], env.tcp_position
    return bool(np.linalg.norm(tcp[:2] - pos[:2]) <= TRIGGER_XY and 0.0 < tcp[2] - pos[2] <= TRIGGER_DZ
                and not env.is_grasped(bid))


def _displace(env: Any, body: str, direction: tuple[float, float]) -> str | None:
    """Move `body` EVENT_SHIFT along `direction` at rest; None if valid, else the reason (state restored)."""
    import mujoco
    from afford_pro.bench.env import TABLE_X, TABLE_Y

    m, d = env.model, env.data
    adr = env.body_qposadr[body]
    dof = env.free_qpos_to_dof[adr]
    saved_qpos, saved_qvel = d.qpos.copy(), d.qvel.copy()
    old = d.qpos[adr:adr + 3].copy()
    new = old + EVENT_SHIFT * np.array([direction[0], direction[1], 0.0])
    if not (TABLE_X[0] + TABLE_MARGIN <= new[0] <= TABLE_X[1] - TABLE_MARGIN
            and TABLE_Y[0] + TABLE_MARGIN <= new[1] <= TABLE_Y[1] - TABLE_MARGIN):
        return "off table"
    focused = env.object_name
    env.focus(body)  # the support rays pass through the focused body
    try:
        above = env.body_bottom(body) + 0.05
        support_old = env.ray_vertical(np.array([old[0], old[1], above]))
        support_new = env.ray_vertical(np.array([new[0], new[1], above]))
    finally:
        env.focus(focused)
    if support_old is None or support_new is None or abs(support_new - support_old) > MAX_SUPPORT_CHANGE:
        return "support changes"
    new[2] = old[2] + (support_new - support_old)  # same clearance above the new support: no drop, no push-up
    d.qpos[adr:adr + 3] = new
    d.qvel[dof:dof + 6] = 0.0
    mujoco.mj_forward(m, d)
    bid = env.body_ids[body]
    for i in range(d.ncon):
        c = d.contact[i]
        if bid in (int(m.geom_bodyid[c.geom1]), int(m.geom_bodyid[c.geom2])) and c.dist < -MAX_PENETRATION:
            d.qpos[:], d.qvel[:] = saved_qpos, saved_qvel
            mujoco.mj_forward(m, d)
            return "penetration"
    return None


def _prefix(env: Any, seed: int, actions: list[np.ndarray], t_star: int) -> None:
    env.reset(seed=seed)
    for a in actions[:t_star]:
        env.step(a)


def events_task(args: tuple[int, int]) -> dict:
    number, seeds = args

    def body(spec: Any, row: dict) -> None:
        from afford_pro.bench.oracle import GoalOracle

        env = _env(spec, "nominal")
        tel = Telemetry(env)
        row["budget"] = env.max_episode_steps
        row["tol_mm"] = _tolerances(env)
        event_body = _event_body(env)
        row["event_body"] = event_body
        if event_body is None:
            env.close()
            return
        cases = []
        for j in range(seeds):
            seed = EVENT_BLOCK + 1000 * number + j
            tel.clear()
            env.reset(seed=seed)
            oracle = GoalOracle(env)
            # Base arm, recording the first step at which the hand arrives above the event body.
            t_star: list[int] = []
            holding: list[bool] = []
            original = env._after_step

            def watch() -> None:
                original()
                if not t_star and _trigger_reached(env, event_body):
                    t_star.append(env.current_step)
                    holding.append(any(env.is_grasped(b) for b in env.body_ids.values()))

            env._after_step = watch
            try:
                actions, _, _, dones = oracle.generate_episode(seed=seed, reset=False)
            finally:
                env._after_step = original
            base = {"success": bool(dones and dones[-1]), "steps": len(actions), **_progress(env), **tel.record()}
            case: dict = {"seed": seed, "base": base}
            if not t_star:
                case["skip"] = "trigger not reached"
                cases.append(case)
                continue
            ts = t_star[0]
            case["t_star"] = ts
            case["holding_at_trigger"] = holding[0]
            # The Base oracle's own simulator state after ts actions (states are recorded before each action).
            oracle_state = oracle.last_states[ts] if ts < len(actions) else oracle.last_final_state
            # Open-loop Base arm: the recorded actions from reset (exact reproduction of the oracle's Base arm).
            case["base_replay"] = _replay(env, tel, seed, actions)
            _prefix(env, seed, actions, ts)
            base_state_at = env.get_sim_state()
            case["prefix_matches_base"] = bool(np.array_equal(base_state_at, oracle_state))
            # Null event: the same prefix and a fresh oracle, without a displacement (isolates the restart).
            tel.clear()
            _prefix(env, seed, actions, ts)
            restart = GoalOracle(env)
            restart.max_steps = env.max_episode_steps - ts
            more0, _, _, done0 = restart.generate_episode(seed=seed, reset=False)
            case["null_restart"] = {"success": bool(done0 and done0[-1]) and ts + len(more0) <= env.max_episode_steps,
                                    "steps": ts + len(more0), **_progress(env), **tel.record()}
            arms = {}
            for name, direction in EVENT_DIRECTIONS.items():
                # Dynamic arm: exact prefix, event, then each continuation (telemetry over the whole episode).
                tel.clear()
                _prefix(env, seed, actions, ts)
                prefix_exact = bool(np.array_equal(env.get_sim_state(), base_state_at))
                reason = _displace(env, event_body, direction)
                if reason is not None:
                    arms[name] = {"invalid": reason}
                    continue
                follow = GoalOracle(env)
                follow.max_steps = env.max_episode_steps - ts
                more, _, _, done2 = follow.generate_episode(seed=seed, reset=False)
                oracle_dyn = {"success": bool(done2 and done2[-1]) and ts + len(more) <= env.max_episode_steps,
                              "steps": ts + len(more), **_progress(env), **tel.record()}
                tel.clear()
                _prefix(env, seed, actions, ts)
                _displace(env, event_body, direction)
                replay_dyn = _replay(env, tel, seed, actions, start=ts, reset=False)
                arms[name] = {"prefix_exact": prefix_exact, "oracle": oracle_dyn, "replay": replay_dyn}
            case["arms"] = arms
            cases.append(case)
        row["cases"] = cases
        env.close()

    return _run_task(number, body)


# ----------------------------------------------------------------------------- Probe: layout pairing
PAIRED_WITH = {"p1_object": "nominal", "p3_visual": "nominal", "p4_physical": "nominal", "combined_ood": "p2_spatial"}


def pairing_task(args: tuple[int, int]) -> dict:
    """Whether a seed gives the same start layout across suites that claim to share it (L1/Color/L3/L4, L2/L5): the
    largest horizontal start difference of the moved bodies, on the replay probe's layout-A seeds."""
    number, seeds = args

    def body(spec: Any, row: dict) -> None:
        suites = ("nominal", "p2_spatial", *PAIRED_WITH)
        envs = {s: _env(spec, s) for s in suites}
        moved = spec.bodies_moved()
        out = []
        for j in range(seeds):
            seed = REPLAY_BLOCK + 1000 * number + j
            starts, fallback = {}, {}
            for s, e in envs.items():
                e.reset(seed=seed)
                starts[s] = {b: e.data.xpos[e.body_ids[b]][:2].copy() for b in moved}
                fallback[s] = bool(e.start_fallback)
            dev = {s: round(1e3 * max((float(np.linalg.norm(starts[s][b] - starts[ref][b])) for b in moved),
                                      default=0.0), 3) for s, ref in PAIRED_WITH.items()}
            out.append({"seed": seed, "max_dev_mm": dev, "fallback": fallback})
        row["seeds"] = out
        for e in envs.values():
            e.close()

    return _run_task(number, body)


# ----------------------------------------------------------------------------- Driver
PROBES = {"replay": (replay_task, 3), "localization": (localization_task, 2), "events": (events_task, 2),
          "pairing": (pairing_task, 3)}


def _numbers(selection: str) -> list[int]:
    if selection == "all":
        return list(range(1, 211))
    out: list[int] = []
    for token in selection.split(","):
        if "-" in token:
            lo, hi = token.split("-")
            out += list(range(int(lo), int(hi) + 1))
        else:
            out.append(int(token))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("probe", choices=sorted(PROBES))
    parser.add_argument("--tasks", default="all", help="all, or comma-separated numbers and ranges (1-30)")
    parser.add_argument("--n", type=int, default=None, help="pairs (replay), episodes per error (localization) or "
                                                              "seeds (events) per task")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    worker, default_n = PROBES[args.probe]
    n = default_n if args.n is None else args.n
    if not 0 < n <= 100:
        parser.error("--n must be in 1..100")
    numbers = _numbers(args.tasks)
    rows = []
    t0 = time.time()
    with Pool(args.workers) as pool:
        for row in pool.imap_unordered(worker, [(k, n) for k in numbers]):
            rows.append(row)
            print(f"#{row['number']:03d} {row['task_id']:42s} {row.get('error', 'ok')} ({row['seconds']}s)", flush=True)
    rows.sort(key=lambda r: r["number"])
    from afford_pro.provenance import collect_provenance

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"probe": args.probe, "n": n, "seconds": round(time.time() - t0, 1),
                                    "provenance": collect_provenance(), "tasks": rows}, indent=1, default=str),
                        encoding="utf-8")
    print(f"{args.probe}: {len(rows)} tasks, errors {sum('error' in r for r in rows)}; wrote {args.out}")


if __name__ == "__main__":
    main()
