# FleetGuard AI — Glossary

Use with the [signal catalogue](signal_catalogue.md) and [generation guide](dataset_generation_guide.md).
Definitions describe the FleetGuard model; manufacturer-specific terminology may differ.

## Wagon and engineering terms

| Term | Meaning in FleetGuard |
| --- | --- |
| Asset / wagon | The unit being monitored, identified by `asset_id`. |
| Fleet | A grouping of assets; distinct from a journey or dataset split. |
| Bogie | A frame supporting two axles. There are two per wagon. |
| Axle / wheelset | One rigid axle with a left and right wheel; both rotate together. |
| Inner / outer | Position within a bogie relative to the wagon centre/end; mirrored at the opposite end. |
| Wheel side | Left/right identity within the selected axle. |
| Bearing | Supports the rotating axle; its temperature is recorded against a wheel side. |
| Axle generator | One of four synthetic power-generation units; the failure scenario also removes that axle's speed/RPM readings. This coupling is a project assumption. |
| BPP | Brake-pipe pressure, shared at wagon level. |
| BCP | Brake-cylinder pressure, one reading for each bogie. |
| AR | Auxiliary-reservoir pressure, shared wagon signal. |
| SR | Secondary-reservoir pressure, shared wagon signal. |
| Transducer | Converts a physical quantity into a measurement; the pressure fault represents a failed reading. |
| Brake demand | Independent simulated apply/release context, distinct from observed pressure response. |
| Brake release failure | Release is demanded but a cylinder-pressure response stays elevated after application. |
| Undemanded application | Braking signature occurs during release demand. |
| Slide | Wheelset rotation is slower than wagon motion during eligible braking. |
| Locked axle | Valid zero wheelset rotation while the wagon is moving. |
| Suspected flat | Synthetic axle vibration uplift consistent with a possible flat; not proof of damage or an identified left/right wheel. |
| RMS | Root mean square, a summary of vibration magnitude rather than a raw waveform. |
| g | Acceleration expressed relative to standard gravity; used for vibration RMS. |
| Adhesion | Wheel–rail grip, represented by a dimensionless coefficient. |
| Controller | Collects and reports the wagon snapshot, alongside its own health and supply diagnostics. |
| Battery cell-equivalent voltage | Synthetic 3.0–4.2 V scale; not a claimed real wagon battery-pack voltage. |
| Regulated supply | Separate controller electrical rail, healthy near 25.2 V. |
| Dwell | Planned stationary time at the origin, intermediate point or destination. |
| Route / journey | Route is the reusable corridor; journey is one planned duty on it. |
| GPS / coordinates | Latitude/longitude location context; FleetGuard interpolates coarse route points. |
| Uptime / reset | Runtime since controller start; recovery can reset uptime and increase reset count. |

## Data and simulation terms

| Term | Meaning |
| --- | --- |
| Synthetic | Created by a simulator, not collected from an operating railway. |
| Healthy baseline | Normal simulated readings before fault transformations. |
| Seed | Initial input for repeatable pseudo-random choices; not an asset ID. |
| Derived seed | Independent repeatable random stream for a specific planning purpose. |
| Noise | Controlled measurement/baseline variation, distinct from a deliberate anomaly. |
| Sampling interval | Time between expected reports: 1, 10 or 60 seconds. |
| Event grain | One received wagon snapshot at one time, not eight independent wagon events. |
| Normalisation | Projection of nested data into separate component rows with shared parent identity. |
| JSON / JSONL | JSON is a document; JSONL has one JSON record per line. |
| Contract / schema | Explicit permitted record structure, types, bounds and consistency rules. |
| Null | No available engineering measurement; never automatically a physical zero. |
| Quality flag | Valid/missing/invalid reading status; omitted entry means valid. |
| Raw error code | Device-style invalid value retained in quality metadata, not the measurement. |
| Truth | Simulator-known cause/target/label, isolated from model inputs. |
| Missing-report truth | A scheduled slot that emitted no report; not an observed event. |
| Outage interval | A group of missing slots; end time is exclusive. |
| Persistent / bounded | Persists through the horizon / resumes at a configured recovery time. |
| Manifest | File inventory with counts, versions and hashes; not itself a validator. |
| Checksum / SHA-256 | Digest used to detect file changes; not certification of physical realism. |
| Lineage | Links a derived row back to source records, asset, journey and configuration. |
| Cohort | Planned collection of assets used to exercise dataset coverage. |
| Replicate | Another copy of each of the 13 fault variants per split, not another sample of the same row. |
| Coverage fixture | Deliberately includes scenarios; does not represent natural fault prevalence. |

## Features and future ML platform

| Term | Meaning |
| --- | --- |
| Feature | A representation selected as a model input; not every saved column is suitable. |
| Window | A time interval grouping readings; current summaries use 60 seconds. |
| Half-open interval | Includes start, excludes end, so boundary samples are not double-counted. |
| Hierarchical summary | Separate summaries at wagon, bogie, axle and wheel levels. |
| Aggregation | Reduction of readings into statistics such as mean/minimum/maximum. |
| First / last | First/last valid numerical value in timestamp order. |
| Completeness | Received reports divided by expected reports. |
| Silent window | No reports received; measurement summaries remain empty, identities remain. |
| Sample fraction | Share of received samples in a state; not necessarily share of elapsed time. |
| Transition count | Changes between observed categories within one window, not exact physical event count. |
| Counter positive change | Sum of positive differences between valid observations within the minute. |
| Train / validation / test | Fit models / select settings / final held-out evaluation. |
| Held-out asset | Wagon whose readings were not used in fitting. |
| Leakage | Evaluation or future information improperly entering training/model inputs. |
| Unsupervised / supervised | Learning patterns without target labels / learning from labelled examples. |
| Anomaly score / threshold | Model evidence of unusual behaviour / selected decision boundary; neither proves failure. |
| False positive / recall | Healthy item incorrectly flagged / proportion of anomalous items detected. |
| MLOps | Traceable lifecycle of training, registration, serving, monitoring and replacement. |
| Model registry | Versioned model records and lifecycle metadata, planned with MLflow. |
| Inference | Applying a trained model to new inputs, planned through FastAPI. |
| Drift | Change in incoming data or prediction behaviour relative to a reference. |
| Orchestration | Scheduling dependent workflow tasks, planned with Airflow. |
| Container / Kubernetes | Packaged service runtime / platform for deploying and operating containers. |
| kind / AKS | Local Kubernetes in Docker / Azure Kubernetes Service. |
| Investigation agent | Planned OpenAI tool-using assistant retrieving governed evidence for human-review briefs. |

Future platform terms describe intended work, not completed deployment.
