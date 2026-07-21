# AI Notepad — Vision-Based Desktop Automation

Automates a Notepad workflow on Windows using **dynamic visual grounding**: a ScreenSeekeR-inspired two-stage cascaded VLM system that locates desktop icons from plain-text descriptions, with BotCity template matching as a last-resort fallback (after VLM failure **or** after clicks that fail to open Notepad).

## How It Works

Per post (×10 from JSONPlaceholder):

```
Win+D once → desktop screenshot
       │
       ▼ (optional, CHECK_POPUPS)
 VLM popup check → dismiss with Enter / Escape / Tab+Enter if needed
       │
       ▼
 Coord cache HIT? ──yes──► double-click cached (x, y)
       │ no
       ▼
 Stage 1 — Planner (Gemini / OpenAI)
   Attempt 1: full screenshot → coarse bounding box
   Retries: quadrant scan (960×540) → box in screen coords
       │
       ▼
 Stage 2 — Grounder (crop of Stage 1 region)
   → precise center (x, y)
   Last VLM attempt: if Stage 2 fails → use Stage 1 box center
       │
       ▼ (if all VLM attempts raise)
 BotCity Template Match (OpenCV)
   → pixel match against resources/templates/
       │
       ▼
 Double-click → wait for Notepad
   (up to 3 launch retries with re-grounding)
       │
       ▼ (if launches still fail and TEMPLATE_MATCH_FALLBACK)
 Template match again → click
       │
       ▼
 Type post → Save As Desktop\tjm-project\post_{id}.txt → Close
```

Notes:

- **Win+D is a toggle** — the loop shows the desktop **once** per post, then reuses that view (a second Win+D would restore windows).
- With **`COORD_CACHE=false`**, the cursor moves to **top-center** before each screenshot so it does not sit on the icon.
- With **`COORD_CACHE=true`**, later posts skip VLM and reuse the first successful `(x, y)`.

## Prerequisites

| Requirement | Detail |
|---|---|
| OS | Windows 10 or 11 |
| Resolution | 1920 × 1080 (recommended) |
| Python | ≥ 3.11 |
| uv | [Install](https://docs.astral.sh/uv/getting-started/installation/) |
| Notepad shortcut | Must exist on the desktop before running |
| Google API Key | Free at [aistudio.google.com](https://aistudio.google.com) (default provider) |

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/youssof-elkassas/ai-notepad.git
cd ai-notepad

# 2. Install dependencies
uv sync

# For unit tests as well:
uv sync --group dev

# 3. Configure environment
cp .env.example .env
# Edit .env and paste your GOOGLE_API_KEY
```

## Run

```bash
uv run python -m src.main
```

Output files are saved to `Desktop\tjm-project\post_{id}.txt`.

## Feature flags and configuration

Boolean flags accept `true` / `false` (also `1` / `0` / `yes` / `on`). Defaults match [`.env.example`](.env.example).

### Feature flags

| Variable | Default | Meaning |
|---|---|---|
| `CHECK_POPUPS` | `true` | Before grounding, ask the VLM if a dialog is blocking and dismiss it |
| `VLM_TRACE` | `true` | Save every image sent to the VLM under `screenshots/vlm_trace/` |
| `COORD_CACHE` | `true` | Reuse grounded `(x, y)` across posts in the same process |
| `TEMPLATE_MATCH_FALLBACK` | `true` | BotCity match after VLM exhaustion **and** after failed Notepad launches |

### Grounding / VLM

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` or `openai` |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model when provider is Gemini |
| `OPENAI_MODEL` | `gpt-4o` | Model when provider is OpenAI |
| `MAX_GROUNDING_RETRIES` | `3` | VLM attempt budget inside `ground()` |
| `GROUNDING_QUERY` | `Notepad desktop shortcut icon` | Plain-English target |
| `GROUNDING_VISUAL_DESCRIPTION` | *(built-in Notepad hints)* | Optional look-and-feel bullets; use `\n` for newlines |

### Template matching

| Variable | Default | Meaning |
|---|---|---|
| `TEMPLATE_IMAGE_PATH` | `resources/templates/notepad_shortcut.png` | Template PNG for BotCity |
| `TEMPLATE_MATCHING` | `0.85` | Minimum match confidence (0–1) |

### Notepad automation

| Variable | Default | Meaning |
|---|---|---|
| `NOTEPAD_LAUNCH_WAIT` | `2.0` | Seconds to wait after double-click before checking the process |

Retarget **finding** another desktop icon by changing `GROUNDING_QUERY` (+ visual description) and regenerating / pointing `TEMPLATE_IMAGE_PATH`. The post-click workflow still opens **Notepad** and saves post text files.

## Testing

See [TESTS.md](TESTS.md) for unit tests and manual smoke scripts.

```bash
uv sync --group dev
uv run pytest
```

## Project Structure

```
ai-notepad/
├── src/
│   ├── main.py               # Orchestrator — entry point
│   ├── grounding/
│   │   ├── screenseeker.py   # Two-stage VLM grounding + coord cache + popup check
│   │   ├── template_match.py # BotCity template-matching fallback
│   │   ├── defaults.py       # Default query + visual description
│   │   └── annotator.py      # Bounding-box annotation for screenshots
│   ├── automation/
│   │   ├── screen.py         # Desktop screenshot capture (mss) + Region helpers
│   │   ├── mouse.py          # Mouse & keyboard control (pyautogui)
│   │   └── notepad.py        # Notepad open / type / save / close workflow
│   ├── api/
│   │   └── posts.py          # JSONPlaceholder API client
│   └── utils/
│       └── logger.py         # Structured logger with screenshot-on-error
├── resources/
│   └── templates/            # Template images for BotCity fallback
├── screenshots/              # Run artifacts, deliverables, vlm_trace/
├── tests/                    # Unit tests (see TESTS.md)
├── logs/                     # Runtime logs & error screenshots
├── scripts/
│   ├── test_grounding.py        # Manual VLM grounding smoke test
│   ├── capture_template.py      # Generate template PNG from VLM grounding
│   └── generate_screenshots.py  # Produce annotated deliverables by position
├── design_doc.md             # Part 1 — System design document
├── TESTS.md                  # How to run unit + manual smoke tests
├── pyproject.toml
└── .env.example
```

## Grounding Approach

Based on **ScreenSpot-Pro / ScreenSeekeR** ([arXiv:2504.07981](https://arxiv.org/abs/2504.07981)).

The VLM reasons about the screen like a human. Retries escalate from a full-screen Stage 1 to a **quadrant scan**. If Stage 2 still fails on the last attempt, the Stage 1 box center is used. If every VLM attempt raises, **BotCity** OpenCV template matching runs. Separately, if Notepad never opens after click retries, template matching is tried again before skipping the post.

This makes the system:

- **Position-invariant** — VLM works wherever the icon is placed
- **Description-driven** — change `GROUNDING_QUERY` (+ optional visual description)
- **Resilient** — template fallback on VLM failure and on failed launches
- **Pop-up aware** — optional VLM dialog detect/dismiss before grounding
- **Cacheable** — optional in-memory coords across posts in one run

Generate the default Notepad template once on Windows:

```bash
uv run python scripts/capture_template.py
```

## Discussion Prep

| Topic | Answer |
|---|---|
| Why VLM over template matching? | Primary path is zero-shot and position-invariant; template match is last resort (and launch-failure recovery) |
| Failure cases? | Tiny/ambiguous icons, VLM hallucination / bad Stage 1 center, network/API errors, missing or stale template |
| Retries? | Up to `MAX_GROUNDING_RETRIES` VLM attempts (full then quadrants); up to 3 open retries; then template if enabled |
| Performance? | ~few seconds per VLM call; Stage 2 uses a padded crop; coord cache avoids repeat grounding |
| Unexpected pop-ups? | With `CHECK_POPUPS=true`, VLM detects and dismisses without knowing appearance in advance |
| Retarget another icon? | Set `GROUNDING_QUERY` / visual description / template path — workflow after click still assumes Notepad |
