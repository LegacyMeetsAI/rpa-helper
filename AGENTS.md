# AGENTS.md

This file defines the product and engineering guardrails for RPA Helper. Future agents should follow it before making implementation decisions.

## Project Identity

- Product name: RPA Helper.
- Product type: lightweight local desktop RPA assistant for hospital/clinic repetitive workflows.
- Target users: non-technical hospital staff and users who need repeated desktop clicks, text input, querying, and exporting.
- Core principle: the software watches the screen, finds images, and clicks or types. It must stay visual and local.
- Do not implement DOM automation, browser reverse engineering, captcha breaking, or Selenium-based control unless the user explicitly changes the product direction.

## Source Of Truth

- `rpa_helper_docs/` is the product and architecture source of truth.
- `rpa_helper_ui_mockup.jsx` is the primary UI style and interaction reference. Match its overall screen structure, navigation, card layout, spacing, rounded controls, icon-led actions, status panels, and workflow-management feel as closely as practical in PyQt6.
- If documents and mockup disagree, prefer `rpa_helper_docs/` for product scope, automation behavior, architecture, and development order; prefer the mockup for UI style, layout, page grouping, and visible interaction patterns.
- The mockup uses React, shadcn-style components, and lucide icons for design expression only. This does not change the intended implementation stack.

## Intended Tech Stack

- Language/runtime: Python.
- Desktop GUI: PyQt6.
- Automation: PyAutoGUI.
- Image processing: OpenCV and Pillow.
- Workflow config: YAML via PyYAML.
- Hotkeys: `keyboard`.
- OCR: PaddleOCR and PaddlePaddle, but only after MVP image-click workflow is working.
- Packaging: PyInstaller, later phase.

Avoid introducing a web app stack, Electron, Selenium, browser extensions, or remote services without explicit user approval.

## Architecture

Use the intended module flow:

```text
User operation
  -> GUI
  -> Workflow Engine
  -> Image Matcher
  -> Mouse Controller
  -> OCR Engine
  -> Logger
```

Recommended project layout:

```text
rpa_helper/
  main.py
  config/
  images/
  core/
  ui/
  logs/
  requirements.txt
```

Core responsibilities:

- Workflow Engine: read workflow YAML, execute ordered steps, manage run state.
- Image Matcher: locate template images on screen with OpenCV/PyAutoGUI style confidence support.
- Mouse Controller: move, click, and type through PyAutoGUI.
- Safety Manager: stop on ESC, stop on timeout, stop when required image is not found.
- Logger: write runtime execution details and errors to `runtime.log`.
- OCR Engine: recognize success/error states in later phases only.

## Workflow Contract

MVP workflow files are YAML and should support these step types:

- `click_image`
- `input_text`
- `wait`
- `confirm`

Example shape:

```yaml
name: "门诊查询"

steps:
  - type: "click_image"
    image: "images/query_menu.png"
    timeout: 10
    confidence: 0.8

  - type: "wait"
    seconds: 1

  - type: "input_text"
    text: "2026-05-23"

  - type: "confirm"
    message: "确认提交？"
```

Implementation should keep workflow files customer-customizable, while the UI should hide YAML from non-technical users.

## MVP Scope And Development Order

Build in this order:

1. Project skeleton and dependencies.
2. Image matching and image-click capability.
3. Mouse/keyboard control.
4. Workflow engine for `click_image`, `input_text`, `wait`, and `confirm`.
5. Runtime logging.
6. Hotkeys: F8 start, ESC stop.
7. PyQt6 GUI with workflow selection, start/stop controls, status, current step, and log output.

Defer until after MVP:

- OCR and status recognition.
- Workflow recorder.
- Full visual workflow editor.
- Screenshot manager.
- GUI polish beyond MVP needs.
- EXE packaging.

## UI Direction

The UI must be oriented toward non-technical users:

- Do not expose YAML or code as the main interaction.
- All routine configuration should be visual.
- Use the mockup as the main visual target: a calm slate-toned desktop app with a left navigation rail, large workspace panels, rounded cards, icon buttons, clear status chips, and dense but readable workflow rows.
- Preserve the mockup's page model: execution panel, workflow editor, recorder, screenshot manager, logs, settings, and save workflow.
- For MVP, the first useful UI should implement the mockup's execution panel and logs around workflow selection, start/stop controls, status, current step, and log output.
- Treat recorder, screenshot manager, and advanced editor as later-phase capabilities unless the user explicitly asks to prioritize them.
- When translating mockup elements to PyQt6, keep the same user-facing concepts and information hierarchy even if individual components differ.

## Safety And Reliability Rules

- Always provide a reliable stop path with ESC.
- Stop execution when an expected image cannot be found within timeout.
- Log every step, error reason, and execution time.
- Require explicit confirmation before potentially final submit/save actions when represented by `confirm` steps.
- Prefer deterministic local behavior over cloud or network dependencies.

## Dependency Baseline

Use `rpa_helper_docs/07_REQUIREMENTS.txt` as the baseline dependency list:

```text
pyautogui
opencv-python
pillow
keyboard
pyyaml
PyQt6
paddleocr
paddlepaddle
pyinstaller
```

For MVP, install/use only the dependencies needed for the current phase where practical. OCR and packaging dependencies can remain deferred until those features are implemented.

## Agent Behavior

- Keep changes aligned with the product: local visual RPA for hospital desktop workflows.
- Prefer small, testable modules in `core/` and PyQt6 UI code in `ui/`.
- Follow the React mockup for UI direction, but do not change the stack or product direction because of it.
- When adding new workflow behavior, update examples and validation together.
- When uncertain, choose the simpler MVP path described in the docs before adding phase-2 features.
