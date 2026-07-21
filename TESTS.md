# Testing

## Unit tests

Automated tests cover pure core logic and mocked grounding retries — not live VLM
calls, desktop capture, or the full Notepad automation loop.

```bash
uv sync --group dev
uv run pytest
```

Run a single file:

```bash
uv run pytest tests/test_ground_retries.py -q
```

### What is covered

| Area | Examples |
|------|----------|
| Parsing | `_parse_json` (raw + markdown fences) |
| Coord formatting | `_normalize_bbox_if_needed` (0–1000 scale vs pixels) |
| Geometry | `Region.padded`, `map_local_to_screen` |
| Config / paths | `GROUNDING_QUERY`, visual description, template path/threshold |
| Trace naming | `_save_vlm_trace` filename pattern when `VLM_TRACE` is on |
| Grounding selection | mocked `ground()` retries, Stage 1 box-center last attempt, template fallback |

### Intentionally excluded

- Live Gemini / OpenAI API calls
- Real `mss` desktop screenshots
- BotCity OpenCV matching against a live screen
- End-to-end `python -m src.main`

## Manual smoke tests

These scripts exercise the real VLM / desktop and need Windows + `.env` (`GOOGLE_API_KEY`).

| Script | Purpose |
|--------|---------|
| `uv run python scripts/test_grounding.py` | One-shot grounding smoke test; writes `screenshots/screenshot_*.png` |
| `uv run python scripts/generate_screenshots.py <position>` | Deliverable annotated shots (`top_left` / `center` / `bottom_right`) |
| `uv run python scripts/capture_template.py` | Crop a template PNG for BotCity fallback |

## Env flags that affect grounding tests / smokes

| Flag | Role |
|------|------|
| `GROUNDING_QUERY` | Plain-English target for VLM |
| `GROUNDING_VISUAL_DESCRIPTION` | Optional visual hints (`\n` for newlines) |
| `COORD_CACHE` | Reuse grounded `(x, y)` across posts in one run |
| `TEMPLATE_MATCH_FALLBACK` | BotCity last resort after VLM (and after failed launches) |
| `VLM_TRACE` | Save images sent to the VLM under `screenshots/vlm_trace/` |
| `CHECK_POPUPS` | Extra VLM call to detect blocking dialogs before grounding |
