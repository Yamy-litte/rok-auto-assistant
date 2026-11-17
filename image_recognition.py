from pathlib import Path

import cv2
import numpy as np


class ImageRecognizer:
    """
    OpenCV template matcher with:
    - BGR matching (keeps button colors).
    - PNG alpha masks.
    - Multi-scale matching.
    - Multiple match collection for repeated list buttons.
    - ROI support to avoid matching unrelated UI elements.
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
            mask = None
            anchor = (raw.shape[1] / 2.0, raw.shape[0] / 2.0)
        elif raw.shape[2] == 4:
            color = raw[:, :, :3]
            alpha = raw[:, :, 3]
            mask = np.where(alpha > 16, 255, 0).astype(np.uint8)
            ys, xs = np.where(mask > 0)
            if len(xs) == 0:
                raise ValueError(
                    f"Template không có vùng nhìn thấy: {name}"
                )
            anchor = (float(xs.mean()), float(ys.mean()))
            if cv2.countNonZero(mask) == mask.size:
                mask = None
        else:
            color = raw[:, :, :3]
            mask = None
            anchor = (color.shape[1] / 2.0, color.shape[0] / 2.0)

        # btn_home template contains the BlueStacks "Space" key label.
        # The debug image showed that the circular castle button is at
        # approximately the center of this ellipse; exclude the label area.
        if name == "btn_home":
            height, width = color.shape[:2]
            home_mask = np.zeros((height, width), dtype=np.uint8)
            center = (round(width * 0.50), round(height * 0.52))
            axes = (max(1, round(width * 0.43)), max(1, round(height * 0.38)))
            cv2.ellipse(home_mask, center, axes, 0, 0, 360, 255, -1)
            if mask is not None:
                home_mask = cv2.bitwise_and(home_mask, mask)
            mask = home_mask
            anchor = (width * 0.50, height * 0.52)

        if mask is not None and cv2.countNonZero(mask) < 20:
            raise ValueError(f"Mask template không hợp lệ: {name}")

        data = {"color": color, "mask": mask, "anchor": anchor}
        self._cache[name] = data
        print(
            f"[OpenCV] Loaded {name}: {color.shape[1]}x{color.shape[0]}, "
            f"alpha/shape mask={mask is not None}"
        )
        return data

    @staticmethod
    def _normalize_roi(roi, screen_width, screen_height):
        if roi is None:
            return 0, 0, screen_width, screen_height

        x1, y1, x2, y2 = map(int, roi)
        x1 = max(0, min(x1, screen_width))
        y1 = max(0, min(y1, screen_height))
        x2 = max(0, min(x2, screen_width))
        y2 = max(0, min(y2, screen_height))

        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"ROI không hợp lệ: {roi}")

        return x1, y1, x2, y2

    @staticmethod
    def _make_result(x, y, width, height, anchor, scale, score):
        anchor_x, anchor_y = anchor
        return {
            "x": int(round(x + anchor_x * scale)),
            "y": int(round(y + anchor_y * scale)),
            "score": float(score),
            "scale": float(scale),
            "box": (int(x), int(y), int(width), int(height)),
        }

    @staticmethod
    def _yellow_button_ratio(screen, box):
        """Return the fraction of yellow/orange pixels inside a button patch."""
        x, y, width, height = box
        patch = screen[
            y + int(height * 0.12): y + int(height * 0.88),
            x + int(width * 0.08): x + int(width * 0.92),
        ]
        if patch.size == 0:
            return 0.0

        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        # OpenCV hue range 0..179; yellow/orange game button is approx 8..42.
        yellow = cv2.inRange(
            hsv,
            np.array([8, 80, 90], dtype=np.uint8),
            np.array([42, 255, 255], dtype=np.uint8),
        )
        return float(cv2.countNonZero(yellow)) / float(yellow.size)

    @staticmethod
    def _iou(box_a, box_b):
        ax, ay, aw, ah = box_a
        bx, by, bw, bh = box_b
        left = max(ax, bx)
        top = max(ay, by)
        right = min(ax + aw, bx + bw)
        bottom = min(ay + ah, by + bh)
        if right <= left or bottom <= top:
            return 0.0

        intersection = (right - left) * (bottom - top)
        union = aw * ah + bw * bh - intersection
        return intersection / union if union else 0.0

    def _match_screen(
        self,
        screen,
        name,
        threshold,
        roi=None,
        max_matches=12,
        all_matches=False,
        yellow_only=False,
    ):
        screen_height, screen_width = screen.shape[:2]
        roi_x1, roi_y1, roi_x2, roi_y2 = self._normalize_roi(
            roi, screen_width, screen_height
        )
        search_area = screen[roi_y1:roi_y2, roi_x1:roi_x2]

        data = self.load(name)
        template = data["color"]
        mask = data["mask"]
        anchor = data["anchor"]

        area_h, area_w = search_area.shape[:2]
        template_h, template_w = template.shape[:2]

        best_score = -1.0
        best_match = None
        candidates = []

        scales = self.scales.get(name, self.default_scales)

        for scale in scales:
            new_w = max(1, int(round(template_w * scale)))
            new_h = max(1, int(round(template_h * scale)))
            if new_w > area_w or new_h > area_h:
                continue

            interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
            resized = cv2.resize(
                template, (new_w, new_h), interpolation=interpolation
            )

            resized_mask = None
            if mask is not None:
                resized_mask = cv2.resize(
                    mask, (new_w, new_h), interpolation=cv2.INTER_NEAREST
                )
                match_mask = np.repeat(resized_mask[:, :, None], 3, axis=2)
                response = cv2.matchTemplate(
                    search_area,
                    resized,
                    cv2.TM_CCORR_NORMED,
                    mask=match_mask,
                )
            else:
                response = cv2.matchTemplate(
                    search_area,
                    resized,
                    cv2.TM_CCOEFF_NORMED,
                )

            response = np.nan_to_num(
                response, nan=-1.0, posinf=-1.0, neginf=-1.0
            )

            # Keep the strongest peak for ordinary single-match lookup.
            _, scale_best, _, scale_location = cv2.minMaxLoc(response)
            if scale_best > best_score:
                best_score = float(scale_best)
                lx, ly = scale_location
                box = (roi_x1 + lx, roi_y1 + ly, new_w, new_h)
                best_match = self._make_result(
                    roi_x1 + lx, roi_y1 + ly,
                    new_w, new_h, anchor, scale, scale_best
                )
                best_match["box"] = box

            if not all_matches:
                continue

            # Extract multiple local peaks at this scale. Suppression prevents
            # the same button being returned repeatedly at nearby pixels.
            work = response.copy()
            for _ in range(max_matches):
                _, score, _, location = cv2.minMaxLoc(work)
                if score < threshold:
                    break

                lx, ly = location
                abs_x = roi_x1 + lx
                abs_y = roi_y1 + ly
                box = (abs_x, abs_y, new_w, new_h)

                if yellow_only:
                    ratio = self._yellow_button_ratio(
                        screen,
                        box,
                    )
                    if ratio < 0.10:
                        # Suppress this false-colored candidate and continue.
                        pass
                    else:
                        match = self._make_result(
                            abs_x, abs_y, new_w, new_h,
                            anchor, scale, score
                        )
                        match["box"] = box
                        match["yellow_ratio"] = ratio
                        candidates.append(match)
                else:
                    match = self._make_result(
                        abs_x, abs_y, new_w, new_h,
                        anchor, scale, score
                    )
                    match["box"] = box
                    candidates.append(match)

                # Suppress an area larger than the current template so
                # adjacent peaks from the same button are not duplicated.
                pad_x = max(2, new_w // 2)
                pad_y = max(2, new_h // 2)
                sx1 = max(0, lx - pad_x)
                sy1 = max(0, ly - pad_y)
                sx2 = min(work.shape[1], lx + new_w + pad_x)
                sy2 = min(work.shape[0], ly + new_h + pad_y)
                work[sy1:sy2, sx1:sx2] = -1.0

        self.last_scores[name] = {
            "score": best_score,
            "roi": (roi_x1, roi_y1, roi_x2, roi_y2),
            "candidates": len(candidates),
        }

        if not all_matches:
            if best_match is None or best_score < threshold:
                return None
            return best_match

        # Non-maximum suppression across scales.
        candidates.sort(key=lambda item: item["score"], reverse=True)
        kept = []
        for candidate in candidates:
            if all(
                self._iou(candidate["box"], existing["box"]) < 0.35
                for existing in kept
            ):
                kept.append(candidate)
            if len(kept) >= max_matches:
                break

        # In a vertical scout list, choose/read candidates top-to-bottom.
        kept.sort(key=lambda item: (item["y"], item["x"]))
        return kept

    def locate(self, screenshot_path, name, threshold=None, roi=None):
        screen = cv2.imread(str(screenshot_path), cv2.IMREAD_COLOR)
        if screen is None:
            raise ValueError(
                f"Không đọc được screenshot: {screenshot_path}"
            )

        limit = self.threshold if threshold is None else float(threshold)
        return self._match_screen(
            screen,
            name,
            threshold=limit,
            roi=roi,
            all_matches=False,
        )

    def locate_color(self, screenshot_path, name, threshold=None, roi=None):
        """Use BGR color matching instead of converting the screenshot to grayscale."""
        return self.locate(
            screenshot_path,
            name,
            threshold=threshold,
            roi=roi,
        )

    def locate_all(
        self,
        screenshot_path,
        name,
        threshold=None,
        roi=None,
        max_matches=12,
        yellow_only=False,
    ):
        screen = cv2.imread(str(screenshot_path), cv2.IMREAD_COLOR)
        if screen is None:
            raise ValueError(
                f"Không đọc được screenshot: {screenshot_path}"
            )

        limit = self.threshold if threshold is None else float(threshold)
        return self._match_screen(
            screen,
            name,
            threshold=limit,
            roi=roi,
            max_matches=max_matches,
            all_matches=True,
            yellow_only=yellow_only,
        )

    def draw_debug(self, screenshot_path, name, match, output_path=None):
        image = cv2.imread(str(screenshot_path), cv2.IMREAD_COLOR)
        if image is None or match is None:
            return None

        x, y, width, height = match["box"]
        cv2.rectangle(
            image, (x, y), (x + width, y + height), (0, 255, 0), 2
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

        output = (
            Path(output_path)
            if output_path
            else self.base_dir / f"debug_{name}.png"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output), image)
        return str(output.resolve())

    def draw_debug_all(self, screenshot_path, name, matches, output_path=None):
        image = cv2.imread(str(screenshot_path), cv2.IMREAD_COLOR)
        if image is None:
            return None

        for index, match in enumerate(matches, start=1):
            x, y, width, height = match["box"]
            cv2.rectangle(
                image, (x, y), (x + width, y + height), (0, 255, 0), 2
            )
            cv2.drawMarker(
                image,
                (match["x"], match["y"]),
                (0, 0, 255),
                cv2.MARKER_CROSS,
                18,
                2,
            )
            cv2.putText(
                image,
                f"{index}: {match['score']:.3f}",
                (x, max(20, y - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
            )

        output = (
            Path(output_path)
            if output_path
            else self.base_dir / f"debug_{name}_all.png"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output), image)
        return str(output.resolve())

    def exists(self, screenshot_path, name, threshold=None, roi=None):
        return self.locate(
            screenshot_path,
            name,
            threshold=threshold,
            roi=roi,
        ) is not None
