# AI Notepad — Vision-Based Desktop Automation

Automates a Notepad workflow on Windows using **dynamic visual grounding**: a ScreenSeekeR-inspired two-stage cascaded VLM system that can locate any desktop icon or UI element from a plain-text description — no template matching, no hardcoded coordinates.

## How It Works

```
Desktop Screenshot
       │
       ▼
 Stage 1 — Planner (Gemini 2.5 Flash)
   → Identifies rough bounding region of the target icon
       │
       ▼
 Stage 2 — Grounder (Gemini 2.5 Flash on cropped region)
   → Pinpoints exact center (x, y) within the crop
       │
       ▼
 Mouse double-click → Notepad opens
       │
       ▼
 Type post content → Save → Close → Repeat ×10
```

## Prerequisites

| Requirement | Detail |
|---|---|
| OS | Windows 10 or 11 |
| Resolution | 1920 × 1080 |
| Python | ≥ 3.11 |
| uv | [Install](https://docs.astral.sh/uv/getting-started/installation/) |
| Notepad shortcut | Must exist on the desktop before running |
| Google API Key | Free at [aistudio.google.com](https://aistudio.google.com) |

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/youssof-elkassas/ai-notepad.git
cd ai-notepad

# 2. Install dependencies
uv sync

# 3. Configure environment
cp .env.example .env
# Edit .env and paste your GOOGLE_API_KEY
```

## Run

```bash
uv run python -m src.main
```

Output files are saved to `Desktop\tjm-project\post_{id}.txt`.

## Project Structure

```
ai-notepad/
├── src/
│   ├── main.py               # Orchestrator — entry point
│   ├── grounding/
│   │   ├── screenseeker.py   # Two-stage VLM grounding engine
│   │   └── annotator.py      # Bounding-box annotation for screenshots
│   ├── automation/
│   │   ├── screen.py         # Desktop screenshot capture (mss)
│   │   ├── mouse.py          # Mouse & keyboard control (pyautogui)
│   │   └── notepad.py        # Notepad open / type / save / close workflow
│   ├── api/
│   │   └── posts.py          # JSONPlaceholder API client
│   └── utils/
│       └── logger.py         # Structured logger with screenshot-on-error
├── screenshots/              # Annotated grounding deliverables
├── logs/                     # Runtime error screenshots & logs
├── scripts/
│   └── generate_screenshots.py  # Utility to produce the 3 annotated deliverables
├── design_doc.md             # Part 1 — System design document
├── pyproject.toml
└── .env.example
```

## Grounding Approach

Based on **ScreenSpot-Pro / ScreenSeekeR** ([arXiv:2504.07981](https://arxiv.org/abs/2504.07981)).

The key insight: instead of matching pixels, we ask a vision-language model to reason about the screen like a human would. This makes the system:

- **Position-invariant** — works wherever the icon is placed
- **Description-driven** — target any element with plain English
- **Pop-up resilient** — the VLM can identify and dismiss unexpected dialogs without prior knowledge of their appearance
- **Generalizable** — change one string to target a different icon, button, or field

## Discussion Prep

| Topic | Answer |
|---|---|
| Why VLM over template matching? | Position-invariant, zero-shot, handles any visual context |
| Failure cases? | Very small icons, visually ambiguous screens, VLM hallucination |
| Performance? | ~2-3s per grounding call; mitigated by cropped Stage 2 |
| Scaling? | Swap the `query` string — engine is already fully general |
| Unexpected pop-ups? | VLM detects and dismisses without knowing appearance in advance |
