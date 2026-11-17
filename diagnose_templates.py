import argparse
from pathlib import Path

from adb_controller import ADBController
from image_recognition import ImageRecognizer


ADB_PATH = r"C:\Users\nghia\platform-tools\adb.exe"
SERIAL = "127.0.0.1:6610"

ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = ROOT / "templates"

TEMPLATES = [
    "btn_home",
    "scout_camp",
    "scout_icon",
    "btn_explore_1",
    "btn_explore_2",
    "btn_send_scout",
]

ROI_BY_TEMPLATE = {
    "btn_home": (0, 440, 230, 720),
    "btn_explore_1": (820, 240, 1190, 690),
    "btn_send_scout": (760, 100, 1280, 720),
}


def main():
    parser = argparse.ArgumentParser(
        description="Chẩn đoán template bằng cùng recognizer của ứng dụng."
    )
    parser.add_argument("--template", choices=TEMPLATES)
    parser.add_argument("--threshold", type=float, default=0.82)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Tìm tất cả nút cùng tên; hữu ích với btn_explore_1.",
    )
    args = parser.parse_args()

    adb = ADBController(adb_path=ADB_PATH)
    adb.connect(SERIAL)

    screenshot_path = ROOT / "diagnostic_screen.png"
    adb.screenshot(str(screenshot_path))
    print(f"Screenshot: {screenshot_path}")
    print(f"Screenshot size: {adb.screenshot_size}")
    print(f"Android input size: {adb.get_display_size()}")

    recognizer = ImageRecognizer(
        template_dir=str(TEMPLATE_DIR),
        threshold=args.threshold,
    )

    selected = [args.template] if args.template else TEMPLATES

    for name in selected:
        template_path = TEMPLATE_DIR / f"{name}.png"
        if not template_path.is_file():
            print(f"{name}: MISSING ({template_path})")
            continue

        roi = ROI_BY_TEMPLATE.get(name)

        if args.all or name == "btn_explore_1":
            matches = recognizer.locate_all(
                str(screenshot_path),
                name,
                threshold=args.threshold,
                roi=roi,
                max_matches=12,
                yellow_only=(name == "btn_explore_1"),
            )
            print(f"\n{name}: {len(matches)} match(es)")
            for index, match in enumerate(matches, start=1):
                print(
                    f"  {index}. score={match['score']:.3f}, "
                    f"center=({match['x']},{match['y']}), "
                    f"box={match['box']}, "
                    f"yellow={match.get('yellow_ratio')}"
                )
            output = recognizer.draw_debug_all(
                str(screenshot_path),
                name,
                matches,
            )
            print(f"  debug={output}")
        else:
            match = recognizer.locate(
                str(screenshot_path),
                name,
                threshold=args.threshold,
                roi=roi,
            )
            print(f"\n{name}: {match}")
            print(f"  best={recognizer.last_scores.get(name)}")
            if match:
                print(
                    "  debug="
                    + str(
                        recognizer.draw_debug(
                            str(screenshot_path),
                            name,
                            match,
                        )
                    )
                )

    print("\nHoàn tất chẩn đoán.")


if __name__ == "__main__":
    main()
