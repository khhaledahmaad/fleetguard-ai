# UK railway geometry — generator 0.4.0

## Route representation

The generator follows track-level polylines from Network Rail's public GIS
release.
The fixture is bundled in the Python package, so generation works offline.
No live routing API is required.

| Route ID | Origin | Destination | Mapped distance |
| --- | --- | --- | ---: |
| FG-RTE-LONDON-AVONMOUTH | London Aggregate Terminal | Avonmouth Freight Terminal | 198.45 km |
| FG-RTE-AVONMOUTH-CARDIFF | Avonmouth Freight Terminal | Cardiff | 67.56 km |
| FG-RTE-CARDIFF-SWANSEA | Cardiff | Swansea Materials Terminal | 73.45 km |
| FG-RTE-LONDON-SWANSEA | London Aggregate Terminal | Swansea Materials Terminal | 339.45 km |

Reverse duties use the same geometry in reverse. The full London–Swansea duty
retains the established via-Avonmouth corridor, rather than being replaced with
a different direct service. Existing named intermediate waypoints are retained.

## Source and attribution

- Source: Network Rail **NetworkLinks**, a track-level ELR/TRID geometry release.
- Mirror: https://github.com/openraildata/network-rail-gis
- Pinned commit: `a7c2cece9df7770e68a78cd716604c96ae38cd1a` (15 August 2024).
- Retrieved: 15 October 2026. This date is not the date of a fresh infrastructure survey.
- Licence: Open Government Licence v3.0.
- Attribution: Contains information of Network Rail Infrastructure Limited
  licensed under the Open Government Licence v3.0.
- Licence: https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/
- Source caveats: https://github.com/openraildata/network-rail-gis/blob/a7c2cece9df7770e68a78cd716604c96ae38cd1a/CAVEATS.md

The mirror explicitly describes its data as out of date. A newer product exists
on Rail Data Marketplace; this fixture is a reproducible historical geometry
reference, not a claim about current operational infrastructure.

## How the fixture was derived

1. Read the source track links in British National Grid, EPSG:27700.
2. Build a graph from successive source vertices, quantised to 0.1 m. Do not
   invent crossovers, connect nearby parallel lines or bridge gaps.
3. Snap the existing illustrative waypoints to vertices in the connected network.
4. Find distance-weighted paths between those waypoints.
5. Check every selected link is marked `IN USE` in the historical attribution table.
6. Transform source vertices using a pinned OSGB36/WGS84 Helmert pipeline and
   bundle the four routes. This avoids machine-dependent optional grid selection;
   it is not a claim of centimetre-level positional accuracy.

The selected paths use 314 unique source link IDs. Source hashes, named points,
link IDs, snapping distances and limitations are recorded in
`src/fleetguard/generator/data/uk_rail_routes.geojson`.
Source link attributes are historical evidence, not current access permissions.

The derived graph represents geometry connectivity. It does not model signalling,
gauge clearance, permitted directions, point-setting or freight operating access.
Telemetry follows the extracted links without added straight-line connectors.

## Locations and names

Route anchor coordinates are snapped to nearby mapped rail vertices. The fixture
records each anchor, snapped point and snapping distance for reproducibility.
Terminal and holding-point names are illustrative: the fixture does not confirm
actual sidings, freight stops or named commercial premises.

## Speed, distance and duration

`route_progress` represents fraction of **along-track distance travelled**.
The same continuous speed profile determines reported speed and position:

- accelerate for 120 seconds;
- cruise as needed;
- brake for 120 seconds;
- dwell with zero speed and fixed coordinates.

Running time is rounded up to full minutes and cruise speed solved so the
integral covers the exact mapped distance. Intermediate stops use cumulative
track distance. Journey speed has no independent random noise that could make
it disagree with the position trajectory; other measurement variation remains.

Duration is physically consistent with this simplified model, **not a real
freight timetable or a track-specific speed-limit model**. Terminal dwell and
intermediate holds are simulated. Real service timing needs train performance,
speed restrictions, pathing and booked operating information.

Fixed-period development helpers advance on the same track geometry only by their generated travelled distance.
They can finish partway through a route because period count is an observation
horizon, not a promise to complete a duty.

## Versions and downstream work

- Generator: 0.4.0.
- Geometry and motion model: 2.0.
- Telemetry contract: 3.2, unchanged.
- Feature contract: 2.0, unchanged.

Run manifests record geometry version, geometry SHA-256 and motion-model version.
Current portfolio validation checks those fields. The canonical development
dataset is `portfolio-v1`; source and features must share matching provenance.

See [the data workflow](data_workflow.md) for commands.

## Output publication

The generator publishes each completed UTF-8 file through a
temporary file and atomic replacement, before writing its manifest. Validation
still checks every saved file; no checksum or row-count check is bypassed.
Serialisation is per in-memory run, so very large shared-fleet demo runs require
more memory. The portfolio runner continues to generate one asset per run.
