# /// script
# requires-python = ">=3.11"
# dependencies = ["Pillow>=11,<13"]
# ///
"""Render the README explainer: uv run --script scripts/render_workflow.py.

This is an illustrated workflow, not captured execution or measured timings.
Pillow is only needed to regenerate the images, not to run Incident Lab.
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"
WIDTH, HEIGHT, FPS, SCALE = 1120, 570, 8, 2
BG, INK, MUTED = "#f5f7fb", "#17243b", "#5a6980"
BLUE, GREEN, AMBER, RED = "#3864df", "#147d65", "#a26915", "#c04d57"
LINE = "#c7d0df"
FONTS = {
    size: ImageFont.load_default(size=size * SCALE) for size in (14, 15, 17, 18, 20, 22, 24, 32)
}

NODES = {
    "alert": (40, 172, 216, 274),
    "evidence": (256, 172, 432, 274),
    "policy": (472, 172, 648, 274),
    "approval": (688, 172, 864, 274),
    "recover": (904, 172, 1080, 274),
    "abstain": (472, 338, 648, 412),
    "stop": (688, 338, 864, 412),
}
LABELS = {
    "alert": ("Alert", "HTTP 503", "Orders unavailable"),
    "evidence": ("Evidence", "Logs + metrics", "Changes + docs"),
    "policy": ("Validate", "Cause + citations", "Evidence required"),
    "approval": ("Approve", "Operator review", "Expiring approval"),
    "recover": ("Recover", "Restore config", "HTTP checks"),
    "abstain": ("Abstain", "Human review", ""),
    "stop": ("No action", "Invalid approval", ""),
}
EDGES = [
    ("alert", "evidence"),
    ("evidence", "policy"),
    ("policy", "approval"),
    ("approval", "recover"),
    ("policy", "abstain"),
    ("approval", "stop"),
]
# duration, active node, completed nodes, active edge, title, detail, accent
STAGES = [
    (
        1.8,
        "alert",
        [],
        None,
        "01 / A service stops responding",
        "The local orders service returns HTTP 503 after an invalid configuration change.",
        RED,
    ),
    (
        2.4,
        "evidence",
        ["alert"],
        ("alert", "evidence"),
        "02 / Investigate through read-only tools",
        "Collect logs, metrics and deployment history; retrieve relevant runbooks.",
        BLUE,
    ),
    (
        2.4,
        "policy",
        ["alert", "evidence"],
        ("evidence", "policy"),
        "03 / Require evidence for the diagnosis",
        "A configuration-validation error and a preceding configuration change support the hypothesis.",
        BLUE,
    ),
    (
        2.4,
        "approval",
        ["alert", "evidence", "policy"],
        ("policy", "approval"),
        "04 / Wait for an operator",
        "The model has no action tools. A separate workflow proposes the exact configuration restore.",
        BLUE,
    ),
    (
        2.4,
        "recover",
        ["alert", "evidence", "policy", "approval"],
        ("approval", "recover"),
        "05 / Restore only after valid approval",
        "Approval, parameters, evidence freshness and state revision must pass before execution.",
        GREEN,
    ),
    (
        3.0,
        "recover",
        ["alert", "evidence", "policy", "approval"],
        None,
        "Recovery verified: HTTP 200 / 200 / 200",
        "Actual HTTP probes check recovery. The proposal, approval and outcome remain in the audit.",
        GREEN,
    ),
    (
        3.2,
        "abstain",
        ["alert", "evidence"],
        ("policy", "abstain"),
        "Alternate path / Evidence missing or conflicting?",
        "Abstain and request human review. An unsupported diagnosis is rejected by the backend.",
        AMBER,
    ),
    (
        3.2,
        "stop",
        ["alert", "evidence", "policy"],
        ("approval", "stop"),
        "Alternate path / Approval expired or state changed?",
        "No action. Recovery requires a valid approval for the exact proposal and current state.",
        AMBER,
    ),
]


def scaled(values):
    return tuple(value * SCALE for value in values)


def text(draw, xy, value, size=17, fill=INK, anchor=None):
    draw.text(scaled(xy), value, font=FONTS[size], fill=fill, anchor=anchor)


def rounded_box(draw, bounds, *, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(
        scaled(bounds), radius=radius * SCALE, fill=fill, outline=outline, width=width * SCALE
    )


def circle(draw, bounds, fill):
    draw.ellipse(scaled(bounds), fill=fill)


def path_points(source, target):
    left = NODES[source]
    right = NODES[target]
    if target in {"abstain", "stop"}:
        return ((left[0] + left[2]) / 2, left[3]), ((right[0] + right[2]) / 2, right[1])
    return (left[2], (left[1] + left[3]) / 2), (right[0], (right[1] + right[3]) / 2)


def arrow(draw, source, target, color=LINE, width=2):
    start, end = path_points(source, target)
    draw.line((scaled(start), scaled(end)), fill=color, width=width * SCALE)
    x, y = end
    if target in {"abstain", "stop"}:
        points = ((x - 4, y - 8), (x, y), (x + 4, y - 8))
    else:
        points = ((x - 8, y - 4), (x, y), (x - 8, y + 4))
    draw.line(tuple(scaled(point) for point in points), fill=color, width=width * SCALE)


def frame(stage_index, progress):
    _, active, completed, edge, heading, detail, accent = STAGES[stage_index]
    image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), BG)
    draw = ImageDraw.Draw(image)
    text(draw, (40, 30), "Incident Lab", 32)
    text(draw, (40, 75), "Evidence first. Operator-controlled recovery.", 20, MUTED)
    rounded_box(draw, (843, 37, 1080, 73), radius=18, fill="#e8edf8")
    text(draw, (961, 55), "LOCAL SANDBOX", 17, BLUE, "mm")

    for source, target in EDGES:
        passed = source in completed and (target in completed or target == active)
        arrow(draw, source, target, BLUE if passed else LINE, 3 if passed else 2)
    if edge:
        arrow(draw, *edge, accent, 3)
    for key, bounds in NODES.items():
        x1, y1, x2, y2 = bounds
        selected, passed = key == active, key in completed
        color = accent if selected else GREEN if passed else MUTED
        fill = "#ffffff"
        if selected:
            fill = (
                "#fff6e6"
                if accent == AMBER
                else "#edf3ff"
                if accent == BLUE
                else "#eff8f5"
                if accent == GREEN
                else "#fff0f1"
            )
        rounded_box(
            draw,
            bounds,
            radius=14,
            fill=fill,
            outline=color if selected or passed else "#d6deea",
            width=3 if selected else 1,
        )
        title, first, second = LABELS[key]
        if key not in {"abstain", "stop"}:
            step = list(NODES).index(key) + 1
            circle(
                draw,
                (x1, y1 - 33, x1 + 23, y1 - 10),
                fill=color if selected or passed else "#e4e9f2",
            )
            text(
                draw,
                (x1 + 11, y1 - 21),
                str(step),
                14,
                "#ffffff" if selected or passed else MUTED,
                "mm",
            )
            text(draw, (x1 + 13, y1 + 15), title, 24, INK)
            text(draw, (x1 + 13, y1 + 51), first, 17, color)
            text(draw, (x1 + 13, y1 + 76), second, 17, MUTED)
        else:
            text(draw, ((x1 + x2) / 2, y1 + 23), title, 24, color, "mm")
            text(draw, ((x1 + x2) / 2, y1 + 53), first, 17, MUTED, "mm")
    text(draw, (477, 302), "Missing / conflicting", 17, MUTED)
    text(draw, (702, 302), "Not authorized", 17, MUTED)

    if edge:
        start, end = path_points(*edge)
        fraction = (progress * 2) % 1
        x = start[0] + (end[0] - start[0]) * fraction
        y = start[1] + (end[1] - start[1]) * fraction
        circle(draw, (x - 5, y - 5, x + 5, y + 5), fill=accent)

    rounded_box(draw, (40, 442, 1080, 534), radius=14, fill="#ffffff", outline="#d6deea")
    rounded_box(draw, (40, 458, 44, 517), radius=2, fill=accent)
    text(draw, (60, 459), heading, 24, accent)
    text(draw, (60, 499), detail, 18, MUTED)
    for i in range(len(STAGES)):
        x = 958 + i * 14
        circle(draw, (x, 423, x + 6, 429), fill=accent if i == stage_index else "#d2dbea")
    text(
        draw,
        (40, 550),
        "Illustrated workflow / not a live recording",
        17,
        MUTED,
    )
    return image


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # A shared palette prevents color changes between frames.
    swatches = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE * len(STAGES)))
    for index in range(len(STAGES)):
        swatches.paste(frame(index, 0.5), (0, index * HEIGHT * SCALE))
    palette = swatches.quantize(colors=256)
    frames = []
    for index, (duration, *_) in enumerate(STAGES):
        count = math.ceil(duration * FPS)
        frames.extend(
            frame(index, i / count).quantize(palette=palette, dither=Image.Dither.NONE)
            for i in range(count)
        )
    frames[0].save(
        OUT / "incident-workflow.gif",
        save_all=True,
        append_images=frames[1:],
        duration=1000 // FPS,
        loop=0,
        optimize=True,
        disposal=1,
    )
    frame(5, 0.5).save(OUT / "incident-workflow.png", optimize=True)
    print(
        f"Rendered {len(frames)} frames; GIF: {(OUT / 'incident-workflow.gif').stat().st_size:,} bytes"
    )


if __name__ == "__main__":
    main()
