# Contract schema snapshots

These JSON Schemas were exported from the current Pydantic record models.
Source records are version 3.2; component windows are feature version 2.0.

- [AssetMetadata](./AssetMetadata.schema.json)
- [JourneyMetadata](./JourneyMetadata.schema.json)
- [TelemetryEvent](./TelemetryEvent.schema.json)
- [BogieObservation](./BogieObservation.schema.json)
- [AxleObservation](./AxleObservation.schema.json)
- [WheelObservation](./WheelObservation.schema.json)
- [AnomalyTruth](./AnomalyTruth.schema.json)
- [MissingReportTruth](./MissingReportTruth.schema.json)
- [OutageTruth](./OutageTruth.schema.json)
- [ComponentWindow](./ComponentWindow.schema.json)

JSON Schema describes fields, required values, types and numerical boundaries.
Python validators additionally enforce relationships: identities, temporal
consistency, quality/null rules and feature field policies. Validating against
JSON Schema alone does not execute those custom checks. Use the saved-dataset
CLI validators described in [the generation guide](../dataset_generation_guide.md).

Administrative manifests, cohort plans and scenario configuration are not
Pydantic record snapshots in this directory. Their actual checks live in the
portfolio and feature dataset validators.
