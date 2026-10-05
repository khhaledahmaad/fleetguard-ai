# FleetGuard AI Engineering Atlas — Edition 04

## Open

Extract the standalone atlas ZIP completely and open index.html. In the full
repository, open atlas/_site/index.html. Keep the assets folder beside the HTML.
No internet, server, Python or Quarto is required to view it.

## The visual story

System and signals → healthy generation → anomaly injection → data and features.
The future ML platform is a short roadmap. Technical policies and sources remain
available through collapsed sections and the reference register.

Native HTML/SVG engineering drawings show two bogies, four axles and eight wheels,
with both wheel sides below their parent axles. Components are colour-coded and
clickable, including generators, brake cylinders, shared pneumatics, battery and
controller. Assembled/exploded transitions, wheel motion, fault highlights and
reporting state are illustrated directly in the atlas. It has no GIF dependency.
Independent assets in the repository's root assets folder are kept separate.

Demos default to 1× and run for 20 seconds. Scenario presentation gives healthy
context, fault development and the resulting effect. This is compressed playback,
not real time or a change to the generator. Full generated observations remain
in the plots and scrubber. Simulated UTC time is always displayed. Animated views autoplay and loop; pause, replay, 0.5× and 2× remain available.
Reduced-motion preferences default to paused. Motion is an engineering illustration, not a
validated mechanical simulation.

The twelve scenario types include both controller outage modes. Fixed demo targets
are distinct from seeded portfolio assignments. Numerical examples come from the
actual project generator and hierarchical aggregation functions. No model has
been trained or deployed by this atlas.

## Rebuild (Windows CMD, from repository root)

```cmd
python scripts\build_fleetguard_atlas.py
```

Uses existing project dependencies. Refreshes atlas/assets/data.js, index.html,
index.qmd and _site. It does not modify generated datasets or feature datasets.

Quarto source is included. Optional command, if Quarto is installed:

```cmd
quarto render atlas
```

The supplied offline HTML is built by Python. Quarto rendering was not tested.

## Edit

- atlas/assets/atlas.js: drawings, interactions, page content and playback.
- atlas/assets/atlas.css: colour system, animation and responsive layout.
- atlas/_body.html: navigation and application shell.
- scripts/build_fleetguard_atlas.py: reproducible fixtures and offline build.

Rebuild after editing. atlas/_site is ignored by Git. Source atlas files and its
small documentation fixtures belong in Git; large generated datasets are ignored.
Ignore rules do not untrack files already committed.

## Component explorer and product framing

Overview introduces FleetGuard as a product concept and technical demonstrator.
Demonstrated data/feature capabilities are distinguished from planned ML services
and commercial validation needs. Real-data performance and operational suitability
are not claimed. The original product contract still records the learning origin.

Every component opens its own functional SVG cutaway: wheel and bearing, axle,
generator, bogie, battery, controller, BPP, AR, SR and per-bogie BCP. Cutaways have
independent pause/replay. Illustrative internals are not manufacturer drawings.
Controller details distinguish reported location/speed from health measurements.
No new sensor fields are introduced. The wagon uses a light chassis frame.

Healthy generation keeps location and its signal plots in one compact panel.
Component selection persists through trace redraws. Modals support Escape,
keyboard focus containment and return; navigation closes an open dialog.
Static documents and tables stay static. Animated views start automatically,
except when the browser requests reduced motion.

## Visual guide for mixed audiences

Primary pages now explain the story without code knowledge:

1. System and components: permanent inner/outer and generator labels in all views.
2. The data: component pictures, readable signal names and the reporting chain.
3. How we create data: fleet characteristics → journey → healthy readings → fault.
4. Anomaly signatures: healthy/fault comparisons with readable signal names.
5. Features: six ten-second readings → one-minute summaries, by component level.

The feature guide lists the policies for all 28 numerical field placements and
all categorical fields. Location retains its last observed coordinate pair;
fixed attributes and identities remain linked. Bogie summaries carry shared
wagon context alongside local cylinder pressure. Counter changes and quality
information are explained separately. The original reports remain available.

The reporting controller collects measurements; it is not presented as the
physical origin of every measurement. The redundant isolated BPP sensor symbol
is removed. Each pressure remains individually inspectable.

Detailed trace, field inspector, file validation and source code are optional
under Technical detail. Functional generation diagrams are illustrative; the
feature example values are computed by the existing aggregation implementation.
