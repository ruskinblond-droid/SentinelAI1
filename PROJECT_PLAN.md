# SentinelAI — Project Plan & Antigravity Development Guide

## 1. Project Overview

SentinelAI is an existing team project for continuous behavioral authentication using typing behavior.

The system should learn a user's normal typing behavior during enrollment and then continuously compare later typing behavior against that personalized baseline.

Final flow:

**Keystroke events → Feature extraction → Personalized ML model → Anomaly score → Risk engine → Authentication action**

Possible actions:
- Continue the session
- Monitor the session
- Request re-authentication
- Lock the session

The goal is NOT to build a generic typing-speed classifier.

The goal is to build a **personalized behavioral authentication system** that learns how an individual normally types.

## 2. Existing Repository

Repository: `ruskinblond-droid/SentinelAI`

Important structure:

```text
backend/
  ML/
    evaluate.py
    models.py
    train.py
  api/
    __init__.py
    auth.py
    dashboard.py
    enrollment.py
    monitoring.py
  database/
    __init__.py
    database.py
    models.py
  frontend/
    app.py
  security/
    auth.py
    sessionlock.py
  services/
    adaptivelearning.py
    ml.py
    risk_engine.py
main.py
requirements.txt
README.md
sentinelai.db
```

This is an existing team repository.

**DO NOT rebuild it from scratch.**

Preserve existing backend and API functionality unless a change is necessary for ML integration.

## 3. Existing ML Integration

The existing FastAPI application already contains authentication, monitoring, database models, risk calculation and adaptive learning.

The current verification flow is approximately:

1. Verification session starts.
2. Behavioral features are submitted.
3. `backend/services/ml.py` produces a prediction.
4. The prediction anomaly score goes to the risk engine.
5. The risk engine determines risk level/action.
6. A behavior sample and risk event are stored.
7. Adaptive learning may update the user's profile when behavior is considered safe.

Existing feature contract:

- `typing_speed`
- `mean_hold_time`
- `std_hold_time`
- `mean_flight_time`
- `std_flight_time`
- `backspace_rate`
- `pause_mean`
- `mouse_velocity_mean`
- `click_interval_mean`

`backend/services/ml.py` is currently a temporary heuristic implementation. It must eventually be replaced by proper personalized ML.

## 4. ML Objective

The ML system must learn the user's own typing pattern.

Do not make the final system depend on hardcoded rules such as typing speed > X or hold time < Y.

The model should answer:

> Does this current typing behavior resemble the behavior this user normally produces?

rather than:

> Is this person generally a fast or slow typist?

## 5. Personalized Enrollment

During enrollment:

1. Authenticate the user.
2. Ask the user to type controlled text/prompts.
3. Capture raw keyboard timing events.
4. Extract features.
5. Collect multiple legitimate samples.
6. Clean and validate samples.
7. Create a personalized baseline/model.
8. Store the baseline/model for verification.

Do not rely on a single short sample.

## 6. Raw Keystroke Data

Capture behavioral timing information rather than sensitive text unnecessarily.

Useful information:
- key identifier where appropriate
- key press timestamp
- key release timestamp
- event type
- event sequence/order

Hold time = key down → key up.

Flight time = time between consecutive relevant key events, using one clearly defined convention.

Pause = longer gap between typing events.

Use the same timing definitions during enrollment and verification.

Do not store passwords or sensitive typed content unnecessarily.

## 7. Feature Engineering

The first implementation must support the existing nine-feature backend contract:

1. typing speed
2. mean hold time
3. standard deviation of hold time
4. mean flight time
5. standard deviation of flight time
6. backspace rate
7. mean pause
8. mean mouse velocity
9. mean click interval

Possible later features:
- median hold time
- hold-time percentiles
- flight-time percentiles
- digraph timing
- trigraph timing
- typing rhythm
- pause frequency
- burst length
- variability measures

Do not expand the feature set unnecessarily before validating the core pipeline.

Keyboard behavior is the primary signal. Mouse behavior can remain optional if reliable mouse data is unavailable.

## 8. Data Strategy

Use three conceptual data categories.

### Development / experimentation data

Public keystroke datasets may be used for feature engineering, preprocessing, debugging and algorithm experiments.

They are **NOT** a substitute for personalized enrollment.

### Personalized enrollment data

This is the most important data for the final authentication system.

Each user's legitimate typing samples should create that user's behavioral baseline/model.

### Continuous verification data

New typing windows are collected during application use.

Each window is transformed into the same feature representation used during enrollment.

The model determines how closely the new behavior resembles the user's learned behavior.

## 9. Candidate ML Approaches

Investigate appropriate one-class/anomaly-detection approaches, including:

- Isolation Forest
- One-Class SVM
- Local Outlier Factor where appropriate
- distance/statistical approaches
- hybrid personalized anomaly detection

Choose based on:
- suitability for one-class behavioral authentication
- enrollment data requirements
- inference speed
- stability
- personalized-data suitability
- interpretability
- integration simplicity

Do not choose an algorithm merely because it is popular.

Run controlled experiments before finalizing the model.

## 10. Training Pipeline

The training pipeline should eventually:

1. Load enrollment data.
2. Validate data.
3. Remove invalid timing values.
4. Handle missing values.
5. Extract/verify features.
6. Normalize/scale when required.
7. Train the personalized anomaly detector.
8. Evaluate using appropriate validation data.
9. Save model/preprocessor.
10. Make the model available to inference.

Training and inference must use consistent preprocessing.

## 11. Evaluation

Do not evaluate only with ordinary classification accuracy.

Where supported by the data, investigate:
- False Acceptance Rate (FAR)
- False Rejection Rate (FRR)
- Equal Error Rate (EER)
- precision
- recall
- F1
- ROC-AUC where appropriate

Distinguish genuine-user behavior from impostor behavior.

If a metric cannot be meaningfully calculated, document the limitation instead of inventing a result.

## 12. Adaptive Learning

The existing adaptive-learning mechanism should preserve this principle:

**Only trustworthy behavior should influence the future baseline.**

Suspicious behavior must not automatically become training data.

Any adaptive-learning change must be explained before implementation.

Avoid feedback loops where an attacker can teach the model that malicious behavior is normal.

## 13. ML Inference Integration

Primary integration point:

`backend/services/ml.py`

Existing verification endpoint:

`/verification/features`

The ML result should be usable by the existing monitoring/risk flow.

A logical result may include:
- anomaly score
- anomaly status
- model information
- explanation fields where useful

Do not invent a meaningless confidence value if the selected model does not provide one.

If the existing system requires confidence, document how any confidence-like value is derived.

## 14. Risk Engine

Existing conceptual thresholds:

- below 30 → LOW / CONTINUE
- 30–59 → MEDIUM / MONITOR
- 60–79 → HIGH / REAUTHENTICATE
- 80+ → CRITICAL / LOCK_SESSION

Do not casually change these thresholds.

If calibration requires a change, explain and test it first.

## 15. Database

Existing concepts include:
- User
- Device
- BehaviorProfile
- Session
- RiskEvent
- BehaviorSample

Do not change the database schema unless necessary.

If a schema change becomes necessary:
1. Explain why.
2. Identify affected code.
3. Identify migration/data risks.
4. Make the smallest reasonable change.
5. Test existing functionality afterward.

## 16. Model Storage

Use an appropriate serialization mechanism such as joblib where suitable.

Do not commit:
- large datasets
- unnecessary generated model binaries
- temporary experiment outputs
- secrets
- `.env` files containing credentials

## 17. Security / Privacy

Do not store sensitive typed content unnecessarily.

Never commit:
- passwords
- API keys
- tokens
- secrets
- `.env` files containing credentials

Prefer behavioral timing information over retaining actual typed text.

## 18. Antigravity Development Safety Rules

This is an existing team repository.

### Never
- rebuild from scratch
- delete existing working functionality
- rewrite unrelated files
- modify `main`
- force push
- reset the repository
- rewrite Git history
- expose secrets
- commit `.env`
- commit `__pycache__`
- commit unnecessary datasets
- install random/unnecessary dependencies
- change database schema without explaining it
- change unrelated teammate code without a clear reason

### Before significant changes

Always:
1. Inspect the existing implementation.
2. Explain what will change.
3. Explain why.
4. Identify affected files.
5. Identify risks.
6. Implement the smallest reasonable change.

### Development cycle

**PLAN → IMPLEMENT → TEST → REVIEW → COMMIT**

Prefer small reversible changes.

Preserve existing APIs where possible.

ML integrates with the existing backend rather than replacing the application architecture.

When uncertain about a destructive or architectural change, stop and ask.

## 19. Git Safety

Work only on the dedicated development branch.

Never directly modify `main`.

Never:
- force push
- reset main
- delete main
- rewrite shared history

Prefer small commits such as:
- setup ML environment
- add keystroke feature extraction
- add enrollment pipeline
- add personalized anomaly model
- integrate ML inference
- add ML evaluation

Review changes before committing.

# 20. Antigravity Prompts

## Prompt 0 — Read-Only Repository Audit

```text
I am working on an existing team project called SentinelAI.

This is my first time using Antigravity, so do not make changes yet.

First inspect and understand entire repo.

IMPORTANT:
- Do not create/delete/rename/modify files.
- Do not install packages.
- Do not change architecture.
- Do not modify the database.
- Do not modify existing application functionality.
- Read-only analysis.

Read and analyze the overall structure, backend, FastAPI, DB, auth, verification/monitoring, ML files, adaptive learning, risk engine, frontend, requirements, and incomplete files.

Pay particular attention to:
- backend/ML/
- backend/services/ml.py
- backend/services/adaptivelearning.py
- backend/services/risk_engine.py
- backend/api/monitoring.py
- backend/api/enrollment.py
- backend/database/models.py
- backend/main.py
- requirements.txt

Explain:
A. Current architecture
B. Implemented functionality
C. Incomplete functionality
D. ML work required
E. Exact ML integration points
F. Problems/risks
G. Recommended implementation order

Do not implement anything yet.
```

## Prompt 1 — Create the Development Environment

```text
Now prepare the development environment, but do not implement application functionality yet.

Tasks:
1. Inspect requirements.txt.
2. Determine the Python version required by current dependencies.
3. Check whether venv exists.
4. If appropriate create .venv.
5. Ensure required Python development dependencies are available.
6. Recommend/install only relevant development extensions.
7. Configure Python interpreter.
8. Configure debugging for FastAPI.
9. Configure Jupyter.
10. Configure linting/formatting.
11. Configure Git/GitHub.
12. Configure SQLite inspection if useful.

Before changing anything, show the exact changes intended.

Do not modify application source code/database/ML architecture.

Do not install unnecessary packages.
```

## Prompt 2 — ML Architecture Design

```text
Based on PROJECT_PLAN.md and your repository audit, design the ML architecture for SentinelAI.

Do not implement code yet.

The ML system must support personalized behavioral authentication based primarily on typing behavior.

Compare appropriate approaches such as Isolation Forest, One-Class SVM, LOF, and a statistical/distance-based baseline.

Consider:
- personalized enrollment
- limited enrollment samples
- feature scaling
- anomaly scoring
- inference speed
- evaluation
- model persistence
- integration with backend/services/ml.py
- adaptive learning safety

Produce:
1. recommended architecture
2. data flow
3. training flow
4. inference flow
5. evaluation strategy
6. model storage strategy
7. exact files that should be created/modified
8. risks and mitigations

Do not modify files yet.
```

## Prompt 3 — Raw Keystroke / Feature Pipeline

```text
Implement only the keystroke data processing and feature extraction layer described in PROJECT_PLAN.md.

Before editing, show the files you intend to modify/create.

Requirements:
- preserve existing backend architecture
- use the existing nine-feature contract
- define timing calculations clearly
- validate invalid timestamps
- handle missing/insufficient events safely
- avoid storing sensitive typed text unnecessarily
- make feature extraction reusable by both enrollment and verification
- add tests for feature calculations

Do not implement the ML model yet.

After implementation:
1. run relevant tests
2. report failures
3. summarize every changed file
4. do not modify unrelated code
```

## Prompt 4 — Enrollment

```text
Implement the personalized behavioral enrollment pipeline described in PROJECT_PLAN.md.

Before editing, inspect existing authentication, database, monitoring, and API code.

Requirements:
- collect multiple legitimate typing samples
- process raw keyboard timing events
- generate the same feature representation used during verification
- validate samples
- create/update user's personalized behavioral baseline
- do not use suspicious samples for learning
- avoid storing sensitive typed content unnecessarily
- preserve existing APIs unless a new endpoint is genuinely required

Before making any database schema change, stop and explain it.

After implementation, run tests and perform an end-to-end enrollment test.
```

## Prompt 5 — ML Experiments

```text
Now implement the ML experimentation pipeline described in PROJECT_PLAN.md.

Candidate approaches should include appropriate one-class/anomaly detection methods.

Requirements:
- reproducible preprocessing
- feature scaling where appropriate
- training on genuine-user behavioral data
- validation using appropriate genuine/impostor data where available
- meaningful evaluation metrics
- no fabricated metrics
- model persistence
- clear experiment outputs

Keep experimentation code separated from production inference code.

Do not replace the existing backend yet.
```

## Prompt 6 — Final Personalized Model

```text
Based on the completed experiments and documented results, implement the selected personalized anomaly-detection model.

Do not choose an algorithm based only on popularity.

Before implementation, explain:
- selected model
- why it fits our data
- preprocessing
- expected input
- output/anomaly score interpretation
- limitations

Then implement the smallest production-ready version.

Preserve the existing backend contract.
```

## Prompt 7 — Integrate ML With Backend

```text
Integrate the completed ML model into the existing SentinelAI backend.

Primary integration point:
backend/services/ml.py

Existing verification flow:
/verification/features

Requirements:
- preserve existing API behavior where possible
- use the same feature definitions during training and inference
- load the trained personalized model safely
- produce an anomaly score usable by the existing risk engine
- handle missing/unavailable models safely
- do not invent meaningless confidence values
- preserve adaptive-learning safety

Test the complete path:

keyboard features → ML inference → anomaly score → risk engine → stored behavior/risk event

Do not modify unrelated application functionality.
```

## Prompt 8 — End-to-End Testing

```text
Test SentinelAI end to end.

Verify:
1. user authentication
2. enrollment
3. collection of behavioral samples
4. feature extraction
5. personalized model creation/loading
6. verification
7. anomaly scoring
8. risk calculation
9. behavior sample storage
10. risk event storage
11. safe adaptive learning
12. failure handling

Test both:
- genuine behavior
- behavior that differs significantly from enrolled baseline

Do not claim success without actually running tests.

Report:
- tests run
- passed
- failed
- remaining issues
- files changed
```

## Prompt 9 — Final Review / Cleanup

```text
Perform a final engineering review of the completed SentinelAI ML implementation.

Check:
- correctness
- security
- privacy
- ML/data leakage
- preprocessing consistency
- model persistence
- API integration
- error handling
- adaptive learning safety
- unnecessary dependencies
- unnecessary files
- Git hygiene

Also identify committed __pycache__ / .pyc files and propose a safe cleanup.

Do not delete anything until showing me exactly what would be removed.

Do not modify unrelated team work.

Produce a final summary of:
- implemented functionality
- changed files
- tests
- known limitations
- recommended next steps
```

# 21. Definition of Done

The ML portion is complete only when:

- personalized enrollment works
- keyboard events can be collected
- features are extracted consistently
- multiple enrollment samples can be used
- a personalized model/baseline can be created
- new behavior can be evaluated
- an anomaly score is generated
- the existing backend consumes the ML result
- the risk engine receives the result
- suspicious behavior does not automatically poison the model
- adaptive learning is safely controlled
- evaluation is documented
- the system can be demonstrated end-to-end
- tests have been executed
- known limitations are documented

# 22. Working Principle

Do not ask Antigravity to "build the whole project" in one giant operation.

Use:

**Context → Rules → Audit → Design → Small Implementation → Test → Review → Commit**

This keeps the existing team project safe while allowing Antigravity to handle the ML development incrementally.
