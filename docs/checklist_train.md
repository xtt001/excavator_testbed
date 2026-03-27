# AGX ACT Testbed Readiness Checklist

Before recording demos and training the first baseline, make sure the testbed can support:

1. reliable data collection,
2. reproducible training,
3. interpretable rollout analysis,
4. easy failure diagnosis.

---

## 1. Environment and episode control

### Reset and initialization

- Environment reset is stable and repeatable
- Initial excavator pose is deterministic for baseline experiments
- Soil pile / target dump area initialization is deterministic for baseline experiments
- Camera pose(s) are fixed and recorded
- Any randomness in the environment can be switched on/off by config

### Episode lifecycle

- Clear episode start condition
- Clear episode termination condition
- Clear timeout condition
- Clear success condition
- Clear failure condition
- Episode ID is unique and saved everywhere

### Timing

- Control frequency is fixed and known
- Observation frequency is fixed and known
- Logging frequency is fixed and known
- Timestamps are recorded for every observation-action pair
- Teleop latency is measured or at least estimated

---

## 2. Observation pipeline

### Observation definition

- Final baseline observation space is explicitly defined
- The exact observation keys are documented
- Observation dimensions are printed and checked at runtime
- Train-time and eval-time observations are guaranteed to match

### Sensor sanity checks

- Joint positions are correct
- Joint velocities are correct
- Bucket pose is correct
- End-effector / bucket tip position is correct
- Target area state is correct
- Soil-related state, if used, is correct
- Camera images are synchronized and not stale

### Logging

- Raw observations can be saved per timestep
- A lightweight observation summary can be printed during rollout
- Missing / NaN / invalid observations trigger warnings

---

## 3. Action pipeline

### Action definition

- Action space is explicitly documented
- Action dimensions are printed and checked at runtime
- Action bounds are defined
- Action clipping behavior is defined
- Action smoothing / filtering behavior is defined or intentionally disabled

### Execution sanity checks

- A commanded action produces the expected excavator behavior
- Action delay between command and simulator response is understood
- Teleop action format and policy action format are identical
- Recorded actions and replayed actions are in the same scale and convention

### Logging

- Executed action is logged every timestep
- Raw commanded action and final executed action are both saved if filtering exists
- Sudden action spikes can be automatically detected

---

## 4. Demo recording pipeline

### Metadata

- Every demo stores episode ID
- Every demo stores operator ID
- Every demo stores scenario/task version
- Every demo stores timestamp
- Every demo stores config snapshot
- Every demo stores observation/action definitions used during recording

### Quality control

- Each recorded demo can be replayed
- Each demo can be labeled as success/failure
- Each demo can be labeled with notes
- Broken demos can be excluded cleanly
- Very short or truncated demos can be automatically flagged

### Video

- A rollout video is saved for every demo
- Video is synchronized with timestep index
- It is easy to inspect demo videos before using them for training

---

## 5. Dataset tooling

### Dataset inspection

- Script exists to print dataset statistics
- Script exists to inspect episode lengths
- Script exists to inspect action distribution
- Script exists to inspect observation ranges
- Script exists to detect NaN / inf / missing values

### Splits

- Train / val / test split is explicit and saved
- Split is episode-based, not random timestep-based
- Split files can be reproduced with a fixed seed
- Baseline uses a frozen split

### Visualization

- Plot of action trajectories is available
- Plot of episode length distribution is available
- Plot of key state trajectories is available
- Quick viewer exists for stepping through one demo

---

## 6. Training pipeline

### Reproducibility

- Training config is saved with every run
- Random seed is saved
- Code version / git commit is saved
- Checkpoint naming is consistent
- Output directory naming is consistent

### Logging

- Train loss is logged
- Validation loss is logged
- Learning rate is logged
- KL loss is logged if applicable
- Any auxiliary losses are logged
- Checkpoint save events are logged

### Monitoring

- Loss curves can be plotted automatically
- Best checkpoint is tracked automatically
- Last checkpoint is always saved
- Training crash recovery is possible

### Sanity tests

- Model can overfit a tiny subset of demos
- One training batch can run end-to-end without error
- Rollout from an early checkpoint can run without interface bugs

---

## 7. Rollout evaluation pipeline

### Eval protocol

- Eval environment config is fixed for baseline
- Eval seeds are fixed and saved
- Number of rollout trials per checkpoint is fixed
- Eval uses the same observation interface as training
- Eval uses the same action interface as deployment

### Success metrics

- Binary overall task success is defined
- Digging success is defined
- Swing/rotation success is defined
- Dumping success is defined
- Timeout is defined
- Safety violation / invalid behavior is defined if needed

### Per-rollout outputs

- Save rollout video
- Save timestep-wise observations
- Save timestep-wise actions
- Save key event markers
- Save final success/failure label
- Save failure reason label

---

## 8. Failure analysis support

### Failure taxonomy

- Failure labels are defined before experiments begin
- Common failure type: cannot enter soil correctly
- Common failure type: enters soil but fails to scoop
- Common failure type: scoops but loses material before dump
- Common failure type: swing trajectory is wrong
- Common failure type: reaches dump zone but fails to unload correctly
- Common failure type: action jitter / oscillation
- Common failure type: late-stage drift / accumulated error
- Common failure type: rollout diverges despite low training loss

### Analysis tooling

- Tool exists to review failed rollouts quickly
- Tool exists to compare successful and failed rollouts
- Tool exists to plot key state/action traces over time
- Tool exists to align rollout video with timestep logs

---

## 9. Debug visualization

### Must-have visual overlays

- Show episode ID on video
- Show timestep on video
- Show success/failure status on video
- Show current phase if available
- Show commanded action values if useful
- Show key state values if useful

### Nice-to-have

- Side-by-side expert vs policy rollout viewer
- Side-by-side successful vs failed rollout viewer
- Ability to scrub video by timestep
- Ability to inspect a rollout from multiple camera views

---

## 10. Minimum experiment-readiness gates

Before recording the main dataset, confirm these gates are all true:

- I can record one demo and replay it perfectly
- I can save synchronized observation-action-video logs
- I can inspect dataset quality before training
- I can train one small run and get complete logs
- I can rollout one checkpoint and save videos plus metrics
- I can label rollout failures without ambiguity
- I can compare runs reproducibly

---

## 11. Highest-priority things to perfect first

If time is limited, prioritize these in order:

1. [ ] Stable reset and deterministic baseline scenario
2. [x] Correct observation/action logging with timestamps
3. [ ] Demo replay and video saving
4. [x] Frozen train/val split and saved configs
5. [x] Rollout video + per-timestep action/state logging
6. [ ] Clear success metrics and failure labels
7. [ ] Tiny-dataset overfit sanity test

---

## 12. Practical question to ask before baseline training

If the baseline fails, will we be able to answer all of these?

- Was the demo data clean?
- Were observations correct?
- Were actions executed as intended?
- Was training stable?
- Did rollout fail in one phase or all phases?
- Was it a policy problem or a testbed/interface problem?

If the answer is "no" to any of these, improve the testbed first.

