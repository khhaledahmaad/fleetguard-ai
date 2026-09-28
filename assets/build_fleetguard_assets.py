"""Render light, technical FleetGuard storyboards as separate animated GIFs."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
W, H = 1500, 940
PAPER = "#F7F7F3"
WHITE = "#FFFFFF"
INK = "#223946"
SUB = "#647783"
GRID = "#E7EAE7"
RULE = "#B8C5C8"
TEAL = "#087C79"
BLUE = "#3279A0"
AMBER = "#B56B37"
RED = "#BB4D43"
GREEN = "#368466"


def font_path(*candidates: str) -> str:
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    raise FileNotFoundError("Install DejaVu Sans or use the Windows Arial/Consolas fonts")


FONT = font_path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf")
MONO = font_path(
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "C:/Windows/Fonts/consola.ttf"
)
BOLD = font_path(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"
)
F11 = ImageFont.truetype(MONO, 11)
F13 = ImageFont.truetype(MONO, 13)
F15 = ImageFont.truetype(FONT, 15)
F17 = ImageFont.truetype(FONT, 17)
F18 = ImageFont.truetype(FONT, 18)
F20 = ImageFont.truetype(BOLD, 20)
F23 = ImageFont.truetype(BOLD, 23)
F33 = ImageFont.truetype(BOLD, 33)


SCENARIOS = [
    {
        "slug": "01_bearing_degradation",
        "name": "Gradual bearing degradation",
        "scope": "WHEEL + PARENT AXLE",
        "focus": "wheel-left",
        "lead": "A single bearing warms progressively; its parent axle also vibrates more.",
        "lines": [
            "Target: bogie 1 / outer axle / left wheel",
            "Bearing temperature rises above peers.",
            "Parent-axle vibration rises too.",
            "Other wheelsets retain healthy baselines.",
        ],
        "traces": [
            ("bearing temp · target", RED, [0.27, 0.28, 0.31, 0.37, 0.47, 0.56, 0.67, 0.76, 0.85]),
            ("bearing temp · peers", BLUE, [0.27, 0.28, 0.29, 0.29, 0.31, 0.30, 0.32, 0.32, 0.33]),
            (
                "parent axle vibration",
                AMBER,
                [0.20, 0.21, 0.22, 0.25, 0.30, 0.36, 0.44, 0.52, 0.60],
            ),
        ],
        "end": "Correlated heat and vibration support an investigation; they do not prove failure.",
    },
    {
        "slug": "02_brake_pressure_leak",
        "name": "Brake pressure leak",
        "scope": "WAGON PNEUMATICS",
        "focus": "pneumatic",
        "lead": "Shared brake-pipe and auxiliary-reservoir pressure decay abnormally.",
        "lines": [
            "Target: wagon pneumatic system",
            "BPP and AR fall below healthy behaviour.",
            "SR and both bogie BCP readings stay on",
            "their healthy baseline in this scenario.",
        ],
        "traces": [
            ("BPP", RED, [0.83, 0.82, 0.80, 0.75, 0.68, 0.59, 0.50, 0.42, 0.34]),
            ("AR", AMBER, [0.78, 0.78, 0.77, 0.73, 0.67, 0.60, 0.52, 0.45, 0.38]),
            ("SR · unchanged", BLUE, [0.77, 0.77, 0.78, 0.77, 0.77, 0.78, 0.77, 0.77, 0.78]),
        ],
        "end": "A commanded brake application also lowers BPP; context matters.",
    },
    {
        "slug": "03_bearing_sensor_drift",
        "name": "Bearing temperature sensor drift",
        "scope": "WHEEL MEASUREMENT",
        "focus": "wheel-left",
        "lead": "One reported bearing temperature drifts while physical vibration stays normal.",
        "lines": [
            "Target: bogie 1 / outer axle / left wheel",
            "Reported bearing temperature rises.",
            "Parent-axle vibration stays healthy.",
            "The true bearing condition is unknown.",
        ],
        "traces": [
            ("reported temperature", RED, [0.29, 0.30, 0.32, 0.40, 0.49, 0.59, 0.67, 0.78, 0.87]),
            ("parent axle vibration", BLUE, [0.20, 0.21, 0.19, 0.21, 0.20, 0.20, 0.22, 0.21, 0.20]),
        ],
        "end": "The changing reading belongs to the sensor fault, not a proven hot bearing.",
    },
    {
        "slug": "04_axle_speed_generator_failure",
        "name": "Axle speed generator failure",
        "scope": "AXLE GENERATOR + SPEED",
        "focus": "axle",
        "lead": "One axle generator loses its usable speed output and power contribution.",
        "lines": [
            "Target: bogie 1 / outer axle",
            "Speed becomes missing, invalid or stuck.",
            "Other axles show the wagon is moving.",
            "Remaining generators may sustain power.",
        ],
        "traces": [
            ("other axles · speed", BLUE, [0.65, 0.66, 0.67, 0.68, 0.68, 0.69, 0.69, 0.70, 0.70]),
            ("target axle · reading", RED, [0.65, 0.66, 0.66, 0.66, None, None, None, None, None]),
            (
                "generator contribution",
                AMBER,
                [0.65, 0.65, 0.64, 0.52, 0.30, 0.12, 0.08, 0.08, 0.08],
            ),
        ],
        "end": "A raw invalid sentinel is a quality flag, never a physical wheel speed.",
    },
    {
        "slug": "05_wheel_slide",
        "name": "Wheel slide",
        "scope": "AXLE / WHEELSET",
        "focus": "axle",
        "lead": "Under braking, the wheelset rotates more slowly than wagon travel.",
        "lines": [
            "Target: one axle / wheelset",
            "Axle speed dips below wagon speed.",
            "Rotation continues and can recover.",
            "Validate speed sensor and brake context.",
        ],
        "traces": [
            ("wagon speed", BLUE, [0.82, 0.80, 0.77, 0.74, 0.71, 0.68, 0.64, 0.61, 0.58]),
            ("target axle speed", RED, [0.82, 0.80, 0.77, 0.57, 0.43, 0.49, 0.58, 0.61, 0.58]),
        ],
        "end": "A brief slide may need 1-second samples; 10-second samples can miss it.",
    },
    {
        "slug": "06_locked_axle",
        "name": "Locked axle",
        "scope": "AXLE / WHEELSET",
        "focus": "axle",
        "lead": "The wagon moves while a valid axle-speed reading approaches zero.",
        "lines": [
            "Target: one axle / wheelset",
            "Wagon speed remains positive.",
            "Axle rotation approaches zero and persists.",
            "Confirm measurement quality first.",
        ],
        "traces": [
            ("wagon speed", BLUE, [0.81, 0.79, 0.77, 0.74, 0.71, 0.67, 0.63, 0.60, 0.57]),
            ("target axle speed", RED, [0.81, 0.79, 0.76, 0.55, 0.29, 0.08, 0.07, 0.07, 0.07]),
        ],
        "end": "Sustained sliding may lead to wheel-tread damage and track impacts.",
    },
    {
        "slug": "07_suspected_wheel_flat",
        "name": "Suspected wheel flat",
        "scope": "AXLE VIBRATION · WHEEL UNKNOWN",
        "focus": "wheel-unknown",
        "lead": "A repeating impact signature appears on the affected axle during movement.",
        "lines": [
            "Target: one axle / wheelset",
            "Axle vibration includes repeated peaks.",
            "Wheel speed remains physically plausible.",
            "Left or right wheel cannot be identified.",
        ],
        "traces": [
            ("target axle vibration", RED, [0.18, 0.20, 0.21, 0.26, 0.82, 0.30, 0.86, 0.34, 0.88]),
            ("peer axle vibration", BLUE, [0.18, 0.20, 0.19, 0.20, 0.19, 0.20, 0.18, 0.20, 0.19]),
        ],
        "end": "At 10-second sampling, store impact-window features to retain short shocks.",
    },
    {
        "slug": "08_pressure_transducer_failure",
        "name": "Pressure transducer failure",
        "scope": "SENSOR AT ITS PHYSICAL LEVEL",
        "focus": "bcp-1",
        "lead": "A pressure reading becomes invalid while the actual pressure is unknown.",
        "lines": [
            "Example: bogie 1 BCP transducer",
            "BPP / AR / SR are wagon-level sensors.",
            "BCP is measured once per bogie.",
            "Compare corroborating pressure signals.",
        ],
        "traces": [
            ("bogie 1 BCP reading", RED, [0.27, 0.27, 0.28, 0.29, 0.88, None, None, None, None]),
            ("bogie 2 BCP", BLUE, [0.27, 0.27, 0.27, 0.28, 0.27, 0.27, 0.28, 0.27, 0.27]),
        ],
        "end": "Do not interpret an invalid pressure value as a physical pressure spike.",
    },
    {
        "slug": "09_brake_release_failure",
        "name": "Brake release failure",
        "scope": "WAGON BRAKE SYSTEM",
        "focus": "brakes",
        "lead": "Release is requested and BPP recovers, yet braking persists.",
        "lines": [
            "Truth scope: whole wagon brake system",
            "Wagon BPP rises after release demand.",
            "BCP on one or both bogies stays elevated.",
            "Preserve both bogie readings as evidence.",
        ],
        "traces": [
            ("wagon BPP", BLUE, [0.20, 0.21, 0.23, 0.40, 0.56, 0.69, 0.77, 0.79, 0.79]),
            ("bogie 1 BCP", RED, [0.79, 0.79, 0.79, 0.77, 0.76, 0.75, 0.74, 0.73, 0.72]),
            ("bogie 2 BCP", AMBER, [0.79, 0.79, 0.78, 0.60, 0.43, 0.28, 0.20, 0.17, 0.16]),
        ],
        "end": "One bogie is shown remaining applied; the anomaly label stays wagon-level.",
    },
    {
        "slug": "10_undemanded_brake_application",
        "name": "Undemanded brake application",
        "scope": "WAGON BRAKE SYSTEM",
        "focus": "brakes",
        "lead": "Braking starts without a corresponding application demand.",
        "lines": [
            "Truth scope: whole wagon brake system",
            "Demand remains at release.",
            "Wagon BPP falls unexpectedly here.",
            "Both bogie BCP readings rise.",
        ],
        "traces": [
            ("wagon BPP", BLUE, [0.80, 0.80, 0.79, 0.76, 0.62, 0.48, 0.38, 0.35, 0.34]),
            ("bogie 1 BCP", RED, [0.17, 0.18, 0.18, 0.21, 0.35, 0.51, 0.63, 0.66, 0.67]),
            ("bogie 2 BCP", AMBER, [0.17, 0.17, 0.18, 0.20, 0.32, 0.48, 0.60, 0.64, 0.65]),
        ],
        "end": "The observed pattern signals a fault; it does not establish root cause.",
    },
    {
        "slug": "11_premature_battery_depletion",
        "name": "Premature battery depletion",
        "scope": "SHARED WAGON BATTERY",
        "focus": "battery",
        "lead": "The wagon loses battery reserve faster than expected during standstill.",
        "lines": [
            "Target: one shared wagon battery",
            "Four axle generators recharge in motion.",
            "Battery supports the controller at rest.",
            "At cut-off, messages cease until power returns.",
        ],
        "traces": [
            (
                "expected battery voltage",
                BLUE,
                [0.91, 0.87, 0.82, 0.77, 0.72, 0.66, 0.60, 0.54, 0.49],
            ),
            ("actual battery voltage", RED, [0.91, 0.84, 0.74, 0.61, 0.47, 0.32, 0.20, None, None]),
            ("warning · synthetic 3.2 V", AMBER, [0.34] * 9),
        ],
        "end": (
            "4.2 / 3.2 / 3.0 V are project assumptions per cell equivalent; "
            "no post-cut-off reading.",
        ),
    },
    {
        "slug": "12_controller_supply_failure",
        "name": "Controller supply failure",
        "scope": "WAGON CONTROLLER / FCU",
        "focus": "controller",
        "lead": "One controller power-path fault with two possible outage patterns.",
        "lines": [
            "Target: wagon controller power path",
            "A / Persistent: supply sags; reports stop.",
            "B / Bounded: abrupt gap; reboot follows.",
            "Upstream power is healthy in truth.",
        ],
        "end": "Both merit review. Missing reports alone cannot prove a controller power fault.",
    },
]


def line_text(draw, xy, value, font=F15, fill=INK):
    draw.text(xy, value, font=font, fill=fill)


def plate(draw, box, fill=WHITE, outline=RULE, radius=7, width=2):
    draw.rounded_rectangle(box, radius, fill=fill, outline=outline, width=width)


def brand(draw):
    # FleetGuard logo reproduced in the raster animation headers.
    draw.ellipse((50, 36, 88, 74), outline=TEAL, width=3)
    draw.ellipse((62, 48, 76, 62), outline=TEAL, width=2)
    draw.line((39, 56, 50, 56), fill=TEAL, width=3)
    draw.line((88, 56, 99, 56), fill=TEAL, width=3)
    draw.line((70, 50, 73, 44, 78, 51), fill=TEAL, width=3)
    line_text(draw, (111, 37), "FLEETGUARD", F23, INK)
    line_text(draw, (113, 65), "AI  /  RAIL TELEMETRY", F11, TEAL)


def layout(draw, title, code, subtitle):
    draw.rectangle((0, 0, W, H), PAPER)
    for x in range(60, 1085, 25):
        draw.line((x, 163, x, 738), fill=GRID)
    for y in range(163, 739, 25):
        draw.line((60, y, 1085, y), fill=GRID)
    brand(draw)
    draw.line((46, 103, 1454, 103), fill=INK, width=2)
    line_text(draw, (49, 114), title, F33, INK)
    line_text(draw, (52, 171), subtitle, F15, SUB)
    line_text(draw, (1260, 45), code, F13, TEAL)
    line_text(draw, (1305, 70), "DWG FG-OPS / A", F11, SUB)
    draw.rectangle((43, 198, 1094, 746), outline=RULE, width=2)
    draw.rectangle((1114, 198, 1458, 746), fill=WHITE, outline=RULE, width=2)
    draw.line((46, 764, 1454, 764), fill=INK, width=2)
    line_text(
        draw,
        (50, 918),
        "FLEETGUARD  /  SYNTHETIC TRAINING DATA   •   NOT FOR OPERATIONAL DECISIONS",
        F11,
        SUB,
    )
    line_text(draw, (1340, 918), "A / 01", F11, SUB)


def engineering_wagon(draw, focus="", phase=0, exploded=False):
    active = phase >= 2
    base = INK
    battery_color = RED if active and focus == "battery" else TEAL
    pneumatic_color = RED if active and focus in ("pneumatic", "brakes") else BLUE
    y_shift = (-30 if phase >= 1 else 0) if exploded else 0
    bogie_shift = (26 if phase >= 2 else 0) if exploded else 0
    wheel_shift = (41 if phase >= 3 else 0) if exploded else 0
    # Wagon body: hopper silhouette, framing ribs, and underframe.
    outline = [
        (150, 341 + y_shift),
        (212, 291 + y_shift),
        (950, 291 + y_shift),
        (1014, 341 + y_shift),
        (965, 468 + y_shift),
        (190, 468 + y_shift),
    ]
    draw.polygon(outline, fill=WHITE)
    draw.line(outline + [outline[0]], fill=base, width=3, joint="curve")
    draw.line((212, 291 + y_shift, 950, 291 + y_shift), fill=INK, width=3)
    for x in (295, 410, 525, 640, 755, 870):
        draw.line((x, 298 + y_shift, x - 25, 454 + y_shift), fill=RULE, width=2)
    draw.line((133, 475 + y_shift, 1034, 475 + y_shift), fill=INK, width=5)
    draw.line((180, 488 + y_shift, 984, 488 + y_shift), fill=INK, width=2)
    line_text(draw, (502, 318 + y_shift), "FG-WGN-0001", F20, INK)
    line_text(draw, (509, 350 + y_shift), "FREIGHT WAGON", F13, SUB)
    # Pneumatic trunk: wagon BPP, and the two shared reservoirs.
    draw.line((236, 435 + y_shift, 928, 435 + y_shift), fill=pneumatic_color, width=3)
    for x in range(246, 922, 42):
        draw.line((x, 432 + y_shift, x + 12, 438 + y_shift), fill=pneumatic_color, width=1)
    plate(draw, (244, 394 + y_shift, 357, 429 + y_shift), outline=pneumatic_color, width=2)
    plate(draw, (371, 394 + y_shift, 484, 429 + y_shift), outline=pneumatic_color, width=2)
    plate(draw, (498, 394 + y_shift, 611, 429 + y_shift), outline=pneumatic_color, width=2)
    for x, label in ((264, "BPP"), (405, "AR"), (534, "SR")):
        line_text(draw, (x, 403 + y_shift), label, F15, pneumatic_color)
    # Controller, battery, communication node, and power cable.
    controller_color = RED if active and focus == "controller" else TEAL
    plate(
        draw,
        (664, 391 + y_shift, 793, 425 + y_shift),
        outline=controller_color,
        width=3 if controller_color == RED else 2,
    )
    plate(draw, (815, 391 + y_shift, 929, 425 + y_shift), outline=battery_color, width=3)
    line_text(draw, (672, 400 + y_shift), "CONTROL", F13, controller_color)
    line_text(draw, (833, 400 + y_shift), "BATTERY", F13, battery_color)
    draw.line(
        (751, 382 + y_shift, 751, 371 + y_shift, 857, 371 + y_shift, 857, 390 + y_shift),
        fill=TEAL,
        width=2,
    )
    draw.arc((729, 352 + y_shift, 773, 393 + y_shift), 190, 350, fill=TEAL, width=2)
    if focus == "controller" and phase >= 4:
        draw.line((739, 352 + y_shift, 767, 379 + y_shift), fill=RED, width=3)
    # Two bogie frames, each with a single brake-cylinder pressure sensor.
    for bi, (cx, label) in enumerate(((351, "BOGIE 1"), (815, "BOGIE 2"))):
        by = 528 + bogie_shift
        bogie_focus = active and (
            focus in ("brakes", "pneumatic") or (focus == "bcp-1" and bi == 0)
        )
        color = RED if bogie_focus else INK
        draw.rounded_rectangle(
            (cx - 140, by - 19, cx + 140, by + 39), 10, fill=WHITE, outline=color, width=3
        )
        draw.line((cx - 116, by + 3, cx + 116, by + 3), fill=RULE, width=2)
        line_text(draw, (cx - 60, by - 14), label, F13, INK)
        plate(draw, (cx - 52, by + 8, cx + 54, by + 34), outline=color, width=2)
        line_text(draw, (cx - 35, by + 13), "BCP 0" + str(bi + 1), F11, color)
        draw.line((cx, 475 + y_shift, cx, by - 20), fill=pneumatic_color, width=2)
    # Outer axles face the wagon ends; rear bogie reads inner then outer.
    # Each module displays its lateral L/R wheels as a schematic pair.
    for a, (cx, tag) in enumerate(((276, "B1-O"), (425, "B1-I"), (740, "B2-I"), (889, "B2-O"))):
        wy = 635 + wheel_shift
        axle_y = wy - 42 if exploded and phase >= 4 else wy
        is_axle = active and a == 0 and focus in ("axle", "wheel-left", "wheel-unknown")
        acolor = RED if is_axle else INK
        draw.line((cx, 566 + bogie_shift, cx, axle_y - 31), fill=acolor, width=3)
        draw.line((cx - 42, axle_y, cx + 42, axle_y), fill=acolor, width=3)
        wheel_offset = 45 if exploded and phase >= 4 else 29
        wheel_y = wy + 18 if exploded and phase >= 4 else wy
        for side, wx in (("L", cx - wheel_offset), ("R", cx + wheel_offset)):
            selected = is_axle and (
                focus == "wheel-unknown" or (focus == "wheel-left" and side == "L")
            )
            wc = RED if selected else INK
            if exploded and phase >= 4:
                # The hub/axle remains above; wheel discs drop away with
                # light dashed alignment lines to show physical separation.
                for guide_y in range(axle_y + 8, wheel_y - 26, 9):
                    draw.line((wx, guide_y, wx, guide_y + 4), fill=TEAL, width=1)
            draw.ellipse(
                (wx - 26, wheel_y - 26, wx + 26, wheel_y + 26), fill=WHITE, outline=wc, width=3
            )
            draw.ellipse(
                (wx - 5, wheel_y - 5, wx + 5, wheel_y + 5), fill=WHITE, outline=wc, width=2
            )
            line_text(
                draw, (wx - 5, wheel_y + 28 if exploded and phase >= 4 else wy + 30), side, F11, wc
            )
        plate(
            draw,
            (cx - 30, wy - 68, cx + 30, wy - 43),
            outline=RED if active and focus == "axle" and a == 0 else TEAL,
            width=2,
        )
        line_text(draw, (cx - 18, wy - 64), "GEN", F11, TEAL)
        line_text(draw, (cx - 25, wy + 56 if exploded and phase >= 4 else wy + 48), tag, F11, SUB)
        # Deliberately diagrammatic wiring from all four generators to battery bus.
        draw.line((cx, wy - 69, cx, 490 + y_shift), fill=TEAL, width=1)


def wrapped(draw, value, x, y, max_width, font=F13, fill=INK, line_height=18):
    current = ""
    for word in value.split():
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] > max_width and current:
            line_text(draw, (x, y), current, font, fill)
            y += line_height
            current = word
        else:
            current = candidate
    if current:
        line_text(draw, (x, y), current, font, fill)


def side_panel(draw, title, lead, lines, stage, final):
    line_text(draw, (1133, 219), "EVENT INTERPRETATION", F13, TEAL)
    draw.line((1133, 249, 1436, 249), fill=RULE, width=1)
    line_text(draw, (1133, 266), title, F20, INK)
    words = lead.split()
    run = ""
    yy = 306
    for word in words + [" "]:
        next_line = f"{run} {word}".strip()
        if draw.textbbox((0, 0), next_line, font=F15)[2] > 296 and run:
            line_text(draw, (1133, yy), run, F15, SUB)
            yy += 23
            run = word.strip()
        else:
            run = next_line
    if run.strip():
        line_text(draw, (1133, yy), run, F15, SUB)
    draw.line((1133, 374, 1436, 374), fill=RULE, width=1)
    for i, value in enumerate(lines):
        color = RED if i == 1 and stage >= 2 else (TEAL if i == 0 else INK)
        draw.ellipse((1135, 398 + i * 49, 1142, 405 + i * 49), fill=color)
        wrapped(draw, value, 1151, 392 + i * 49, 276, F13, color, 17)
    draw.line((1133, 612, 1436, 612), fill=RULE, width=1)
    label = ("BASELINE", "LOCALISE", "DEVELOPMENT", "CORROBORATE", "EVIDENCE", "INTERPRET")[stage]
    plate(draw, (1133, 628, 1435, 682), fill="#EFF6F4", outline=TEAL)
    line_text(draw, (1146, 639), f"{stage + 1:02d} / 06   {label}", F15, TEAL)
    if stage >= 4:
        text = final
        run = ""
        y = 692
        for word in text.split() + [" "]:
            proposed = f"{run} {word}".strip()
            if draw.textbbox((0, 0), proposed, font=F11)[2] > 287 and run:
                line_text(draw, (1135, y), run, F11, SUB)
                y += 15
                run = word.strip()
            else:
                run = proposed
        if run.strip() and y < 739:
            line_text(draw, (1135, y), run, F11, SUB)


def traces(draw, data, stage):
    # Values are schematic relative signal levels; no operational thresholds.
    x0, x1, y0, y1 = 69, 1077, 805, 887
    draw.rectangle((49, 782, 1454, 904), fill=WHITE, outline=RULE, width=2)
    line_text(draw, (67, 788), "SIGNAL EVIDENCE  /  QUALITATIVE TIME TRACE", F11, SUB)
    for i in range(9):
        x = x0 + i * (x1 - x0) / 8
        draw.line((x, y0, x, y1), fill=GRID, width=1)
    draw.line((x0, y1, x1, y1), fill=RULE, width=2)
    shown = [2, 4, 6, 8, 9, 9][stage]
    for j, (name, color, values) in enumerate(data):
        pts = []
        for i, val in enumerate(values[:shown]):
            x = int(x0 + i * (x1 - x0) / 8)
            if val is None:
                if len(pts) > 1:
                    draw.line(pts, fill=color, width=3, joint="curve")
                pts = []
                if i == 5:
                    draw.line((x - 5, 831, x + 5, 841), fill=color, width=3)
                    draw.line((x - 5, 841, x + 5, 831), fill=color, width=3)
                continue
            pts.append((x, int(y1 - val * (y1 - y0))))
        if len(pts) > 1:
            draw.line(pts, fill=color, width=3, joint="curve")
        yy = 806 + 26 * j
        draw.line((1102, yy + 6, 1132, yy + 6), fill=color, width=3)
        line_text(draw, (1141, yy), name, F13, INK)
    is_battery_outage = any(name.startswith("actual battery") for name, _, _ in data)
    is_controller_outage = any(name.startswith("controller supply") for name, _, _ in data)
    if (is_battery_outage or is_controller_outage) and stage >= 4:
        x = int(x0 + 6 * (x1 - x0) / 8)
        draw.line((x, 827, x, 873), fill=RED, width=2)
        line_text(draw, (x + 9, 833), "NO REPORTS", F11, RED)
    line_text(draw, (68, 886), "EARLIER", F11, SUB)
    line_text(draw, (1012, 886), "LATER →", F11, SUB)


def controller_traces(draw, stage):
    """Two reporting outcomes of one fault type; never interpolate the gaps."""
    draw.rectangle((49, 782, 1454, 904), fill=WHITE, outline=RULE, width=2)
    line_text(
        draw, (67, 788), "CONTROLLER POWER PATH  /  QUALITATIVE LAST-REPORT EVIDENCE", F11, SUB
    )

    def branch(x0, x1, title, supply, upstream, shown, gap_index, reset_index=None):
        draw.line((x0, 880, x1, 880), fill=RULE, width=2)
        line_text(draw, (x0, 807), title, F13, TEAL)
        for i in range(len(supply)):
            x = int(x0 + i * (x1 - x0) / (len(supply) - 1))
            draw.line((x, 825, x, 880), fill=GRID, width=1)
        for values, color in ((upstream, BLUE), (supply, RED)):
            points = []
            for i, value in enumerate(values[:shown]):
                x = int(x0 + i * (x1 - x0) / (len(values) - 1))
                if value is None:
                    if len(points) > 1:
                        draw.line(points, fill=color, width=3)
                    points = []
                    continue
                points.append((x, int(880 - value * 55)))
            if len(points) > 1:
                draw.line(points, fill=color, width=3)
        if shown > gap_index:
            gx = int(x0 + gap_index * (x1 - x0) / (len(supply) - 1))
            draw.line((gx, 834, gx, 870), fill=RED, width=2)
            line_text(draw, (gx + 8, 841), "GAP", F11, RED)
        if reset_index is not None and shown > reset_index:
            rx = int(x0 + reset_index * (x1 - x0) / (len(supply) - 1))
            draw.line((rx, 834, rx, 870), fill=TEAL, width=2)
            line_text(draw, (rx + 8, 857), "RESET", F11, TEAL)

    branch(
        68,
        548,
        "A / PERSISTENT",
        [0.78, 0.76, 0.62, 0.39, 0.16, None, None],
        [0.81, 0.81, 0.80, 0.82, 0.81, None, None],
        [2, 3, 6, 7, 7, 7][stage],
        5,
    )
    if stage >= 3:
        branch(
            598,
            1078,
            "B / BOUNDED",
            [0.78, 0.78, None, None, 0.76, 0.78, 0.79],
            [0.81, 0.81, None, None, 0.80, 0.81, 0.80],
            {3: 2, 4: 4, 5: 7}[stage],
            2,
            4 if stage == 5 else None,
        )
    else:
        line_text(draw, (598, 807), "B / BOUNDED  •  NEXT", F13, SUB)
    draw.line((1102, 818, 1132, 818), fill=RED, width=3)
    line_text(draw, (1141, 811), "controller supply", F13, INK)
    draw.line((1102, 845, 1132, 845), fill=BLUE, width=3)
    line_text(draw, (1141, 838), "upstream · last seen", F13, INK)
    line_text(draw, (70, 886), "NO READINGS ARE DRAWN DURING A REPORTING GAP", F11, SUB)


def scenario_frame(index, stage):
    s = SCENARIOS[index]
    image = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(image)
    layout(draw, s["name"], f"SCENARIO {index + 1:02d} / {len(SCENARIOS)}", s["scope"])
    engineering_wagon(draw, s["focus"], stage)
    side_panel(draw, "Wagon evidence", s["lead"], s["lines"], stage, s["end"])
    if s["slug"].startswith("12_controller"):
        controller_traces(draw, stage)
    else:
        traces(draw, s["traces"], stage)
    return image


def exploded_frame(stage):
    image = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(image)
    layout(
        draw,
        "One wagon / complete telemetry",
        f"ASSEMBLY 00 / {len(SCENARIOS)}",
        "ORTHOGRAPHIC EXPLODED DATA VIEW",
    )
    engineering_wagon(draw, phase=stage, exploded=True)
    owners = [
        ("01  WAGON", "route, GPS, speed, acceleration", "BPP, AR, SR, battery, power source"),
        ("02  CONTROLLER", "temperature and regulated supply", "health, uptime and counters"),
        ("03  BOGIES  ×2", "BCP pressure on each bogie", "one handbrake-equipped bogie"),
        ("04  AXLES  ×4", "generator; speed and RPM", "load and vibration per axle"),
        ("05  WHEELS  ×8", "left / right on each axle", "bearing temperature; diameter metadata"),
    ]
    line_text(draw, (1135, 219), "EVENT GRAIN", F13, TEAL)
    line_text(draw, (1135, 257), "1 wagon  ×  1 timestamp", F20, INK)
    draw.line((1135, 291, 1438, 291), fill=RULE, width=1)
    for i, (head, a, b) in enumerate(owners):
        y = 310 + i * 79
        colour = TEAL if i <= stage else SUB
        line_text(draw, (1135, y), head, F15, colour)
        line_text(draw, (1135, y + 24), a, F13, INK if i <= stage else SUB)
        line_text(draw, (1135, y + 42), b, F11, INK if i <= stage else SUB)
        draw.line((1135, y + 65, 1438, y + 65), fill=GRID, width=1)
    draw.rectangle((49, 782, 1454, 904), fill=WHITE, outline=RULE, width=2)
    line_text(draw, (70, 794), "NESTED EVENT", F13, TEAL)
    line_text(draw, (70, 834), "wagon → 2 bogies → 4 axles → 8 wheels", F23, INK)
    line_text(
        draw,
        (71, 872),
        "Parallel files: asset metadata  /  component observations  /  truth  /  manifest",
        F13,
        SUB,
    )
    return image


def save_animation(frames, path):
    timings = [1900, 1700, 1700, 1900, 2500, 3400]
    buffer = BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=timings,
        loop=0,
        optimize=False,
    )
    payload = buffer.getvalue()
    if not payload.startswith(b"GIF89a"):
        raise RuntimeError(f"GIF export failed: {path}")
    path.write_bytes(payload)


def write_logo():
    (ROOT / "fleetguard-logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="420" height="85" viewBox="0 0 420 85">'
        '<rect width="420" height="85" fill="#F7F7F3"/>'
        '<g stroke="#087C79" fill="none" stroke-width="3"><circle cx="43" cy="37" r="21"/>'
        '<circle cx="43" cy="37" r="8"/><path d="M11 37h11m42 0h11M43 30l4-6 5 7"/></g>'
        '<text x="87" y="35" fill="#223946" font-family="DejaVu Sans,sans-serif" '
        'font-size="26" font-weight="bold">FLEETGUARD</text>'
        '<text x="89" y="60" fill="#087C79" font-family="DejaVu Sans Mono,monospace" '
        'font-size="12">AI  /  RAIL TELEMETRY</text></svg>\n',
        encoding="utf-8",
    )


def write_contact_sheet():
    sheet = Image.new("RGB", (590 * 4, 390 * 4), "#E7EEF1")
    for i, path in enumerate(sorted(ROOT.glob("[01][0-9]_*.gif"))):
        with Image.open(path) as animated:
            animated.seek(animated.n_frames - 1)
            frame = animated.convert("RGB")
        frame.thumbnail((570, 355))
        tile = Image.new("RGB", (590, 390), WHITE)
        tile.paste(frame, ((590 - frame.width) // 2, 10))
        ImageDraw.Draw(tile).text((14, 367), path.stem, font=F13, fill=INK)
        sheet.paste(tile, ((i % 4) * 590, (i // 4) * 390))
    draw = ImageDraw.Draw(sheet)
    draw.rectangle((600, 1180, 2350, 1550), fill=WHITE, outline=RULE, width=2)
    line_text(draw, (655, 1230), "FLEETGUARD  /  ANOMALY ATLAS", F33, INK)
    draw.line((655, 1289, 2280, 1289), fill=TEAL, width=3)
    line_text(
        draw,
        (655, 1320),
        "1 wagon  •  12 scenario animations  •  component-level evidence",
        F20,
        INK,
    )
    line_text(
        draw,
        (655, 1375),
        "Controller outage: show the last reports and the reporting gap.",
        F18,
        SUB,
    )
    line_text(
        draw,
        (655, 1423),
        "Synthetic illustration  /  human investigation  /  no operational claims",
        F18,
        SUB,
    )
    sheet.save(ROOT / "contact_sheet.png")


def main():
    write_logo()
    save_animation([exploded_frame(s) for s in range(6)], ROOT / "00_wagon_exploded.gif")
    exploded_frame(5).save(ROOT / "00_wagon_exploded_poster.png")
    for n, s in enumerate(SCENARIOS):
        frames = [scenario_frame(n, stage) for stage in range(6)]
        save_animation(frames, ROOT / f"{s['slug']}.gif")
    write_contact_sheet()
    (ROOT / "README.md").write_text(
        "# FleetGuard animation assets\n\n"
        "Light engineering-style schematic animations for documentation. "
        "`00_wagon_exploded.gif` covers wagon hierarchy and telemetry ownership; "
        "`01`–`12` each cover a separate anomaly scenario. Each loop takes about 13 seconds. "
        "The exploded view separates the body, bogies, axles and wheels in sequence. "
        "Outer axles are nearest their respective wagon ends.\n\n"
        "The signal traces are illustrative sketches, not measured data or "
        "detector thresholds. The 3.0–4.2 V battery curve is a synthetic "
        "single-cell equivalent. Controller scenario 12 shows persistent sag and "
        "a bounded abrupt interruption with reboot under one anomaly type. Its "
        "reporting gaps contain no invented readings. "
        "The hub and GPS failures are outside this catalogue. `fleetguard-logo.svg` "
        "is the FleetGuard logo used in these animations.\n\n"
        "`contact_sheet.png` provides an overview of the complete set. "
        "To rebuild with Pillow and either DejaVu Sans or Windows Arial/Consolas: "
        "`python build_fleetguard_assets.py`.\n",
        encoding="utf-8",
    )
    print("Rendered wagon view and", len(SCENARIOS), "scenario GIFs to", ROOT)


if __name__ == "__main__":
    main()
