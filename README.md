# RoK Auto Assistant

Python desktop assistant for Rise of Kingdoms using ADB and OpenCV template matching.

## Requirements

- Windows 10/11
- Python 3.10+
- BlueStacks with ADB enabled
- Android Platform Tools
- Display target: 1280x720 (DPI setting is configured in BlueStacks)

## Setup

\`\`\`powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
\`\`\`

Edit \`ADB_PATH\` and \`DEFAULT_DEVICE\` in \`main.py\` if your local ADB path or BlueStacks port differs.

## Scout templates

Required files in \`templates/\`:

- \`btn_home.png\`
- \`scout_camp.png\`
- \`scout_icon.png\`
- \`btn_explore_1.png\`
- \`btn_explore_2.png\`
- \`btn_send_scout.png\`

The available-scout button is matched in BGR color and in a restricted list area so that the blue "ĐI" buttons are not treated as available scouts. \`btn_home\` is searched in the lower-left navigation area. Transparent PNG templates use alpha masks. The current \`btn_home.png\` contains the BlueStacks "Space" overlay; the recognizer applies a circular mask that ignores that label, but a clean crop without the overlay is still preferable.

## Coordinate handling

ADB screenshot dimensions are read from the PNG header. Android input dimensions are read from \`adb shell wm size\`. Tap and swipe coordinates are scaled between these spaces. The controller stops with an error when aspect ratios differ by more than 2%, rather than risking a wrong click.

The recognizer logs the detected template, confidence score, screenshot coordinate and Android input coordinate. It writes \`debug_<template>.png\` with a green match rectangle and a red click-center marker.

## Diagnose templates

Make sure the game is in the relevant screen, then run one template at a time:

\`\`\`powershell
python diagnose_templates.py --template btn_home
python diagnose_templates.py --template scout_icon
python diagnose_templates.py --template btn_explore_1
\`\`\`

For \`btn_home\`, display the world map. For \`scout_icon\`, select the Scout Camp so its action icon is visible. For \`btn_explore_1\`, open Scout Management. Review the corresponding \`debug_*.png\` before running automation.

## Current limitations

- Resource gathering is still a basic template-driven flow. March-slot OCR and occupied-node fallback are not complete.
- Template positions and ROIs are calibrated for the supplied 1280x720 BlueStacks game view and may need adjustment if the game viewport changes.
- No method can guarantee that game automation will avoid anti-cheat detection or account penalties. Use cautiously and follow the game's terms.
