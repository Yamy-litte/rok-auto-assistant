
import subprocess
from pathlib import Path
import cv2

# Đường dẫn ADB của máy bạn
ADB = r"C:\Users\nghia\platform-tools\adb.exe"
SERIAL = "127.0.0.1:6610"

ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = ROOT / "templates"

TEMPLATES = [
    "scout_camp",
    "scout_icon",
    "explore",
    "explore_confirm",
    "send",
    "home_button"
]

SCALES = [0.75, 0.85, 0.95, 1.0, 1.05, 1.15, 1.25]


def capture_screen():

    print("\nĐang chụp màn hình BlueStacks...")

    result = subprocess.run(
        [
            ADB,
            "-s", SERIAL,
            "exec-out",
            "screencap",
            "-p"
        ],
        capture_output=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.decode(errors="ignore")
        )

    path = ROOT / "diagnostic_screen.png"
    path.write_bytes(result.stdout)

    return path


def compare_template(screen, template_path):

    template = cv2.imread(
        str(template_path),
        cv2.IMREAD_GRAYSCALE
    )

    if template is None:
        raise ValueError("Không đọc được ảnh template.")

    best_score = -1
    best_location = None
    best_size = None

    th, tw = template.shape[:2]
    sh, sw = screen.shape[:2]

    for scale in SCALES:

        new_w = int(tw * scale)
        new_h = int(th * scale)

        if new_w > sw or new_h > sh:
            continue

        resized = cv2.resize(
            template,
            (new_w, new_h),
            interpolation=cv2.INTER_AREA
        )

        result = cv2.matchTemplate(
            screen,
            resized,
            cv2.TM_CCOEFF_NORMED
        )

        _, score, _, location = cv2.minMaxLoc(result)

        if score > best_score:
            best_score = score
            best_location = location
            best_size = (new_w, new_h)

    return best_score, best_location, best_size


def main():

    print("=" * 55)
    print("       ROK TEMPLATE DIAGNOSTIC")
    print("=" * 55)

    if not TEMPLATE_DIR.is_dir():
        raise FileNotFoundError(TEMPLATE_DIR)

    screenshot_path = capture_screen()

    screen = cv2.imread(
        str(screenshot_path),
        cv2.IMREAD_COLOR
    )

    if screen is None:
        raise ValueError("Không đọc được screenshot.")

    gray_screen = cv2.cvtColor(
        screen,
        cv2.COLOR_BGR2GRAY
    )

    print("\nKích thước screenshot:")
    print(gray_screen.shape[::-1])

    debug = screen.copy()

    for name in TEMPLATES:

        path = TEMPLATE_DIR / f"{name}.png"

        print("\n" + "-" * 45)
        print("Template:", name)

        if not path.is_file():
            print("KẾT QUẢ: KHÔNG TÌM THẤY FILE")
            continue

        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)

        if image is None:
            print("KẾT QUẢ: ẢNH BỊ LỖI")
            continue

        print("Kích thước template:", image.shape[::-1])

        if image.shape == gray_screen.shape:
            print("CẢNH BÁO: Template đang là ảnh toàn màn hình.")

        score, location, size = compare_template(
            gray_screen,
            path
        )

        print(f"Điểm nhận diện: {score:.4f}")

        if score >= 0.85:
            print("ĐÁNH GIÁ: Khớp tốt")

        elif score >= 0.70:
            print("ĐÁNH GIÁ: Có thể khớp, cần kiểm tra")

        elif score >= 0.50:
            print("ĐÁNH GIÁ: Khớp yếu")

        else:
            print("ĐÁNH GIÁ: Không khớp")

        if location and size and score >= 0.50:

            x, y = location
            w, h = size

            cv2.rectangle(
                debug,
                (x, y),
                (x + w, y + h),
                (0, 255, 0),
                2
            )

            cv2.putText(
                debug,
                f"{name}: {score:.2f}",
                (x, max(20, y - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1
            )

    output = ROOT / "diagnostic_result.png"

    cv2.imwrite(str(output), debug)

    print("\n" + "=" * 55)
    print("ĐÃ HOÀN TẤT KIỂM TRA")
    print("Ảnh gốc:", screenshot_path)
    print("Ảnh kết quả:", output)
    print("=" * 55)


if __name__ == "__main__":
    main()
