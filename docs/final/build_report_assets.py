"""Build the single compact Web evidence figure used by the five-page report."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[2]
GRAPH_SCREEN = WORKSPACE / "截屏2026-11-08 22.31.10.png"
ANSWER_SCREEN = WORKSPACE / "截屏2026-11-08 22.31.17.png"
OUTPUT = HERE / "final-report-web-evidence.png"
ARCHITECTURE_OUTPUT = HERE / "final-report-architecture.png"


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _band(label: str, image: Image.Image, width: int = 2520) -> Image.Image:
    image = image.resize((width, round(image.height * width / image.width)), Image.Resampling.LANCZOS)
    header = 74
    canvas = Image.new("RGB", (width, image.height + header), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((0, 0, width, header - 8), radius=18, fill="#e9efff")
    draw.text((28, 16), label, font=_font(34), fill="#1d3570")
    canvas.paste(image, (0, header))
    return canvas


def _architecture() -> None:
    width, height = 2520, 430
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    labels = [
        ("LoCoMo 对话", "session / turn"),
        ("结构化 Memory", "事实、时间、来源"),
        ("Hybrid Top-K", "BM25 + Embedding"),
        ("自适应 Graph", "拒答 / 列表题触发"),
        ("动态关系解析", "时间、状态、冲突"),
        ("DeepSeek 作答", "最短完整答案"),
        ("引用校验与 Web", "Memory ID 可追溯"),
    ]
    box_width, box_height, gap, start_x = 310, 190, 43, 24
    y = 102
    for index, (title, subtitle) in enumerate(labels):
        x = start_x + index * (box_width + gap)
        fill = "#eaf0ff" if index < 3 else ("#fff2df" if index == 3 else "#e8f8f2")
        outline = "#88a9f2" if index < 3 else ("#e4a85a" if index == 3 else "#64b99c")
        draw.rounded_rectangle(
            (x, y, x + box_width, y + box_height), radius=24,
            fill=fill, outline=outline, width=4,
        )
        title_font, subtitle_font = _font(32), _font(23)
        title_box = draw.textbbox((0, 0), title, font=title_font)
        subtitle_box = draw.textbbox((0, 0), subtitle, font=subtitle_font)
        draw.text(
            (x + (box_width - (title_box[2] - title_box[0])) / 2, y + 48),
            title, font=title_font, fill="#183361",
        )
        draw.text(
            (x + (box_width - (subtitle_box[2] - subtitle_box[0])) / 2, y + 113),
            subtitle, font=subtitle_font, fill="#4c5f78",
        )
        if index < len(labels) - 1:
            arrow_start = x + box_width + 7
            arrow_end = x + box_width + gap - 7
            center_y = y + box_height // 2
            draw.line((arrow_start, center_y, arrow_end, center_y), fill="#64789d", width=5)
            draw.polygon(
                ((arrow_end, center_y), (arrow_end - 15, center_y - 10),
                 (arrow_end - 15, center_y + 10)),
                fill="#64789d",
            )
    draw.text((24, 24), "可追溯的动态记忆问答链路", font=_font(34), fill="#1d3570")
    canvas.save(ARCHITECTURE_OUTPUT, optimize=True)


def main() -> None:
    graph = Image.open(GRAPH_SCREEN).convert("RGB")
    answer = Image.open(ANSWER_SCREEN).convert("RGB")

    graph_summary = graph.crop((180, 420, 2700, 675))
    coco_path = graph.crop((180, 1320, 2700, 1595))
    graph_panel = Image.new(
        "RGB", (2520, graph_summary.height + coco_path.height + 12), "white",
    )
    graph_panel.paste(graph_summary, (0, 0))
    graph_panel.paste(coco_path, (0, graph_summary.height + 12))

    answer_panel = answer.crop((170, 530, 2700, 1435))
    panels = [
        _band("A  Graph 有界多跳扩展：由 Shadow 记忆找回 Coco", graph_panel),
        _band("B  真实 DeepSeek 答案、Memory ID 与原始 session/turn", answer_panel),
    ]
    gap = 24
    total_height = sum(panel.height for panel in panels) + gap
    output = Image.new("RGB", (2520, total_height), "white")
    y = 0
    for panel in panels:
        output.paste(panel, (0, y))
        y += panel.height + gap
    output.save(OUTPUT, optimize=True)
    _architecture()
    print(OUTPUT)
    print(ARCHITECTURE_OUTPUT)


if __name__ == "__main__":
    main()
