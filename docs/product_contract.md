# FleetGuard AI — Product Contract

## 1. Product Summary

FleetGuard AI is a production-shaped machine-learning platform for detecting
abnormal behaviour in synthetic rail-fleet telemetry.

The platform will generate realistic multivariate telemetry for a fleet of rail
assets, detect developing equipment and sensor anomalies, serve predictions
through an API, monitor model and service behaviour, and support controlled
model retraining and deployment.

An OpenAI-powered investigation agent will retrieve governed evidence from the
platform and produce structured incident briefs for human review.

FleetGuard is a portfolio and learning project. It is not a safety-critical
railway system and must not be presented as suitable for real operational
decisions.

## 2. Intended Users

### Fleet reliability engineer

Needs to identify assets displaying abnormal behaviour, inspect the supporting
telemetry and prioritise cases for investigation.

### Maintenance planner

Needs a concise summary of the affected asset, anomaly severity, supporting
signals and recommended next inspection step.

### ML platform engineer

Needs to train, register, deploy, monitor and safely replace anomaly-detection
models while preserving traceability.

## 3. Core Problem

Fleet telemetry contains variations caused by asset condition, operating load
and environmental conditions.

The platform must distinguish expected variation from potentially abnormal
behaviour while limiting unnecessary alerts.

The initial failure catalogue will include:

1. Gradual axle-bearing degradation.
2. Brake-pressure leakage.
3. Sensor malfunction or drift.

## 4. Initial User Workflow

1. Generate versioned synthetic telemetry for multiple rail assets.
2. Validate telemetry against an explicit data contract.
3. Transform telemetry into leakage-safe time-window features.
4. Train and evaluate anomaly-detection models.
5. Register and promote an approved model.
6. Serve anomaly scores and decisions through a versioned API.
7. Persist predictions and model metadata for auditability.
8. Monitor service health, data drift and prediction behaviour.
9. Raise an alert when defined conditions are exceeded.
10. Allow the investigation agent to retrieve approved evidence.
11. Produce a structured incident brief for human review.
12. Retrain and redeploy models through a governed workflow.

## 5. Primary Success Criteria

### Model effectiveness

On held-out assets, the selected model should detect at least 85% of injected
anomalous windows while keeping the healthy-window false-positive rate at or
below 2%.

These initial thresholds may be revised only through a documented decision
after the synthetic generator and evaluation protocol are validated.

### Serving performance

The inference API should achieve a measured p95 response time below 200 ms for
single-window predictions under the defined local load-test conditions.

### Operational reliability

The Kubernetes deployment must demonstrate:

- readiness and liveness behaviour;
- recovery after pod deletion;
- horizontal scaling under controlled load;
- a rolling model-service update;
- rejection or rollback of an unhealthy release.

### Traceability

Every production-shaped prediction must identify:

- request ID;
- asset ID;
- feature timestamp;
- feature schema version;
- model name and version;
- anomaly score;
- decision and severity;
- processing latency.

### Agent reliability

Every agent-generated incident brief must:

- conform to a structured output schema;
- identify the evidence retrieved through tools;
- distinguish observed evidence from recommendations;
- avoid claiming that an anomaly proves equipment failure;
- recommend human review when evidence is incomplete.

## 6. In Scope

- Synthetic rail-fleet telemetry generation.
- Versioned data and feature contracts.
- Unsupervised and supervised anomaly-model comparison.
- MLflow experiment tracking and model registry.
- Governed model-promotion checks.
- FastAPI inference.
- PostgreSQL prediction and lifecycle metadata.
- Airflow retraining orchestration.
- Docker containerisation.
- Local Kubernetes deployment using kind.
- Helm packaging.
- Prometheus, Grafana and model-drift monitoring.
- CI/CD with GitHub Actions.
- Azure deployment using ACR and AKS.
- Azure workload identity and managed secret access.
- OpenAI API tool calling and structured incident briefs.
- Automated testing, resilience exercises and runbooks.

## 7. Non-Goals

FleetGuard will not:

- use real, confidential or employer-owned railway data;
- claim certification for safety-critical use;
- automatically authorise maintenance or vehicle withdrawal;
- build any streaming data-engineering pipeline using Kafka and Spark;
- attempt to model every possible rail subsystem;
- use an LLM to calculate anomaly scores;
- permit the agent unrestricted database access;
- introduce multiple agents without a demonstrated requirement;
- optimise for global enterprise scale;
- hide model uncertainty or synthetic-data limitations.

## 8. Safety and Decision Boundary

FleetGuard supports investigation; it does not make final maintenance decisions.

Model outputs represent statistical evidence of unusual behaviour rather than
proof of physical failure. Agent recommendations must remain advisory and must
identify uncertainty and missing evidence.

## 9. Portfolio Outcome

FleetGuard should demonstrate the ability to take an ML system through:

data design → feature engineering → experimentation → model registration →
serving → monitoring → retraining → Kubernetes operation → cloud deployment →
governed AI-assisted investigation.