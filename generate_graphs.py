from pathlib import Path
import csv
import json
import re
import subprocess
from collections import Counter, defaultdict
from statistics import mean, pstdev

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, Rectangle


FIGURE_DIR = Path("dissertation_material/figures")
FIGURE_DIR.mkdir(parents=True, exist_ok=True)
SURVEY_DIR = Path("dissertation_material/survey data")
VALIDATION_PATH = Path("dissertation_material/exceptional_validation_data.jsonl")
BENCHMARK_PATH = Path("dissertation_material/method_benchmark_manifest.csv")
COMPARISON_PATH = Path("dissertation_material/method_example_comparison.csv")
LIVE_BENCHMARK_PATH = Path("dissertation_material/live_benchmark_results_subset.csv")

NAVY = "#15324b"
BLUE = "#2563eb"
CYAN = "#0ea5e9"
GREEN = "#16a34a"
AMBER = "#d97706"
RED = "#dc2626"
INK = "#172033"
MUTED = "#64748b"
LINE = "#cbd5e1"
PAPER = "#f8fafc"
WHITE = "#ffffff"

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update(
    {
        "font.size": 11,
        "font.family": "DejaVu Sans",
        "axes.titleweight": "bold",
        "axes.edgecolor": "#d0d7de",
        "axes.labelcolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "grid.color": "#e5e7eb",
    }
)


def rounded_box(ax, xy, width, height, text, face=WHITE, edge=LINE, text_color=INK, lw=1.5):
    box = FancyBboxPatch(
        xy,
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.03",
        linewidth=lw,
        edgecolor=edge,
        facecolor=face,
    )
    ax.add_patch(box)
    ax.text(
        xy[0] + width / 2,
        xy[1] + height / 2,
        text,
        ha="center",
        va="center",
        color=text_color,
        fontsize=10,
        weight="bold" if face != WHITE else "normal",
        wrap=True,
    )


def label(ax, x, y, text, size=11, weight="bold", color=INK, ha="left"):
    ax.text(x, y, text, fontsize=size, weight=weight, color=color, ha=ha, va="center")


def save_canvas(fig, filename):
    fig.savefig(FIGURE_DIR / filename, dpi=300, bbox_inches="tight", facecolor=WHITE)
    plt.close(fig)


def plot_finetune_run_summary():
    labels = ["Run 621d", "Run 766f", "Run 3"]
    final_loss = [1.27, 1.36, 1.88]
    final_accuracy = [0.69, 0.67, 0.60]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.2, 4.8))
    x = np.arange(len(labels))

    ax1.bar(x, final_loss, color=[NAVY, BLUE, RED], edgecolor="none")
    ax1.set_title("Final Train Loss by Fine-Tuning Run")
    ax1.set_ylabel("Loss")
    ax1.set_xticks(x, labels)
    ax1.set_ylim(0, 2.2)
    ax1.spines[["top", "right"]].set_visible(False)
    for idx, value in enumerate(final_loss):
        ax1.text(idx, value + 0.05, f"{value:.2f}", ha="center", va="bottom", color=INK, weight="bold", fontsize=10)

    ax2.bar(x, final_accuracy, color=[GREEN, CYAN, AMBER], edgecolor="none")
    ax2.set_title("Final Mean Token Accuracy by Fine-Tuning Run")
    ax2.set_ylabel("Accuracy")
    ax2.set_xticks(x, labels)
    ax2.set_ylim(0, 0.8)
    ax2.spines[["top", "right"]].set_visible(False)
    for idx, value in enumerate(final_accuracy):
        ax2.text(idx, value + 0.02, f"{value:.2f}", ha="center", va="bottom", color=INK, weight="bold", fontsize=10)

    fig.tight_layout()
    save_canvas(fig, "finetune_run_summary.png")


def render_mermaid_diagrams():
    subprocess.run(["node", "render_mermaid_diagrams.mjs"], check=True)


def build_architecture_diagram():
    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    sections = [
        ("Ingestion Layer", 0.05, 0.72, 0.9, 0.18, ["Xero API", "OAuth2", "Data Fetcher"]),
        ("Core Processing", 0.05, 0.47, 0.9, 0.18, ["Parser", "DataMasker", "Decimal Rules", "Variance Analyzer"]),
        ("Agentic Synthesis", 0.05, 0.23, 0.9, 0.17, ["Analyst Agent", "Writer Agent", "QC Reviewer"]),
        ("Presentation Layer", 0.05, 0.04, 0.9, 0.12, ["Workbench", "Side-by-Side Review"]),
    ]
    for title, x, y, w, h, items in sections:
        ax.add_patch(Rectangle((x, y), w, h, facecolor=PAPER, edgecolor=LINE, linewidth=1.2))
        label(ax, x + 0.025, y + h - 0.035, title, size=12, color=NAVY)
        gap = w / (len(items) + 1)
        previous_right = None
        for idx, item in enumerate(items, start=1):
            bx = x + gap * idx - 0.075
            by = y + 0.04
            rounded_box(ax, (bx, by), 0.15, 0.065, item, face=WHITE, edge=BLUE)
            if previous_right is not None:
                ax.annotate(
                    "",
                    xy=(bx - 0.012, by + 0.032),
                    xytext=(previous_right + 0.012, by + 0.032),
                    arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.4, shrinkA=0, shrinkB=0),
                )
            previous_right = bx + 0.15
        if title != "Presentation Layer":
            ax.annotate("", xy=(0.5, y - 0.065), xytext=(0.5, y - 0.005), arrowprops=dict(arrowstyle="->", color=NAVY, lw=1.8))
    save_canvas(fig, "architecture_diagram.png")


def build_dashboard_wireframe():
    fig, ax = plt.subplots(figsize=(10.5, 6))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(Rectangle((0.02, 0.04), 0.96, 0.9, facecolor=WHITE, edgecolor=LINE, linewidth=1.5))
    ax.add_patch(Rectangle((0.02, 0.04), 0.18, 0.9, facecolor=NAVY, edgecolor=NAVY))
    label(ax, 0.05, 0.87, "PHM AI Review", size=13, color=WHITE)
    for y, text in [(0.75, "Clients"), (0.67, "Reports"), (0.59, "Settings")]:
        rounded_box(ax, (0.045, y - 0.025), 0.12, 0.045, text, face="#244963", edge="#40627a", text_color=WHITE, lw=1)
    label(ax, 0.24, 0.86, "Client Workbench", size=16, color=NAVY)
    rounded_box(ax, (0.24, 0.75), 0.42, 0.06, "Search clients, company number, year end", face=PAPER)
    rounded_box(ax, (0.69, 0.75), 0.22, 0.06, "Filter: pending review", face=PAPER)
    ax.add_patch(Rectangle((0.24, 0.18), 0.67, 0.48, facecolor=WHITE, edgecolor=LINE, linewidth=1.2))
    for i, header in enumerate(["Client", "Last sync", "Status", "Action"]):
        label(ax, 0.27 + i * 0.16, 0.61, header, size=10, color=MUTED)
    rows = [("Alpha Ltd", "04 May 2026", "Pending", "Generate"), ("Beta LLP", "03 May 2026", "Complete", "View"), ("Gamma Co", "01 May 2026", "Review", "Open")]
    for idx, row in enumerate(rows):
        y = 0.52 - idx * 0.11
        ax.plot([0.26, 0.89], [y + 0.045, y + 0.045], color="#e5e7eb", lw=1)
        for col, text in enumerate(row):
            color = BLUE if col == 3 else INK
            label(ax, 0.27 + col * 0.16, y, text, size=10, weight="normal", color=color)
    save_canvas(fig, "dashboard_wireframe.png")


def build_review_wireframe():
    fig, ax = plt.subplots(figsize=(10.5, 6))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(Rectangle((0.03, 0.08), 0.94, 0.84, facecolor=WHITE, edgecolor=LINE, linewidth=1.5))
    label(ax, 0.06, 0.86, "Synthesis Hub: Side-by-Side Review", size=15, color=NAVY)
    rounded_box(ax, (0.06, 0.72), 0.18, 0.055, "Client year end", face=PAPER)
    rounded_box(ax, (0.76, 0.72), 0.15, 0.055, "Confidence 94%", face="#ecfdf5", edge=GREEN, text_color=GREEN)
    ax.add_patch(Rectangle((0.06, 0.2), 0.41, 0.45, facecolor=PAPER, edgecolor=LINE, linewidth=1.2))
    ax.add_patch(Rectangle((0.53, 0.2), 0.38, 0.45, facecolor=WHITE, edgecolor=LINE, linewidth=1.2))
    label(ax, 0.08, 0.61, "Deterministic source data", size=11, color=NAVY)
    label(ax, 0.55, 0.61, "AI-generated review note", size=11, color=NAVY)
    for idx, text in enumerate(["Travel: GBP 1,200", "Office: GBP 450", "Payroll: GBP 5,000", "Variance > 10%"]):
        rounded_box(ax, (0.09, 0.52 - idx * 0.08), 0.31, 0.045, text, face=WHITE)
    for idx, width in enumerate([0.29, 0.31, 0.24, 0.28]):
        ax.add_patch(Rectangle((0.56, 0.52 - idx * 0.08), width, 0.025, facecolor="#dbeafe", edgecolor="#bfdbfe"))
    for x, text, color in [(0.55, "Approve", GREEN), (0.68, "Regenerate", AMBER), (0.83, "Save draft", BLUE)]:
        rounded_box(ax, (x, 0.12), 0.1, 0.045, text, face=color, edge=color, text_color=WHITE)
    save_canvas(fig, "review_wireframe.png")


def build_sidebar_wireframe():
    fig, ax = plt.subplots(figsize=(6.5, 5.8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(Rectangle((0.14, 0.08), 0.28, 0.82, facecolor=NAVY, edgecolor=NAVY))
    ax.add_patch(Rectangle((0.42, 0.08), 0.42, 0.82, facecolor=PAPER, edgecolor=LINE))
    label(ax, 0.19, 0.83, "PHM", size=15, color=WHITE)
    for y, text in [(0.68, "Clients"), (0.58, "Reports"), (0.48, "Settings")]:
        rounded_box(ax, (0.18, y), 0.19, 0.055, text, face="#244963", edge="#40627a", text_color=WHITE, lw=1)
    label(ax, 0.48, 0.78, "Navigation gives", size=12, color=NAVY)
    label(ax, 0.48, 0.70, "fast movement between", size=10, weight="normal", color=MUTED)
    label(ax, 0.48, 0.64, "clients, reports, and", size=10, weight="normal", color=MUTED)
    label(ax, 0.48, 0.58, "system settings.", size=10, weight="normal", color=MUTED)
    save_canvas(fig, "sidebar_wireframe.png")


def build_ui_flow():
    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    steps = [
        ("Login", 0.06),
        ("Client\nWorkbench", 0.23),
        ("Select\nPeriod", 0.41),
        ("Generate\nDraft", 0.59),
        ("Review\n& Edit", 0.76),
        ("Approve", 0.91),
    ]
    for idx, (text, x) in enumerate(steps):
        color = NAVY if idx in [0, 5] else WHITE
        text_color = WHITE if idx in [0, 5] else INK
        rounded_box(ax, (x - 0.055, 0.48), 0.11, 0.13, text, face=color, edge=NAVY, text_color=text_color)
        if idx < len(steps) - 1:
            ax.annotate("", xy=(steps[idx + 1][1] - 0.07, 0.545), xytext=(x + 0.07, 0.545), arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.8))
    ax.annotate("", xy=(0.59, 0.44), xytext=(0.76, 0.44), arrowprops=dict(arrowstyle="<-", color=AMBER, lw=1.8, connectionstyle="arc3,rad=-0.3"))
    label(ax, 0.64, 0.31, "Feedback loop for regeneration", size=10, weight="normal", color=AMBER, ha="center")
    save_canvas(fig, "ui_flow_diagram.png")


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def method_sort_key(label):
    prompt_order = {
        "GPT-5.4 Zero-Shot": 0,
        "GPT-5.4 Single-Shot": 1,
        "GPT-5.4 Few-Shot": 2,
    }
    if label in prompt_order:
        return (0, prompt_order[label])
    match = re.search(r"(\d+)$", label)
    if label.startswith("GPT-4.1 Fine-Tuned") and match:
        return (1, int(match.group(1)))
    return (2, label)


def numeric_or_zero(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def live_benchmark_rows():
    if not LIVE_BENCHMARK_PATH.exists() or LIVE_BENCHMARK_PATH.stat().st_size == 0:
        return []
    rows = read_csv(LIVE_BENCHMARK_PATH)
    return [row for row in rows if not row.get("error")]


def extract_relevant_excerpt(text, limit=260):
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return ""
    segments = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+|###\s+", cleaned) if segment.strip()]
    keywords = (
        "citb",
        "levy",
        "director",
        "loan",
        "overdrawn",
        "gdpr",
        "compliance",
        "share issue",
        "share premium",
        "share capital",
        "investment",
        "paperwork",
        "allotment",
        "wip",
        "cash accounting",
        "query",
    )
    for segment in segments:
        lowered = segment.lower()
        if any(keyword in lowered for keyword in keywords):
            return segment[:limit].rstrip()
    return cleaned[:limit].rstrip()


def build_live_benchmark_artifacts():
    rows = live_benchmark_rows()
    if not rows:
        return

    by_method = defaultdict(list)
    for row in rows:
        by_method[row["method_label"]].append(row)

    manifest_rows = []
    for label in sorted(by_method, key=method_sort_key):
        method_rows = by_method[label]
        latencies = [float(row["latency_seconds"]) for row in method_rows]
        prompt_tokens = [numeric_or_zero(row.get("prompt_tokens")) for row in method_rows]
        completion_tokens = [numeric_or_zero(row.get("completion_tokens")) for row in method_rows]
        total_tokens = [numeric_or_zero(row.get("total_tokens")) for row in method_rows]
        manifest_rows.append(
            {
                "method_id": method_rows[0]["method_id"],
                "method_label": label,
                "method_family": method_rows[0]["method_family"],
                "run_count": len(method_rows),
                "mean_generation_seconds": f"{mean(latencies):.3f}",
                "std_generation_seconds": f"{pstdev(latencies):.3f}",
                "mean_prompt_tokens": f"{mean(prompt_tokens):.1f}",
                "mean_completion_tokens": f"{mean(completion_tokens):.1f}",
                "mean_total_tokens": f"{mean(total_tokens):.1f}",
                "notes": f"Measured on {len(method_rows)} live validation cases.",
            }
        )
    write_csv(
        BENCHMARK_PATH,
        manifest_rows,
        [
            "method_id",
            "method_label",
            "method_family",
            "run_count",
            "mean_generation_seconds",
            "std_generation_seconds",
            "mean_prompt_tokens",
            "mean_completion_tokens",
            "mean_total_tokens",
            "notes",
        ],
    )

    preferred_cases = ["val_064", "val_079", "val_084"]
    comparison_case = next(
        (case_id for case_id in preferred_cases if any(row["example_id"] == case_id for row in rows)),
        max(Counter(row["example_id"] for row in rows), key=lambda example_id: Counter(row["example_id"] for row in rows)[example_id]),
    )
    rows_for_case = [row for row in rows if row["example_id"] == comparison_case]
    rows_by_label = {row["method_label"]: row for row in rows_for_case}

    comparison_rows = [
        {
            "method_order": 0,
            "method_label": "Gold accountant note",
            "comparison_role": "Reference",
            "example_id": comparison_case,
            "response_excerpt": extract_relevant_excerpt(rows_for_case[0]["gold_text"]),
        }
    ]
    for order, label in enumerate(sorted(rows_by_label, key=method_sort_key), start=1):
        row = rows_by_label[label]
        comparison_rows.append(
            {
                "method_order": order,
                "method_label": label,
                "comparison_role": row["method_family"],
                "example_id": comparison_case,
                "response_excerpt": extract_relevant_excerpt(row["output_text"]),
            }
        )
    write_csv(
        COMPARISON_PATH,
        comparison_rows,
        ["method_order", "method_label", "comparison_role", "example_id", "response_excerpt"],
    )


def build_manual_time_chart():
    rows = read_csv(SURVEY_DIR / "Survey1_Baseline_Data.csv")
    order = ["Less than 1 hour", "1 - 2 hours", "2 - 4 hours", "4+ hours"]
    counts = Counter(row["Time_Spent_Manual"] for row in rows)

    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    values = [counts[label] for label in order]
    ax.bar(order, values, color=[GREEN, CYAN, AMBER, RED], edgecolor="none")
    ax.set_title("Manual Drafting Time Before AI Assistance")
    ax.set_xlabel("Reported time per review note")
    ax.set_ylabel("Number of respondents")
    ax.set_ylim(0, max(values) + 1)
    ax.spines[["top", "right"]].set_visible(False)
    for idx, value in enumerate(values):
        ax.text(idx, value + 0.08, str(value), ha="center", va="bottom", color=INK, weight="bold")
    save_canvas(fig, "survey_manual_time.png")


def build_manual_time_by_experience_chart():
    rows = read_csv(SURVEY_DIR / "Survey1_Baseline_Data.csv")
    exp_order = ["0-2 years", "3-5 years", "6-10 years", "10+ years"]
    time_order = ["Less than 1 hour", "1 - 2 hours", "2 - 4 hours", "4+ hours"]
    color_map = {
        "Less than 1 hour": GREEN,
        "1 - 2 hours": CYAN,
        "2 - 4 hours": AMBER,
        "4+ hours": RED,
    }

    counts = {experience: Counter() for experience in exp_order}
    for row in rows:
        counts[row["Experience"]][row["Time_Spent_Manual"]] += 1

    fig, ax = plt.subplots(figsize=(9.2, 5.2))
    x = np.arange(len(exp_order))
    bottom = np.zeros(len(exp_order))
    for bucket in time_order:
        values = np.array([counts[experience][bucket] for experience in exp_order])
        ax.bar(x, values, bottom=bottom, color=color_map[bucket], edgecolor="none", label=bucket)
        bottom += values

    ax.set_xticks(x, exp_order)
    ax.set_ylabel("Number of respondents")
    ax.set_xlabel("Experience band")
    ax.set_title("Manual Drafting Time by Accountant Experience")
    ax.legend(frameon=True, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    save_canvas(fig, "manual_time_by_experience.png")


def build_survey_score_chart():
    rows = read_csv(SURVEY_DIR / "Survey2_AI_Evaluation_Data.csv")
    fields = [
        ("Professionalism", "PartA_Q1_Professional"),
        ("Stylistic fit", "PartA_Q2_Stylistic"),
        ("Narrative flow", "PartA_Q3_Flow"),
        ("Variance handling", "PartB_Q4_Variances"),
        ("Mandatory notes", "PartB_Q5_Mandatory"),
        ("Trust", "PartB_Q6_Trust"),
    ]
    labels = [label for label, _ in fields]
    means = [np.mean([float(row[field]) for row in rows]) for _, field in fields]

    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    y = np.arange(len(labels))
    ax.barh(y, means, color=BLUE, alpha=0.86)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 5)
    ax.set_xlabel("Mean Likert score (1-5)")
    ax.set_title("AI-Generated Notes: Accountant Evaluation Scores")
    ax.spines[["top", "right"]].set_visible(False)
    for idx, value in enumerate(means):
        ax.text(value + 0.05, idx, f"{value:.1f}", va="center", color=INK, weight="bold")
    save_canvas(fig, "survey_ai_scores.png")


def build_edit_reason_chart():
    rows = read_csv(SURVEY_DIR / "Survey2_AI_Evaluation_Data.csv")
    counts = Counter(row["PartC_Primary_Edit_Reason"] for row in rows)
    labels = list(counts.keys())
    values = [counts[label] for label in labels]
    colors = [GREEN if "No edits" in label else BLUE if label == "Formatting" else AMBER if label == "Stylistic Mismatch" else RED for label in labels]

    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    ax.bar(labels, values, color=colors, edgecolor="none")
    ax.set_title("Primary Reason for Human Edits")
    ax.set_ylabel("Number of respondents")
    ax.set_ylim(0, max(values) + 1)
    ax.tick_params(axis="x", rotation=25)
    ax.spines[["top", "right"]].set_visible(False)
    for idx, value in enumerate(values):
        ax.text(idx, value + 0.08, str(value), ha="center", va="bottom", color=INK, weight="bold")
    save_canvas(fig, "survey_edit_reasons.png")


def validation_stats():
    section_markers = {
        "P&L": "### P&L",
        "Corporation Tax": "### CORPORATION TAX",
        "Balance Sheet": "### BALANCE SHEET",
        "Profit Bridge": "### WHERE HAS THE PROFIT GONE?",
        "Personal Tax": "### PERSONAL TAX",
        "Recommendations": "### OUR RECOMMENDATIONS",
        "Tax Saved": "### TAX SAVED",
    }
    section_counts = Counter()
    amount_mentions = []
    char_counts = []
    record_count = 0
    with open(VALIDATION_PATH, encoding="utf-8") as handle:
        for line in handle:
            record_count += 1
            obj = json.loads(line)
            messages = obj.get("messages", [])
            assistant_text = "\n".join(msg.get("content", "") for msg in messages if msg.get("role") == "assistant")
            user_text = "\n".join(msg.get("content", "") for msg in messages if msg.get("role") == "user")
            for label, marker in section_markers.items():
                if marker in assistant_text:
                    section_counts[label] += 1
            amount_mentions.append(user_text.count("£") + assistant_text.count("£"))
            char_counts.append(len(user_text) + len(assistant_text))
    return record_count, section_counts, amount_mentions, char_counts


def build_validation_coverage_chart():
    record_count, section_counts, _, _ = validation_stats()
    labels = list(section_counts.keys())
    values = [section_counts[label] for label in labels]

    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    y = np.arange(len(labels))
    ax.barh(y, values, color=NAVY, alpha=0.88)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, record_count)
    ax.set_xlabel(f"Validation examples containing section (n={record_count})")
    ax.set_title("Validation Corpus Coverage by Review Note Section")
    ax.spines[["top", "right"]].set_visible(False)
    for idx, value in enumerate(values):
        ax.text(value + 1, idx, str(value), va="center", color=INK, weight="bold")
    save_canvas(fig, "validation_section_coverage.png")


def build_prompt_engineering_matrix():
    record_count, _, amount_mentions, char_counts = validation_stats()
    strategies = ["Zero-shot", "Single-shot", "Few-shot"]
    runs = [record_count] * 3
    example_counts = [0, 1, 3]

    fig, ax1 = plt.subplots(figsize=(9.4, 5.2))
    x = np.arange(len(strategies))
    bars = ax1.bar(x, runs, color=[Navy if False else NAVY, BLUE, CYAN], alpha=0.88, label="Validation cases")
    ax1.set_ylabel("Validation cases")
    ax1.set_ylim(0, record_count + 20)
    ax1.set_xticks(x, strategies)
    ax1.set_title("GPT-5.4 Prompt Engineering Validation Matrix")
    ax1.spines[["top", "right"]].set_visible(False)
    for bar in bars:
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2, f"{int(bar.get_height())}", ha="center", weight="bold")

    ax2 = ax1.twinx()
    ax2.plot(x, example_counts, color=AMBER, marker="o", linewidth=2.5, label="In-context examples")
    ax2.set_ylabel("In-context examples")
    ax2.set_ylim(0, 4)
    ax2.spines["top"].set_visible(False)
    ax2.grid(False)

    avg_amounts = np.mean(amount_mentions)
    avg_chars = np.mean(char_counts)
    ax1.text(
        0.02,
        0.92,
        f"Corpus: {record_count} cases | avg GBP mentions: {avg_amounts:.1f} | avg chars/case: {avg_chars:.0f}",
        transform=ax1.transAxes,
        fontsize=9,
        color=MUTED,
    )
    save_canvas(fig, "prompt_engineering_validation_matrix.png")


def build_validation_complexity_chart():
    _, _, amount_mentions, char_counts = validation_stats()
    fig, ax = plt.subplots(figsize=(9.2, 5.3))
    ax.scatter(char_counts, amount_mentions, s=42, color=BLUE, alpha=0.72, edgecolor=WHITE, linewidth=0.5)
    ax.axvline(np.mean(char_counts), color=AMBER, linestyle="--", linewidth=1.8, label=f"Mean chars: {np.mean(char_counts):.0f}")
    ax.axhline(np.mean(amount_mentions), color=GREEN, linestyle="--", linewidth=1.8, label=f"Mean GBP mentions: {np.mean(amount_mentions):.1f}")
    ax.set_title("Validation Case Complexity")
    ax.set_xlabel("Characters across prompt and gold note")
    ax.set_ylabel("GBP mentions across prompt and gold note")
    ax.legend(frameon=True, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    save_canvas(fig, "validation_case_complexity.png")


def build_method_timing_chart():
    rows = read_csv(BENCHMARK_PATH)
    labels = [row["method_label"] for row in rows]
    latencies = [float(row["mean_generation_seconds"]) for row in rows]
    stddevs = [float(row.get("std_generation_seconds") or 0) for row in rows]
    total_tokens = [float(row.get("mean_total_tokens") or 0) for row in rows]
    colors = [NAVY if row["method_id"].startswith("ft_") else CYAN for row in rows]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10.4, 7.8), sharex=True, height_ratios=[1.15, 0.9])
    x = np.arange(len(labels))

    ax1.bar(x, latencies, color=colors, edgecolor="none", yerr=stddevs, capsize=4, ecolor=MUTED)
    ax1.set_ylabel("Seconds per generated note")
    ax1.set_title("Live Mean Generation Time Across Prompting and Fine-Tuned Methods")
    ax1.spines[["top", "right"]].set_visible(False)
    for idx, value in enumerate(latencies):
        ax1.text(idx, value + 0.08, f"{value:.1f}s", ha="center", va="bottom", color=INK, weight="bold", fontsize=9)

    ax2.bar(x, total_tokens, color=[BLUE if row["method_id"].startswith("gpt54") else "#9ca3af" for row in rows], edgecolor="none")
    ax2.set_ylabel("Mean total tokens")
    ax2.set_xticks(x, labels, rotation=20, ha="right")
    ax2.spines[["top", "right"]].set_visible(False)
    for idx, value in enumerate(total_tokens):
        ax2.text(idx, value + max(total_tokens) * 0.015, f"{value:.0f}", ha="center", va="bottom", color=INK, weight="bold", fontsize=9)

    fig.tight_layout()
    save_canvas(fig, "method_timing_comparison.png")


def build_method_output_comparison():
    rows = read_csv(COMPARISON_PATH)
    fig, ax = plt.subplots(figsize=(14, 9.4))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    label_y = 0.94
    case_id = rows[0].get("example_id", "comparison case") if rows else "comparison case"
    ax.text(0.03, label_y, "Method", fontsize=12, weight="bold", color=NAVY, va="top")
    ax.text(0.27, label_y, f"Live response excerpt from {case_id}", fontsize=12, weight="bold", color=NAVY, va="top")

    y = 0.88
    row_h = 0.095
    for idx, row in enumerate(rows):
        face = PAPER if idx % 2 == 0 else WHITE
        edge = "#d7dee7"
        ax.add_patch(Rectangle((0.02, y - row_h + 0.01), 0.96, row_h - 0.015, facecolor=face, edgecolor=edge, linewidth=1))
        ax.text(0.035, y - 0.018, row["method_label"], fontsize=10.5, weight="bold", color=INK, va="top")
        ax.text(0.035, y - 0.055, row["comparison_role"], fontsize=9, color=MUTED, va="top")
        ax.text(0.27, y - 0.018, row["response_excerpt"], fontsize=9.5, color=INK, va="top", wrap=True)
        y -= row_h

    fig.tight_layout()
    save_canvas(fig, "method_output_comparison.png")


def main():
    render_mermaid_diagrams()
    build_live_benchmark_artifacts()
    plot_finetune_run_summary()
    build_dashboard_wireframe()
    build_review_wireframe()
    build_sidebar_wireframe()
    build_manual_time_chart()
    build_manual_time_by_experience_chart()
    build_survey_score_chart()
    build_edit_reason_chart()
    build_validation_coverage_chart()
    build_validation_complexity_chart()
    build_prompt_engineering_matrix()
    build_method_timing_chart()
    build_method_output_comparison()
    print(f"Generated dissertation figures in {FIGURE_DIR}")


if __name__ == "__main__":
    main()
