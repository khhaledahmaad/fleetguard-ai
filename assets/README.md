# FleetGuard animation assets

Light engineering-style schematic animations for documentation. `00_wagon_exploded.gif` covers wagon hierarchy and telemetry ownership; `01`–`12` each cover a separate anomaly scenario. Each loop takes about 13 seconds. The exploded view separates the body, bogies, axles and wheels in sequence. Outer axles are nearest their respective wagon ends.

The signal traces are illustrative sketches, not measured data or detector thresholds. The 3.0–4.2 V battery curve is a synthetic single-cell equivalent. Controller scenario 12 shows persistent sag and a bounded abrupt interruption with reboot under one anomaly type. Its reporting gaps contain no invented readings. The hub and GPS failures are outside this catalogue. `fleetguard-logo.svg` is the FleetGuard logo used in these animations.

`contact_sheet.png` provides an overview of the complete set. To rebuild with Pillow and either DejaVu Sans or Windows Arial/Consolas: `python build_fleetguard_assets.py`.
