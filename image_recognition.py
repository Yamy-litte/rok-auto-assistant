from pathlib import Path

import cv2
import numpy as np


class ImageRecognizer:
    """
    Multi-scale template matching.
    - Dùng BGR để phân biệt nút vàng Thăm dò với nút xanh ĐI.
    - Hỗ trợ alpha mask cho PNG trong suốt.
    - Có mask riêng cho btn_home để bỏ nhãn Space của BlueStacks.
    - Hỗ trợ ROI nhằm hạn chế nhận nhầm biểu tượng ở vùng khác.
    """

    def __init__(self, template_dir="templates", threshold=0.82):
        self.base_dir = Path(__file__).resolve().parent
        requested = Path(template_dir)

        self.template_dir = (
            requested
            if requested.is_absolute()
            else (self.base_dir / requested).resolve()
        )

        self.threshold = float(threshold)
        self._cache = {}
        self.last_scores = {}

        self.scales = {
            "btn_home": [
                0.40, 0.50, 0.60, 0.70, 0.80,
                0.90, 1.00, 1.10, 1.20, 1.30,
            ],
            "scout_icon": [
                0.30, 0.35, 0.40, 0.45, 0.50,
                0.60, 0.70, 0.80, 0.90, 1.00,
                1.10, 1.20, 1.30, 1.40,
            ],
            "scout_camp": [
                0.55, 0.65, 0.75, 0.85, 0.95,
                1.00, 1.05, 1.15, 1.25,
            ],
            "btn_explore_1": [
                0.65, 0.75, 0.85, 0.95, 1.00,
                1.05, 1.15, 1.25, 1.35,
            ],
        }
        self.default_scales = [
            0.65, 0.75, 0.85, 0.95, 1.00,
            1.05, 1.15, 1.25,
        ]

        if not self.template_dir.is_dir():
            raise FileNotFoundError(
                f"Không tìm thấy thư mục template: {self.template_dir}"
            )

    def load(self, name):
        if name in self._cache:
            return self._cache[name]

        path = self.template_dir / f"{name}.png"
        raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)

        if raw is None:
            raise FileNotFoundError(
                f"Không đọc được template: {path}"
            )

        if raw.ndim == 2:
            color = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
            alpha_mask = None
            anchor = (raw.shape[1] / 2.0, raw.shape[0] / 2.0)
        elif raw.shape[2] == 4:
            color = raw[:, :, :3]
            alpha = raw[:, :, 3]
            alpha_mask = np.where(
                alpha > 16, 255, 0
            ).astype(np.uint8)

            ys, xs = np.where(alpha_mask > 0)
            if len(xs) == 0:
                raise ValueError(
                    f"Template không có vùng nhìn thấy: {name}"
                )

            # Tâm vùng có alpha, không tính phần trong suốt.
            anchor = (
                float(xs.mean()),
                float(ys.mean()),
            )

            if cv2.countNonZero(alpha_mask) == alpha_mask.size:
                alpha_mask = None
        else:
            color = raw[:, :, :3]
            alpha_mask = None
            anchor = (color.shape[1] / 2.0, color.shape[0] / 2.0)

        mask = alpha_mask

        # btn_home.png có nhãn phím Space đè lên góc phải dưới.
        # Chỉ so khớp vùng nút tròn và bỏ vùng nhãn Space.
        if name == "btn_home":
            height, width = color.shape[:2]
            mask = np.zeros((height, width), dtype=np.uint8)
            center = (
                round(width * 0.50),
                round(height * 0.52),
            )
            axes = (
                max(1, round(width * 0.43)),
                max(1, round(height * 0.38)),
            )
            cv2.ellipse(
                mask, center, axes,
                0, 0, 360, 255, -1,
            )

            # Vùng nhãn Space theo template hiện có.
            sx1 = round(width * 0.48)
            sy1 = round(height * 0.53)
            sx2 = round(width * 0.99)
            sy2 = round(height * 0.75)
            mask[sy1:sy2, sx1:sx2] = 0

            # Click vào tâm nút tròn, không lấy tâm cả ảnh crop.
            anchor = (
                width * 0.50,
                height * 0.52,
            )

        if mask is not None and cv2.countNonZero(mask) < 20:
            raise ValueError(
                f"Mask template không hợp lệ: {name}"
            )

        data = {
            "color": color,
            "mask": mask,
            "anchor": anchor,
        }
        self._cache[name] = data

        print(
            f"[OpenCV] Loaded {name}: "
            f"{color.shape[1]}x{color.shape[0]}, "
            f"masked={mask is not None}, anchor={anchor}"
        )
        return data

    @staticmethod
    def _clip_roi(roi, width, height):
        if roi is None:
            return 0, 0, width, height

        x1, y1, x2, y2 = map(int, roi)
        x1 = max(0, min(x1, width))
        y1 = max(0, min(y1, height))
        x2 = max(0, min(x2, width))
        y2 = max(0, min(y2, height))

        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"ROI không hợp lệ: {roi}")

        return x1, y1, x2, y2

    def locate(self, screenshot_path, name, threshold=None, roi=None):
        screen = cv2.imread(
            str(screenshot_path),
            cv2.IMREAD_COLOR,
        )
        if screen is None:
            raise ValueError(
                f"Không đọc được screenshot: {screenshot_path}"
            )

        screen_h, screen_w = screen.shape[:2]
        roi_x1, roi_y1, roi_x2, roi_y2 = self._clip_roi(
            roi, screen_w, screen_h
        )
        search_area = screen[roi_y1:roi_y2, roi_x1:roi_x2]

        data = self.load(name)
        template = data["color"]
        mask = data["mask"]
        anchor_x, anchor_y = data["anchor"]

        area_h, area_w = search_area.shape[:2]
        template_h, template_w = template.shape[:2]

        best_score = -1.0
        best_location = None
        best_size = None
        best_scale = None

        scales = self.scales.get(name, self.default_scales)

        for scale in scales:
            new_w = max(1, round(template_w * scale))
            new_h = max(1, round(template_h * scale))

            if new_w > area_w or new_h > area_h:
                continue

            interpolation = (
                cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
            )
            resized = cv2.resize(
                template,
                (new_w, new_h),
                interpolation=interpolation,
            )

            if mask is not None:
                resized_mask = cv2.resize(
                    mask,
                    (new_w, new_h),
                    interpolation=cv2.INTER_NEAREST,
                )
                method = cv2.TM_CCORR_NORMED
                result = cv2.matchTemplate(
                    search_area,
                    resized,
                    method,
                    mask=resized_mask,
                )
            else:
                # BGR matching giữ khác biệt màu, đặc biệt nút vàng/xanh.
                result = cv2.matchTemplate(
                    search_area,
                    resized,
                    cv2.TM_CCOEFF_NORMED,
                )

            result = np.nan_to_num(
                result,
                nan=-1.0,
                posinf=-1.0,
                neginf=-1.0,
            )
            _, score, _, location = cv2.minMaxLoc(result)

            if score > best_score:
                best_score = float(score)
                best_location = location
                best_size = (new_w, new_h)
                best_scale = scale

        self.last_scores[name] = {
            "score": best_score,
            "scale": best_scale,
            "location": best_location,
            "roi": (roi_x1, roi_y1, roi_x2, roi_y2),
        }

        limit = self.threshold if threshold is None else float(threshold)
        if best_location is None or best_score < limit:
            return None

        x, y = best_location
        width, height = best_size

        return {
            "x": roi_x1 + x + round(anchor_x * best_scale),
            "y": roi_y1 + y + round(anchor_y * best_scale),
            "score": best_score,
            "scale": best_scale,
            "box": (
                roi_x1 + x,
                roi_y1 + y,
                width,
                height,
            ),
        }

    def locate_color(self, screenshot_path, name, threshold=None, roi=None):
        """Color-aware matching; unlike the old version this keeps BGR channels."""
        return self.locate(
            screenshot_path,
            name,
            threshold=threshold,
            roi=roi,
        )

    def draw_debug(self, screenshot_path, name, match):
        image = cv2.imread(
            str(screenshot_path),
            cv2.IMREAD_COLOR,
        )
        if image is None or match is None:
            return None

        x, y, width, height = match["box"]
        cv2.rectangle(
            image,
            (x, y),
            (x + width, y + height),
            (0, 255, 0),
            2,
        )
        cv2.drawMarker(
            image,
            (match["x"], match["y"]),
            (0, 0, 255),
            cv2.MARKER_CROSS,
            20,
            2,
        )
        cv2.putText(
            image,
            f"{name}: {match['score']:.3f}",
            (x, max(22, y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 0),
            2,
        )

        output = self.base_dir / f"debug_{name}.png"
        cv2.imwrite(str(output), image)
        return str(output)

    def exists(self, screenshot_path, name, threshold=None, roi=None):
        return self.locate(
            screenshot_path,
            name,
            threshold=threshold,
            roi=roi,
        ) is not None
