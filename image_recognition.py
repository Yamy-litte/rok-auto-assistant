
from pathlib import Path
import cv2
import numpy as np


class ImageRecognizer:
    """Multi-scale template matching có hỗ trợ PNG alpha mask."""

    def __init__(self, template_dir="templates", threshold=0.82):
        self.base_dir = Path(__file__).resolve().parent
        requested = Path(template_dir)

        self.template_dir = (
            requested if requested.is_absolute()
            else (self.base_dir / requested).resolve()
        )

        self.threshold = threshold
        self._cache = {}
        self.last_scores = {}

        if not self.template_dir.is_dir():
            raise FileNotFoundError(self.template_dir)

    def load(self, name):
        if name not in self._cache:
            path = self.template_dir / f"{name}.png"

            raw = cv2.imread(
                str(path),
                cv2.IMREAD_UNCHANGED
            )

            if raw is None:
                raise FileNotFoundError(
                    f"Không đọc được template: {path}"
                )

            # Tách ảnh và alpha mask.
            if raw.ndim == 3 and raw.shape[2] == 4:
                bgr = raw[:, :, :3]
                alpha = raw[:, :, 3]
                mask = np.where(
                    alpha > 16, 255, 0
                ).astype(np.uint8)
            elif raw.ndim == 3:
                bgr = raw
                mask = None
            else:
                bgr = cv2.cvtColor(
                    raw, cv2.COLOR_GRAY2BGR
                )
                mask = None

            gray = cv2.cvtColor(
                bgr, cv2.COLOR_BGR2GRAY
            )

            # Bỏ qua nhãn bàn phím Space của BlueStacks.
            if name == "btn_home" and mask is not None:
                h, w = mask.shape

                x1 = min(70, w)
                x2 = w
                y1 = min(80, h)
                y2 = min(117, h)

                mask[y1:y2, x1:x2] = 0

            if mask is not None and cv2.countNonZero(mask) < 20:
                raise ValueError(
                    f"Alpha mask không hợp lệ: {name}"
                )

            self._cache[name] = {
                "image": gray,
                "mask": mask
            }

            print(
                f"[OpenCV] Loaded {name}: "
                f"{gray.shape[::-1]}, "
                f"alpha_mask={mask is not None}"
            )

        return self._cache[name]

    def locate(self, screenshot_path, name, threshold=None):
        screen = cv2.imread(
            str(screenshot_path),
            cv2.IMREAD_GRAYSCALE
        )

        if screen is None:
            raise ValueError(
                f"Không đọc được screenshot: {screenshot_path}"
            )

        data = self.load(name)
        template = data["image"]
        mask = data["mask"]

        sh, sw = screen.shape
        th, tw = template.shape

        # Tìm kiếm đa tỷ lệ.
        if name == "scout_icon":
            scales = [
                0.45, 0.50, 0.55, 0.60,
                0.65, 0.70, 0.75, 0.80,
                0.85, 0.90, 0.95, 1.0,
                1.05, 1.15, 1.25, 1.35
            ]
        elif name == "btn_home":
            scales = [
                0.55, 0.65, 0.75, 0.85,
                0.95, 1.0, 1.05, 1.15, 1.25
            ]
        else:
            scales = [
                0.75, 0.85, 0.95, 1.0,
                1.05, 1.15, 1.25
            ]

        best_score = -1.0
        best_location = None
        best_size = None
        best_scale = None

        for scale in scales:
            nw = int(tw * scale)
            nh = int(th * scale)

            if nw <= 0 or nh <= 0:
                continue

            if nw > sw or nh > sh:
                continue

            interpolation = (
                cv2.INTER_AREA
                if scale < 1
                else cv2.INTER_CUBIC
            )

            resized = cv2.resize(
                template,
                (nw, nh),
                interpolation=interpolation
            )

            if mask is not None:
                resized_mask = cv2.resize(
                    mask,
                    (nw, nh),
                    interpolation=cv2.INTER_NEAREST
                )

                result = cv2.matchTemplate(
                    screen,
                    resized,
                    cv2.TM_CCORR_NORMED,
                    mask=resized_mask
                )
            else:
                result = cv2.matchTemplate(
                    screen,
                    resized,
                    cv2.TM_CCOEFF_NORMED
                )

            result = np.nan_to_num(
                result,
                nan=-1.0,
                posinf=-1.0,
                neginf=-1.0
            )

            _, score, _, location = cv2.minMaxLoc(result)

            if score > best_score:
                best_score = float(score)
                best_location = location
                best_size = (nw, nh)
                best_scale = scale

        self.last_scores[name] = {
            "score": best_score,
            "scale": best_scale,
            "location": best_location
        }

        limit = (
            self.threshold
            if threshold is None
            else threshold
        )

        if best_location is None or best_score < limit:
            return None

        x, y = best_location
        w, h = best_size

        return {
            "x": x + w // 2,
            "y": y + h // 2,
            "score": best_score,
            "scale": best_scale,
            "box": (x, y, w, h)
        }

    def locate_color(self, screenshot_path, name, threshold=None):
        # Giữ tương thích với các tác vụ đang gọi locate_color.
        return self.locate(
            screenshot_path,
            name,
            threshold
        )

    def exists(self, screenshot_path, name, threshold=None):
        return self.locate(
            screenshot_path,
            name,
            threshold
        ) is not None
