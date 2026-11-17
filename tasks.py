import random
import time
from pathlib import Path


class RoKTasks:
    """RoK tasks controlled by ADB and color-aware OpenCV templates."""

    # Game viewport calibrated for 1280x720.
    HOME_ROI = (0, 440, 230, 720)
    # ROI hiệu chuẩn theo vị trí Scout Camp đã xác nhận trên màn hình 1280x720.
    # Không mở rộng toàn thành phố: các công trình khác ở bên phải có thể
    # cho điểm template cao giả (ví dụ x=956, y=328) và làm lệch ROI scout_icon.
    # Vị trí Scout Camp đã được xác nhận trên giao diện 1280x720.
    # ROI hẹp loại bỏ các đảo trên world map từng khớp giả với template.
    # ROI dùng tọa độ góc trên-trái của template, không phải anchor click.
    # Vị trí camp thật có anchor khoảng (673,294), box bắt đầu x~603;
    # false match trên world map có box bắt đầu x~536 nên bị loại.
    # Loại vùng bản đồ thế giới từng tạo match giả ở mép trái ROI.
    SCOUT_CAMP_ROI = (590, 190, 800, 390)
    SCOUT_LIST_ROI = (820, 240, 1190, 690)
    SEND_PANEL_ROI = (760, 100, 1280, 720)

    SCOUT_SCROLL_START = (640, 625)
    SCOUT_SCROLL_END = (640, 355)
    SCOUT_SCROLL_DURATION_MS = 380
    MAX_SCOUT_SCROLLS = 2

    def __init__(self, adb, recognizer, log, stop_event):
        self.adb = adb
        self.rec = recognizer
        self.log = log
        self.stop = stop_event
        # Sau khi gửi trinh sát, game chắc chắn đang ở bản đồ thế giới.
        # Lượt kế tiếp phải bấm nút về thành phố, không suy đoán từ Scout Camp.
        self._must_return_home_after_send = False
        self.last_screen = str(
            Path(__file__).resolve().parent / "rok_screen.png"
        )

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------
    def _wait(self, low=0.25, high=0.45):
        self.stop.wait(random.uniform(low, high))

    def _capture(self):
        return self.adb.screenshot(self.last_screen)

    def _locate(self, screenshot, template_name, roi=None):
        if template_name == "btn_explore_1":
            return self.rec.locate_color(
                screenshot,
                template_name,
                roi=roi or self.SCOUT_LIST_ROI,
            )
        return self.rec.locate(
            screenshot,
            template_name,
            roi=roi,
        )

    def _find(self, template_name, roi=None):
        screenshot = self._capture()
        return self._locate(screenshot, template_name, roi=roi)

    def _tap_match(self, template_name, match):
        if self.stop.is_set() or match is None:
            return False

        # Use exact template anchor; no random coordinate offset.
        screen_x = int(match["x"])
        screen_y = int(match["y"])

        if hasattr(self.rec, "draw_debug"):
            debug_path = self.rec.draw_debug(
                self.last_screen,
                template_name,
                match,
            )
            if debug_path:
                self.log(f"[DEBUG] {debug_path}")

        android_x, android_y = self.adb.tap(screen_x, screen_y)
        self.log(
            f"[TAP] {template_name} | "
            f"score={match['score']:.3f} | "
            f"screen=({screen_x},{screen_y}) | "
            f"android=({android_x},{android_y})"
        )
        self._wait(0.25, 0.40)
        return True

    def _wait_for_template(
        self,
        template_name,
        timeout=8.0,
        interval=0.30,
        roi=None,
        threshold=None,
    ):
        deadline = time.monotonic() + timeout

        while not self.stop.is_set() and time.monotonic() < deadline:
            screenshot = self._capture()
            if threshold is None:
                match = self._locate(
                    screenshot, template_name, roi=roi
                )
            else:
                match = self.rec.locate(
                    screenshot,
                    template_name,
                    threshold=threshold,
                    roi=roi,
                )

            if match is not None:
                self.log(
                    f"Đã nhận diện {template_name}: "
                    f"{match['score']:.3f}, "
                    f"tọa độ=({match['x']},{match['y']})"
                )
                return match

            self.stop.wait(interval)

        info = getattr(self.rec, "last_scores", {}).get(template_name)
        if info:
            self.log(
                f"Hết thời gian tìm {template_name}; "
                f"best_score={info.get('score', -1):.3f}, "
                f"ROI={info.get('roi')}"
            )
        return None

    def _scout_icon_roi(self, camp_match):
        """
        The binocular action icon appears immediately below/around the
        selected Scout Camp. Limit matching to the local interaction area
        around the detected camp rather than searching the entire screen.
        """
        screen_w, screen_h = self.adb.screenshot_size or (1280, 720)
        _, _, width, height = camp_match["box"]
        anchor_x, anchor_y = camp_match["x"], camp_match["y"]

        # Scout Icon thật nằm chếch xuống-phải khỏi tâm công trình.
        # Không tìm sát/trên tâm Scout Camp: khu vực đó trên world map
        # từng tạo match giả cùng tọa độ (606,244).
        roi = (
            max(0, anchor_x + int(width * 0.25)),
            max(0, anchor_y + int(height * 0.25)),
            min(screen_w, anchor_x + int(width * 1.25)),
            min(screen_h, anchor_y + int(height * 1.35)),
        )
        self.log(f"Vùng tìm scout_icon phía dưới-phải Scout Camp: {roi}")
        return roi

    def _return_home_if_visible(self):
        """
        Xác định trạng thái bằng Scout Camp trước.
        btn_home có thể khớp nhầm nút tròn xanh khi đang ở thành phố,
        vì vậy tuyệt đối không bấm btn_home nếu Scout Camp đã hiện đúng ROI.
        """
        if self.stop.is_set():
            return False

        screen = self._capture()

        # Trạng thái đã biết từ thao tác gửi trinh sát trước đó: đang ở world map.
        # Bắt buộc dùng nút Home để quay về, không cho match Scout Camp giả
        # trên bản đồ thế giới đánh lừa bộ điều khiển.
        if self._must_return_home_after_send:
            home = self.rec.locate(
                screen,
                "btn_home",
                threshold=0.90,
                roi=self.HOME_ROI,
            )
            if home is None:
                self.log(
                    "Sau khi gửi trinh sát, không tìm thấy btn_home; "
                    "không tiếp tục dò để tránh click nhầm."
                )
                return False

            self.log(
                "Đã gửi trinh sát ở vòng trước; chủ động quay về thành phố "
                f"(btn_home={home['score']:.3f})."
            )
            if not self._tap_match("btn_home", home):
                return False

            camp_after = self._wait_for_template(
                "scout_camp",
                timeout=8.0,
                interval=0.4,
                roi=self.SCOUT_CAMP_ROI,
                threshold=0.90,
            )
            if camp_after is None:
                self.log(
                    "Đã bấm btn_home nhưng không xác minh được Scout Camp "
                    "trong vùng thành phố; dừng an toàn."
                )
                return False

            self._must_return_home_after_send = False
            self.log("Đã quay về thành phố sau khi gửi trinh sát.")
            return True

        camp = self.rec.locate(
            screen,
            "scout_camp",
            threshold=0.90,
            roi=self.SCOUT_CAMP_ROI,
        )
        if camp is not None:
            self.log(
                "Đang ở nhà chính: Scout Camp hợp lệ "
                f"(score={camp['score']:.3f}, "
                f"tọa độ=({camp['x']},{camp['y']})); bỏ qua btn_home."
            )
            return True

        # Chỉ thử nút về thành phố khi không thấy Scout Camp trong vùng hợp lệ.
        home = self.rec.locate(
            screen,
            "btn_home",
            threshold=0.90,
            roi=self.HOME_ROI,
        )
        if home is None:
            self.log(
                "Không xác nhận được nhà chính hoặc nút btn_home; "
                "không click để tránh thao tác nhầm."
            )
            return False

        self.log(
            f"Không thấy Scout Camp; phát hiện btn_home "
            f"({home['score']:.3f}), đang thử quay về thành phố."
        )
        if not self._tap_match("btn_home", home):
            return False

        # Xác minh sau click. Không tiếp tục dò trại nếu màn hình chưa về thành phố.
        camp_after = self._wait_for_template(
            "scout_camp",
            timeout=8.0,
            interval=0.4,
            roi=self.SCOUT_CAMP_ROI,
            threshold=0.88,
        )
        if camp_after is None:
            self.log(
                "Đã bấm btn_home nhưng chưa xác minh được Scout Camp; "
                "dừng chu trình để tránh click sai."
            )
            return False

        self.log("Đã xác minh trở về nhà chính.")
        return True

    def _find_explore_button_with_scroll(self):
        """Find all yellow Explore buttons; scroll upward at most twice."""
        for attempt in range(self.MAX_SCOUT_SCROLLS + 1):
            if self.stop.is_set():
                return None

            screenshot = self._capture()

            matches = self.rec.locate_all(
                screenshot,
                "btn_explore_1",
                threshold=0.82,
                roi=self.SCOUT_LIST_ROI,
                max_matches=8,
                yellow_only=True,
            )

            if matches:
                self.log(
                    f"Tìm thấy {len(matches)} nút Thăm dò màu vàng "
                    f"sau {attempt} lần cuộn."
                )
                for index, candidate in enumerate(matches, start=1):
                    self.log(
                        f"Ứng viên {index}: "
                        f"y={candidate['y']}, "
                        f"score={candidate['score']:.3f}, "
                        f"yellow={candidate.get('yellow_ratio', 0):.2f}"
                    )

                debug_path = self.rec.draw_debug_all(
                    screenshot,
                    "btn_explore_1",
                    matches,
                )
                if debug_path:
                    self.log(f"[DEBUG MULTI] {debug_path}")

                # Return the topmost yellow button. Busy blue "Đi" buttons
                # are rejected by BGR matching and yellow-pixel validation.
                return matches[0]

            if attempt < self.MAX_SCOUT_SCROLLS:
                self.log(
                    f"Chưa thấy nút vàng; vuốt danh sách "
                    f"{attempt + 1}/{self.MAX_SCOUT_SCROLLS}."
                )
                self.adb.swipe(
                    *self.SCOUT_SCROLL_START,
                    *self.SCOUT_SCROLL_END,
                    duration_ms=self.SCOUT_SCROLL_DURATION_MS,
                )
                self._wait(0.45, 0.65)

        return None

    def _close_scout_panel_and_return_home(self):
        if self.stop.is_set():
            return False
        try:
            self.adb.back()
            self._wait(0.35, 0.55)
            verified = self._return_home_if_visible()
            if not verified:
                self.log("Không xác minh được nhà chính sau khi đóng bảng trinh sát.")
            return verified
        except Exception as exc:
            self.log(f"Không thể đóng bảng trinh sát: {exc}")
            return False

    # --------------------------------------------------
    # Coordinate calibration: Scout Camp -> Scout icon
    # --------------------------------------------------
    def run_scout_coordinate_test(self):
        """
        Controlled click test. Start with the game showing the city.
        Clicks only the Scout Camp and its binocular action icon, then
        verifies that the scout-management panel is visible.
        """
        self.log("========== KIỂM TRA TỌA ĐỘ CLICK SCOUT ==========")
        screen = self._capture()
        self.log(
            f"[SCREEN] screenshot={self.adb.screenshot_size}, "
            f"android_input={self.adb.get_display_size(refresh=True)}"
        )

        camp = self.rec.locate(
            screen, "scout_camp", threshold=0.82
        )
        if camp is None:
            info = getattr(self.rec, "last_scores", {}).get("scout_camp", {})
            self.log(
                "TEST FAIL: Không tìm thấy scout_camp. "
                f"best_score={info.get('score', -1):.3f}"
            )
            return False

        self.log(
            f"[MATCH] scout_camp score={camp['score']:.3f}, "
            f"box={camp['box']}, anchor=({camp['x']},{camp['y']})"
        )
        if not self._tap_match("scout_camp", camp):
            return False

        self._wait(0.45, 0.65)
        screen = self._capture()
        scout_roi = self._scout_icon_roi(camp)
        icon = self.rec.locate(
            screen, "scout_icon", threshold=0.82, roi=scout_roi
        )
        if icon is None:
            info = getattr(self.rec, "last_scores", {}).get("scout_icon", {})
            self.log(
                "TEST FAIL: Đã click trại nhưng không tìm thấy scout_icon "
                f"trong ROI {scout_roi}; best_score={info.get('score', -1):.3f}"
            )
            return False

        self.log(
            f"[MATCH] scout_icon score={icon['score']:.3f}, "
            f"box={icon['box']}, anchor=({icon['x']},{icon['y']})"
        )
        if not self._tap_match("scout_icon", icon):
            return False

        self._wait(0.55, 0.75)
        panel_screen = self._capture()
        explore = self.rec.locate_all(
            panel_screen,
            "btn_explore_1",
            threshold=0.82,
            roi=self.SCOUT_LIST_ROI,
            max_matches=8,
            yellow_only=True,
        )
        if explore:
            self.log(
                "TEST PASS: Click Scout Camp và Scout Icon thành công; "
                "đã phát hiện bảng quản lý trinh sát "
                f"(nút Khám phá vàng: {len(explore)})."
            )
            return True

        self.log(
            "TEST INCONCLUSIVE: Đã click Scout Icon nhưng chưa phát hiện "
            "nút Khám phá vàng. Kiểm tra ảnh rok_screen.png và trạng thái game."
        )
        return False

    # --------------------------------------------------
    # Fog exploration
    # --------------------------------------------------
    def run_fog_cycle(self):
        """
        Send free scouts one by one.
        status='exhausted' means no yellow btn_explore_1 remains after
        the initial scan and up to two upward swipes.
        """
        sent_count = 0

        while not self.stop.is_set():
            self.log("========== CHU TRÌNH DÒ MÂY ==========")

            # STEP 1: Return to city if btn_home is visible.
            if not self._return_home_if_visible():
                return {"status": "error", "sent": sent_count}

            # STEP 2: Find and select Scout Camp.
            self.log("Bước 2: Tìm Trại Trinh Sát.")
            camp_match = self._wait_for_template(
                "scout_camp",
                timeout=7,
                roi=self.SCOUT_CAMP_ROI,
                threshold=0.88,
            )
            if camp_match is None:
                self.log("Không tìm thấy scout_camp; dừng an toàn.")
                return {"status": "error", "sent": sent_count}

            if not self._tap_match("scout_camp", camp_match):
                return {"status": "stopped", "sent": sent_count}

            self._wait(0.4, 0.65)

            # Find the binocular icon only near the selected Scout Camp.
            scout_roi = self._scout_icon_roi(camp_match)
            scout_icon_match = self._wait_for_template(
                "scout_icon",
                timeout=7,
                roi=scout_roi,
            )
            if scout_icon_match is None:
                self.log(
                    "Không tìm thấy scout_icon trong vùng tương tác "
                    "quanh Trại Trinh Sát."
                )
                return {"status": "error", "sent": sent_count}

            if not self._tap_match("scout_icon", scout_icon_match):
                return {"status": "stopped", "sent": sent_count}

            self._wait(0.4, 0.65)

            # STEP 3: Find the available yellow Explore button.
            self.log("Bước 3: Tìm nút Khám phá màu vàng.")
            explore_1_match = self._find_explore_button_with_scroll()

            if self.stop.is_set():
                return {"status": "stopped", "sent": sent_count}

            if explore_1_match is None:
                self.log(
                    "Không còn nút Khám phá màu vàng sau tối đa hai lần cuộn."
                )
                if not self._close_scout_panel_and_return_home():
                    self.log("Không thể xác minh trạng thái nhà chính; không kết luận hết trinh sát.")
                    return {"status": "error", "sent": sent_count}
                return {"status": "exhausted", "sent": sent_count}

            if not self._tap_match("btn_explore_1", explore_1_match):
                return {"status": "stopped", "sent": sent_count}

            # STEP 4: Wait for the map camera, then select the fog area.
            wait_seconds = random.uniform(1.8, 2.5)
            self.log(f"Chờ bản đồ di chuyển {wait_seconds:.2f} giây.")
            if self.stop.wait(wait_seconds):
                return {"status": "stopped", "sent": sent_count}

            explore_2_match = self._wait_for_template(
                "btn_explore_2",
                timeout=9,
            )
            if explore_2_match is None:
                self.log(
                    "Không tìm thấy btn_explore_2; dừng để tránh click nhầm."
                )
                return {"status": "error", "sent": sent_count}

            if not self._tap_match("btn_explore_2", explore_2_match):
                return {"status": "stopped", "sent": sent_count}

            self._wait(0.35, 0.55)

            # STEP 5: Send scout.
            send_match = self._wait_for_template(
                "btn_send_scout",
                timeout=9,
                roi=self.SEND_PANEL_ROI,
            )
            if send_match is None:
                self.log(
                    "Không tìm thấy btn_send_scout trong bảng điều quân."
                )
                return {"status": "error", "sent": sent_count}

            if not self._tap_match("btn_send_scout", send_match):
                return {"status": "stopped", "sent": sent_count}

            sent_count += 1
            # Xác lập trạng thái màn hình: thao tác gửi trinh sát đưa game
            # trở lại bản đồ thế giới. Vòng tiếp theo phải bấm btn_home.
            self._must_return_home_after_send = True
            self.log(
                f"Đã gửi trinh sát thứ {sent_count}; "
                "quay lại Bước 1 và chụp màn hình mới."
            )
            self._wait(0.6, 0.9)

            # Next loop returns to STEP 1. No old coordinates are reused.

        return {"status": "stopped", "sent": sent_count}

    # --------------------------------------------------
    # Resource gathering (existing basic flow)
    # --------------------------------------------------
    def run_farm_cycle(self, resources, preferred_level):
        if self.stop.is_set():
            return False

        self.log("========== AUTO FARM ==========")

        if not self._tap_template("world_map"):
            self.log("Không tìm thấy world_map.")
            return False
        if not self._tap_template("search_icon"):
            self.log("Không tìm thấy search_icon.")
            return False

        resource = self._choose_resource(resources)
        if not resource or not self._tap_template(resource):
            self.log("Không chọn được loại tài nguyên.")
            return False

        if not self._tap_template(f"level_{preferred_level}"):
            self.log(f"Không tìm thấy level_{preferred_level}.")
            return False
        if not self._tap_template("search_button"):
            return False

        self._wait(1.0, 1.5)
        if not self._tap_template("resource_node"):
            self.log("Không tìm thấy resource_node.")
            return False
        if not self._tap_template("gather"):
            return False
        if not self._tap_template("new_troops"):
            return False
        if not self._tap_template("march"):
            return False

        self.log(
            "Đã thực hiện thao tác hành quân; "
            "cần xác nhận kết quả trên game."
        )
        return True

    def _tap_template(self, template_name):
        match = self._find(template_name)
        if match is None:
            self.log(f"Không tìm thấy template: {template_name}")
            return False
        return self._tap_match(template_name, match)

    @staticmethod
    def _choose_resource(resources):
        mapping = {
            "Food": "food",
            "Wood": "wood",
            "Stone": "stone",
            "Gold": "gold",
        }
        return mapping.get(resources[0]) if resources else None
