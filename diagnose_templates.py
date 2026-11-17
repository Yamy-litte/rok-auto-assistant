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

# ROI khớp với vị trí UI trong game 1280x720.
ROI_BY_TEMPLATE = {
    "btn_home": (0, 440, 230, 720),
    "btn_explore_1": (800, 140, 1190, 720),
    "btn_send_scout": (760, 100, 1280, 720),
}


def main():
    parser = argparse.ArgumentParser(
        description="Chẩn đoán template theo cùng thuật toán với RoK Assistant."
    )
    parser.add_argument(
        "--template",
        choices=TEMPLATES,
        help="Chỉ kiểm tra một template ở trạng thái màn hình hiện tại.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.82,
        help="Ngưỡng nhận diện mặc định (default: 0.82).",
    )
    args = parser.parse_args()

    adb = ADBController(adb_path=ADB_PATH)
    adb.connect(SERIAL)

    screenshot_path = ROOT / "diagnostic_screen.png"
    adb.screenshot(str(screenshot_path))
    print(f"Screenshot: {screenshot_path}")
    print(f"Kích thước screenshot: {adb.screenshot_size}")
    print(f"Kích thước Android: {adb.get_display_size()}")

    recognizer = ImageRecognizer(
        template_dir=str(TEMPLATE_DIR),
        threshold=args.threshold,
    )

    selected = [args.template] if args.template else TEMPLATES

    print("\n========== TEMPLATE DIAGNOSTIC ==========")
    for name in selected:
        path = TEMPLATE_DIR / f"{name}.png"
        if not path.is_file():
            print(f"{name}: MISSING FILE ({path})")
            continue

        roi = ROI_BY_TEMPLATE.get(name)
        match = recognizer.locate(
            str(screenshot_path),
            name,
            threshold=0.0,
            roi=roi,
        )
        info = recognizer.last_scores.get(name, {})
        score = info.get("score", -1)
        scale = info.get("scale")
        location = info.get("location")

        print(
            f"{name}: score={score:.4f}, "
            f"scale={scale}, location={location}, roi={roi}"
        )

        if match is not None:
            debug_path = recognizer.draw_debug(
                str(screenshot_path),
                name,
                match,
            )
            print(
                f"  MATCH center=({match['x']},{match['y']}), "
                f"box={match['box']}, debug={debug_path}"
            )
        else:
            print("  Không tìm được vị trí ứng viên.")

    print("\nHoàn tất. Hãy kiểm tra diagnostic_screen.png và debug_*.png.")


if __name__ == "__main__":
    main()
