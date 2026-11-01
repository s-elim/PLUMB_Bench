# Experiment log

Each entry: command, configuration, versions, seeds, outcome, compute. An entry is marked successful only when its
output was inspected against its success criterion. Environment unless stated: Windows 11, Ryzen 9 3900X, Python
3.13.5, MuJoCo 3.5.0, numpy 2.2.6, h5py 3.12.1, torch 2.10.0+cpu; checkout `main` @ `cba995e` + uncommitted changes
(dirty tree; the provenance sidecars list the modified files and their hashes).

## E-001 Baseline unit tests (2026-10-17)
- Command: `python -m pytest -q tests -p no:cacheprovider`
- Outcome: 1722 passed in 120 s. Success criterion (all pass): met.

## E-002 Dataset low-dim scan, all 210 nominal files (2026-10-17)
- Commands: scratch scripts `explore_ds.py` (4 files, full low-dim per episode) and `seedscan.py` (all files: seeds,
  lengths, alias storage, model_file). Read-only. About 5 min.
- Outcome: 210 files, all registered task ids, 50 demos each (10,500). Seed schemes: 202 files `42+1000n+k`, 7 files
  `42+100n+k`, 1 file `42+k`. Inferred attempts 11,097, failures 597 (94.6% oracle success during generation; per
  domain D1 93.6, D2 97.3, D3 98.0, D4 90.6, D5 96.2, D6 90.4, D7 97.0%; worst `lab_micro_tube_to_rack_b` 50/164).
  130 demos > 400 steps, 114 > 500 steps. 6 files store aliases as copies, 204 as hard links. All model_file
  attributes contain `impratio` (generated after the 2026-10-16 XML change). In the 4 fully scanned files: unique
  seeds and initial states, `init_state == states[0]` for all demos, rewards and dones 0 then 1 at the last step,
  actions finite in [-1, 1], instruction variants rotate 13/13/12/12.
- Caveat: attempts are inferred from seed gaps; the generator does not record failures.

## E-003 Sanity-harness timing (2026-10-17)
- Command: `python scripts/sanity_baselines.py --tasks industrial_shaft_assembly,kitchen_press_brew_button,chain_burger_flip_cheese_top`
- Outcome: 77 s for 3 tasks (about 26 s per task with 5+5 oracle, 5 random, 1 null episodes). Oracle nominal 5/5, 5/5,
  4/5; L4 4/5, 5/5, 5/5; random and null 0. Used only for cost estimation.

## E-004 Sanity floors on the current physics, all 210 tasks (2026-10-17, done)
- Command: 8 shards of `python -I scripts/sanity_baselines.py --shard i/8 --oracle-episodes 5 --episodes 5 --horizon 400 --seed 10000 --out docs/roadmap/evidence/sanity_2026-10-17/part_i.csv --episodes-out .../episodes_i.csv`;
  aggregation `python scripts/aggregate_sanity.py --dir docs/roadmap/evidence/sanity_2026-10-17`.
- Seeds: reset seeds 10000 to 10004 per task (disjoint from all generation seed schemes found in E-002).
- Compute: about 15 min wall clock, 8 processes.
- Outcome (`summary.md`, `summary.json`; intervals are 95% task-clustered bootstrap): oracle nominal 95.3%
  (93.4 to 97.0) within its 600-step budget, 94.6% within H = 400; oracle L4 95.9% (94.4 to 97.3); random 0/1050;
  null 0/210; no task succeeds at reset. Per domain (nominal): D1 95.3, D2 97.3, D3 100, D4 94.0, D5 93.3, D6 92.0,
  D7 95.3. Core tier 95.2 (91.2 to 98.2), reach tier 100. Successful oracle episodes: mean 115.2 steps, median 120.
- Interpretation: contradicts the paper's 99.8% nominal and 47.3% L4 (measured 2026-10-08 on MuJoCo 3.2.7 with
  pyramidal friction cones). Under the current elliptic cones, the L4 perturbation does not reduce oracle success.
- Success criterion (complete run, every shard wrote its CSV, provenance recorded): met.

## E-005 Runtime task audit, all 210 tasks (2026-10-17, done)
- Command: `python -I scripts/audit_tasks.py --resets 10 --workers 4 --out docs/roadmap/evidence/task_audit_2026-10-17.json`
- Seeds: 300000 to 300009 (disjoint from generation and evaluation blocks). About 10 min.
- Outcome: no success at reset; start fallback only in task 12 (always) and 12 tasks at 10 to 30%; hold goals 74,
  93, 160, 172 (74 is a "place" instruction); 29 tasks (14 core by the prompt flags) have start xy std < 1 cm;
  24 of the 78 flag-core tasks place onto an unmarked surface point (table, bench, board, workstation); distractors
  closer than 9 cm to start or goal in 7 of 76 tasks (minimum 3.9 cm, task 29). 12 flag-core tasks re-classified as
  instruction mismatches after reading the audit (`afford_pro/task_tiers.AUDITED_MISMATCHES`): core = 66.

## E-007 Episode-level validation of all 210 datasets with replay (2026-10-17, done)
- Command: `python -I scripts/validate_datasets.py --replay-per-file 3 --workers 8 --out-dir docs/roadmap/evidence/dataset_validation_2026-10-17`
- Scope: every episode of every file (low-dim arrays, terminal semantics, obs/state alignment, next_obs shift,
  duplicates, masks, registry); image shape/dtype for all, content (dark/constant) on the first and last frame of
  every episode; replay of 3 demos per file (first, middle, last). About 1.5 h with 8 workers.
- Outcome (`summary.md`, `report.json`, `manifest.json`): 210 files, 10,500 demos, 1,230,842 steps (mean 117.2);
  0 INVALID, 210 VALID_WITH_WARNINGS. Warnings: no provenance (210 files), terminal next_obs copies obs (all
  10,500 demos), aliases stored as copies (6 files), demos over the 500-step env limit (12 files) and over H = 400
  (20 files). No duplicate initial states or action sequences within or across files.
- Replay: 595/630 demos reach success exactly at their recorded last step; 35 differ (20 succeed 1-32 steps early,
  15 do not succeed by T). Object deviation median 2.3e-5 m, 90th percentile 2.7e-4 m, max 0.085 m (10 > 1 mm).
- Diagnostics (scratch scripts `warmstart_diag.py`, `divergence_diag.py`, `warm_every_step.py`, fresh oracle
  episodes on 4 tasks): replay diverges at the first action by about 1e-9 in free-body velocities; the solver warm
  start before step 0 matches exactly, and imposing the recorded warm start before every step does not remove the
  divergence. Root cause: open (not the warm start).

## E-008 L4 friction x mass sweep on the 66 core tasks (2026-10-17, done)
- Command: `python -I scripts/l4_sweep.py --tier core --mu 0.02,0.05,0.12,0.25 --mass 1.0,2.5,5.0 --seeds 3 --workers 6 --out docs/roadmap/evidence/l4_sweep_2026-10-17.csv`
- Seeds 400000 to 400002. 2,574 oracle episodes, about 25 min.
- Outcome (oracle success %, task-clustered 95% CI): nominal 95.5 (90.4-99.5); mu 0.25: x1 96.0, x2.5 94.4,
  x5 91.9; mu 0.12: 96.0, 91.4, 71.2; mu 0.05: 88.4, 59.6, 36.9; mu 0.02: 51.5, 31.8, 14.1.
- Interpretation: the current L4 range (mu 0.12-0.25, mass x1.8-2.5) lies on the flat part of the curve; the
  physical axis lowers expert success only for mu <= 0.05 or heavy (x5) bodies.

## E-009 Oracle contact-force probe (2026-10-17, done)
- `python -I scripts/force_probe.py --episodes 1 --workers 6 --out docs/roadmap/evidence/force_probe_2026-10-17.csv` (seed 500000).
- Outcome: 203/210 successful; peak robot-scene force median 0 N, 95th percentile 142.6 N, max 163.2 N; 9 of 210
  episodes exceed F_max = 150 N (all D7 kitchen chains).

## E-010 Reactive perturbation probe on the current physics (2026-10-17, done)
- `python -I scripts/test_reactive_perturbation.py --out docs/roadmap/evidence/reactive_perturbation_2026-10-17.csv`
  (defaults: 3 tasks, 3 seeds, T = 60, H = 16, 4 cm displacement).
- Outcome: closed loop 14/18, 16-step chunks 14/18, open-loop replay 0/18. No undisplaced control in this script
  version (the paper's earlier "9 of 9 without displacement" has no current artifact and was removed).

## E-011 Baseline pipeline validation, one task (2026-10-17, done)
- `scripts/train_policy.py --policy {bc,diffusion} --modality lowdim --task tabletop_sort_red --epochs 200 --seed 0`
  then `scripts/evaluate_policy_suite.py --checkpoint ... --episodes 20` (seeds 261000-261019). Checkpoints and
  logs in the session scratchpad (not evidence for the paper's baselines).
- Outcome: BC 16/20 (Wilson 58-92%), best validation L1 loss 0.021; diffusion 0/20, best validation loss 0.088.
  The in-repo diffusion implementation does not learn this task at a budget where BC does; use a reference
  implementation (LeRobot 0.5.1 is installed) before reporting a diffusion baseline.

## E-012 Replay-divergence root cause (2026-10-18)
- Scratch diagnostics `mjdata_diff.py` (diff of every MjData array before the first action, original vs replay) and
  `divergence_diag.py` on fresh oracle episodes of 4 tasks.
- Outcome: before the fix, only uninitialized sparse-index scratch arrays (efc_AR_rowadr, efc_AR_rownnz,
  efc_J_colind) differ, yet the first step diverges by about 1e-9: the executed action was float64 and the recorded
  one float32. After `BaseOracle.act` executes the float32 action, all 4 replays are bit-identical (118, 127, 112,
  104 steps). Regression test `tests/test_replay.py`.

## E-013 Re-measurement after the seed-pairing and float32-action fixes (2026-10-18, done)
- Same commands as E-004, E-008, E-009, with outputs `sanity_2026-10-18/`, `l4_sweep_2026-10-18.csv`,
  `force_probe_2026-10-18.csv`. Supersedes E-004/E-008/E-009 for the paper and the page.
- Sanity: oracle nominal 95.7% (1005/1050, task-bootstrap 93.8-97.4), 94.5% within H = 400, L4 95.0% (93.0-96.8);
  core tier 95.2 / 93.3 / 96.1%; random 0/1050, null 0/210, no success at reset; 28 tasks fail at least once
  (`lab_micro_tube_to_rack_b` 5/5 failures).
- Sweep (core, 3 seeds): >= 94% for mu >= 0.12 up to x2.5; (0.12, x5) 69.7%, (0.05, x5) 38.4%, (0.02, x5) 15.7%.
- Force: median 0 N, p95 142.6 N, max 168.7 N, 10/210 episodes > 150 N (4.8%).

## E-014 End-to-end check of the fixed generation pipeline (2026-10-18)
- `python scripts/generate_demos.py --task tabletop_sort_red --num-demos 3 --output-dir <scratchpad>/newgen` (real
  rendering), then `python scripts/validate_datasets.py --files .../tabletop_sort_red_nominal.hdf5 --replay-per-file 3
  --expected-demos 3`.
- Outcome: status written, 3 demos in 3 attempts, exit 0; validator VALID with no issues (provenance present, final
  observation stored, canonical instructions); all 3 replays exact (object and joint deviation 0.0). The validator now
  treats any replay deviation as an error for files that carry provenance.

## E-015 Reference-policy leaderboard on the 66 core tasks (2026-10-18, done)
- Command: for each domain d in industrial, kitchen, tabletop, lab and policy p in oracle (5 episodes), random (3),
  null (1): `python -I scripts/evaluate_policy_suite.py --policy p --domain d --tier core --suites
  nominal,p1_object,p2_spatial,p3_visual,p4_physical,combined_ood --episodes n --out-dir
  docs/roadmap/evidence/leaderboard_2026-10-18/p_d`; page data rebuilt with `python scripts/build_site_data.py`.
- Seeds: evaluation block 200000 + 1000n + j. Success counts within H = 400 steps. About 2.5 h wall clock.
- Outcome (core, task-bootstrap 95% CI in `data.js`): oracle 93.0 nominal, 93.6 L2, 93.0 L3, 91.8 L4, 90.6 L5,
  93.0 color; per domain nominal: industrial 94.1, kitchen 99.0, tabletop 97.6, lab 75.0 (lab tasks that need more
  than 400 steps or fail, e.g. `lab_micro_tube_to_rack_b`). Random 0/990 and null 0/396 episodes in every suite.
  Nominal, p1 and p3 oracle rates are identical because the oracle reads the true pose and the layouts are paired.

## E-016 Task validation, nominal suite, all 210 tasks (2026-10-19, done)
- Command: `python -I scripts/validate_bench_tasks.py --episodes 10 --resets 20 --floor-episodes 2 --workers 12 --out
  docs/roadmap/evidence/task_validation_2026-10-19_nominal.json`, code at 584cd33 (uncommitted: legacy tools and a
  test, none used by the run). About 50 min, sharing the CPU with E-019.
- Seeds: oracle 600000 + 1000n + j, start audit 700000 + 1000n + j, random/null 800000 + 1000n + j.
- What it checks: every task builds (each goal body dropped into its goal and pre-placed assembly must come to rest),
  20 resets per task (start spread of each moved body, fallbacks to the region center, goals already true at reset),
  10 oracle episodes within the task's step budget, 2 random and 2 null episodes.
- Outcome: oracle 2096/2100 (99.81%); every task >= 9/10 (one failure each in 147, 166, 178, 209); per domain D1-D4
  300/300, D5 299/300, D6 298/300, D7 299/300. Random 0/420, null 0/420. No start fallback and no goal true at reset
  in 4200 resets. Starts: 225 region starts, s.d. over 20 resets >= 0.999 cm (minimum: the gear in task 21);
  31 bodies start pre-placed (assemblies) and 22 in one of two slots, by design.
- Earlier runs of this command (same seeds): 2097/2100 before the second code review, then 2095/2100; the suite
  runs of E-017 exposed defects (A-37 to A-41) that were fixed before the final code. The final code gave the same
  result before and after the package was renamed (2096/2100 both times).
- Development history (scratch runs, not evidence): oracle 88.6% (first pass) -> 94.3 -> 94.9 -> 97.6 -> 99.1 ->
  99.86% after fixes listed in AUDIT_REPORT A-32 to A-35 and T9_TASK_REDESIGN.md.

## E-017 Oracle under the perturbation suites, all 210 tasks (2026-10-19, done)
- Command: `python -I scripts/validate_bench_tasks.py --suite {p4_physical,p2_spatial,combined_ood} --episodes 5
  --resets 3 --workers 12 --out docs/roadmap/evidence/task_validation_2026-10-19_<suite>.json`, code at 584cd33.
  p1 (colour) and p3 (lighting) do not change what the privileged oracle sees, so they equal nominal.
- Outcome (oracle success, the feasibility ceiling of each suite): L4 1038/1050 (98.9%, every task >= 4/5), L2
  1024/1050 (97.5%, >= 2/5), L5 1003/1050 (95.5%, >= 1/5; task 22 is 1/5: the slippery, heavier dowel pin topples).
  No start fallback and no goal true at reset in any suite.
- Failures by cause: the oracle did not achieve a goal (L4 4, L2 20, L5 29); a released body sank into or through
  its support, a contact artifact of thin light parts let go under low friction and higher mass (L4 8, L2 5, L5 17,
  i.e. 0.8%, 0.5%, 1.6% of episodes; A-42); a goal reached then undone (L2 1, L5 1).
- Earlier runs of this command found defects that are now fixed: the oracle swept a seated lid off (A-38), slices
  sank through thin collision layers (A-39), condim 4 between flat bodies destabilised the solver (A-40), and bin
  goals rejected bodies lying in the bin (A-41).

## E-018 Rejected contact-model changes (2026-10-18)
- Replays of failing L5 releases (tasks 124, 190) and A/B runs on nine burger tasks x 10 episodes x {nominal, L5}
  (an A/B script in scratch). Baseline (final physics): nominal 89/90, L5 63/90.
- Default contact time constant 5 ms instead of MuJoCo's 20 ms: fixes the replayed release, but the fingers then
  lose thin slices during the pick (nominal 141/160 on 16 affected tasks). Rejected.
- Easing the hand 1.5 mm up before opening: nominal 79/90, L5 16/90. Rejected.
- impratio 1, pyramidal cones, noslip 10, 500 solver iterations: no effect on the replayed release.

## E-019 Reference-policy leaderboard on all 210 tasks (2026-10-19, done)
- Command: for policy p in oracle (5 episodes), random (3), null (1) and 12 task shards s (task number mod 12):
  `python -I scripts/evaluate_policy_suite.py --policy p --task <shard s> --suites
  nominal,p1_object,p2_spatial,p3_visual,p4_physical,combined_ood --episodes n --out-dir
  docs/roadmap/evidence/leaderboard_2026-10-19/p_s<s>`; all 36 runs at code 584cd33 (no uncommitted code under
  `afford_pro/`). About 70 min, sharing the CPU with E-016/E-017.
- Seeds: evaluation block 200000 + 1000n + j. Success counts within each task's step budget.
- Outcome (task-bootstrap 95% CI in the paper's Table II and `docs/site/data.js`): oracle 99.9 L1, 97.7 L2, 99.9 L3,
  98.9 L4, 95.6 L5, 99.9 color (6,300 episodes); per domain the lowest cell is D7 under L5 (89.3). Random 0/3,780 and
  null 0/1,260 episodes in every suite. L1, L3 and color are equal for the oracle because it reads the true poses and
  the layouts are paired.

## E-006 Generator and validator unit tests (2026-10-17)
- `python -m pytest -q tests/test_dataset_validation.py tests/test_generation.py tests/test_task_registry.py tests/test_dataset_recording.py tests/test_converters.py`
- Outcome: all pass (validator 15, generation 4, registry 638, recording + converters 13).

## E-020 Matched mid-execution events, all 210 tasks (2026-11-01, done)
- Command: `python -I scripts/diagnostic_probes.py events --workers 22 --out docs/roadmap/evidence/probe_events_2026-11-01.json`
  (n = 2 seeds per task), HEAD 0112f5e with the new untracked script `scripts/diagnostic_probes.py`
  (sha256 87634dae...634b). 548 s on 22 workers. Seeds: 1,300,000 + 1000 n + j.
- Protocol (paper Sec. III-F): event body = first moved body whose start is a Region; trigger t* = first Base step with
  the hand within 3 cm horizontally and at most 15 cm above the body, body not grasped; Dynamic arm = exact replay of
  the Base actions to t*, displacement 3 cm along +x/-x/+y/-y with zero velocity, valid only if the support height
  under the new position is within 3 mm of the old one and no contact penetrates more than 1 mm; continuation by the
  closed-loop oracle (budget H - t*) or by the Base actions open loop (then holding still).
- Outcome: 154 of 210 tasks have an event body; all 154 yield valid pairs: 921 pairs (311 directions rejected:
  penetration 269, support change 31, off table 11). Prefix exact (bit-identical simulator state at t*) 921/921;
  median t* = 18 steps. Oracle: (1,1) 898, (1,0) 22, (0,0) 1 -> Dynamic SR 97.5%, CRR 22/920 = 2.4%. Open-loop
  continuation: (1,1) 13, (1,0) 907, (0,0) 1 -> Dynamic SR 1.4%, CRR 907/920 = 98.6%. Base open-loop replay
  reproduced the Base oracle outcome in every case. Per domain, oracle Dynamic SR: D1 124/134, D2 61/62, D3 200/202,
  D4 68/68, D5 140/141, D6 153/161, D7 152/153.
- Note: the existing `afford_pro/dynamic_suite.py` runs on the legacy task set (AUDIT_2026-11-01 A-44) and was not used.

## E-021 Trajectory-replay (memorization) probe, all 210 tasks (2026-11-01, done)
- Command: `python -I scripts/diagnostic_probes.py replay --workers 22 --out docs/roadmap/evidence/probe_replay_2026-11-01.json`
  (n = 3 pairs per task), same code as E-020. 958 s. Seeds: layout A 1,100,000 + 1000 n + j, layout B = A + 500.
- Protocol: a nominal oracle episode on layout A is recorded; its actions are replayed open loop (then holding still to
  the budget) on A nominal, on A under L4 (same layout, friction and mass shifted), on B nominal and on B under L2. The
  closed-loop oracle runs on the same seeds and suites.
- Outcome: oracle source success 629/630 (task 60 failed once). Replay / oracle: same layout L1 629/629 / 629/629
  (exact reproduction); same layout L4 510/629 (81.1%) / 621/629 (98.7%); new layout L1 56/629 (8.9%) / 629/629 (100%);
  new layout L2 43/629 (6.8%) / 611/629 (97.1%). By tolerance tier of the task's tightest placement goal (replay,
  L4 same / L1 new / L2 new): precision <= 2.5 mm (165 pairs) 62.4 / 1.8 / 1.8%; 6-8 mm (156) 84.6 / 2.6 / 1.3%;
  region (206) 85.9 / 7.3 / 4.4%; no placement goal (102) 96.1 / 33.3 / 28.4%. Tasks with a placement goal: new
  layout L1 22/527 (4.2%), L2 14/527 (2.7%). Chains D5/D6/D7 under L4 same layout: 60.0 / 63.3 / 68.9%.
- Telemetry (logged, not a success criterion): peak servo torque reaches the actuator limit in every episode; peak net
  contact force exceeds 150 N in some oracle episodes, largest 1040 N (task 122, a transient). See A-46.

## E-022 Goal-localization error probe, all 210 tasks (2026-11-01, done)
- Command: `python -I scripts/diagnostic_probes.py localization --workers 22 --out docs/roadmap/evidence/probe_localization_2026-11-01.json`
  (n = 2 episodes per task and error), same code as E-020/E-021 (sha256 87634dae...634b). 788 s.
  Seeds: 1,200,000 + 1000 n + j; the same seed at every error level (paired layouts).
- Protocol: the oracle's estimate of every placement goal (`goal_position`, read only by its placement routine) is
  offset horizontally by eps in {0, 1, 2, 3, 4, 6, 8, 12, 16} mm, in a direction drawn per episode and goal
  (rng seeded by task and episode) and kept across eps. Success is the unchanged benchmark check. The oracle keeps its
  closed-loop re-centring and its three placement attempts (retry decided from the true state).
- Outcome: 176 tasks have a placement goal (34 do not). Success by tier of the task's tightest placement goal:
  precision <= 2.5 mm (55 tasks, 110 episodes per eps): 100, 100, 76.4, 50.9, 57.3, 30.0, 15.5, 0, 0% at
  0/1/2/3/4/6/8/12/16 mm; 6-8 mm (52 tasks, 104): 100, 100, 100, 98.1, 97.1, 89.4, 52.9, 0, 0%; region (69 tasks,
  138): 100, 100, 98.6, 99.3, 98.6, 98.6, 97.8, 88.4, 81.2%.

## E-024 Start-layout pairing across suites, all 210 tasks (2026-11-01, done)
- Command: `python -I scripts/diagnostic_probes.py pairing --workers 20 --out docs/roadmap/evidence/probe_pairing_2026-11-01.json`
  (n = 3: the layout-A seeds of E-021), revised script after the code review (adds the pairing and null-event modes).
- Protocol: for each seed, reset the nominal, p1_object (Color), p3_visual, p4_physical, p2_spatial and combined_ood
  environments and compare the horizontal start positions of the moved bodies (L1 vs Color/L3/L4; L2 vs L5).
- Outcome (630 seeds, no start fallback): Color and L3 equal L1 exactly on every seed. L4 equals L1 within 0.1 mm on
  622/630 seeds (98.7%); 8 seeds differ by more than 1 mm (up to 30 mm). L5 equals L2 within 1 mm on 611/630 (97.0%;
  572 within 0.01 mm; up to 190 mm). Cause: the start check settles bodies under the suite's physics, so heavier or
  more slippery bodies are occasionally rejected and a further start is drawn (AUDIT A-51).
- Consequence for E-021: the "same layout, L4" replay condition is reported on the 621 source pairs whose L4 layout
  equals the nominal one: replay 508/621 (81.8%), oracle 615/621 (99.0%); 2 mm tier 103/165 (62.4%), 6-8 mm 132/150
  (88.0%), region 175/204 (85.8%); D5/D6/D7 61.4/63.3/72.1%. (All 629 pairs: 81.1% / 98.7%.)

## E-023 Matched mid-execution events, re-run with controls (2026-11-01, done; supersedes E-020 in the paper)
- Command: as E-020, output `docs/roadmap/evidence/probe_events_2026-11-01_r2.json`, script revised after the code
  review: a null event per case (same prefix, fresh oracle, no displacement), a direct check of the replayed prefix
  against the Base oracle's recorded state at t*, the grasp state at the trigger, and the displaced body placed at its
  old clearance above the new support (no drop).
- Outcome: identical pair outcomes to E-020: 154 tasks, 921 valid pairs (invalid: penetration 269, support change 31,
  off table 11); oracle (1,1) 898, (1,0) 22, (0,0) 1; open loop (1,1) 13, (1,0) 907, (0,0) 1. Over the 302 cases with a
  valid pair: replayed prefix equals the Base oracle state 302/302; Base replay reproduces the Base outcome and step
  count 302/302; null event (1,1) 300, (1,0) 1, (0,1) 1, i.e. the restart alone changes 2 of 302 outcomes; the hand
  held another body at the trigger in 2 of 302 cases.
- Script for E-023 and E-024: `scripts/diagnostic_probes.py` sha256 916f0b2f...42c1 (E-020..E-022: 87634dae...634b); HEAD 0112f5e.
