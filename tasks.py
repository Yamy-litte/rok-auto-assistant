import random
import time
from pathlib import Path


class RoKTasks:
    """RoK tasks controlled by ADB and color-aware OpenCV templates."""

    # Các vùng tìm kiếm trên screenshot 1280x720 của game.
    HOME_ROI = (0, 440, 230, 720)
    EXPLORE_LIST_ROI = (800, 140, 1190, 720)
    SEND_PANEL_ROI = (760, 100, 1280, 720)

    # Vuốt danh sách từ dưới lên trên, tối đa hai lần.
    SCOUT_SCROLL_START = (640, 625)
    SCOUT_SCROLL_END = (640, 355)
    SCOUT_SCROLL_DURATION_MS = 380
    MAX_SCOUT_SCROLLS = 2

    def __init__(self, adb, recognizer, log, stop_event):
        self.adb = adb
        self.rec = recognizer
        self.log = log
        self.stop = stop_event
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

    def _locate(self, screenshot, template_name):
        if template_name == "btn_home":
            return self.rec.locate(
                screenshot,
                template_name,
                roi=self.HOME_ROI,
            )

        if template_name == "btn_explore_1":
            # Color matching + right-side list ROI: blue "ĐI" buttons
            # should not match the yellow available-scout button.
            return self.rec.locate_color(
                screenshot,
                template_name,
                roi=self.EXPLORE_LIST_ROI,
            )

        if template_name == "btn_send_scout":
            return self.rec.locate(
                screenshot,
                template_name,
                roi=self.SEND_PANEL_ROI,
            )

        return self.rec.locate(screenshot, template_name)

    def _find(self, template_name):
        screenshot = self._capture()
        return self._locate(screenshot, template_name)

    def _tap_match(self, template_name, match):
        if self.stop.is_set() or match is None:
            return False

        # Click đúng anchor do recognizer trả về, không cộng jitter.
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

        device_x, device_y = self.adb.tap(screen_x, screen_y)

        self.log(
            f"[TAP] {template_name} | "
            f"score={match['score']:.3f} | "
            f"screen=({screen_x},{screen_y}) | "
            f"android=({device_x},{device_y})"
        )
        self._wait()
        return True

    def _wait_for_template(
        self,
        template_name,
        timeout=8.0,
        interval=0.30,
    ):
        deadline = time.monotonic() + timeout

        while not self.stop.is_set() and time.monotonic() < deadline:
            screenshot = self._capture()
            match = self._locate(screenshot, template_name)

            if match is not None:
                self.log(
                    f"Đã nhận diện {template_name}: "
                    f"{match['score']:.3f}"
                )
                return match

            self.stop.wait(interval)

        return None

    def _return_home_if_visible(self):
        """Chỉ nhấn nút Home khi nhận diện được trong vùng góc dưới bên trái."""
        if self.stop.is_set():
            return False

        match = self._find("btn_home")
        if match is None:
            self.log(
                "Không thấy btn_home trong vùng nút điều hướng; "
                "giả định đang ở thành phố."
            )
            return True

        self.log("Phát hiện btn_home; đang quay về thành phố.")
        if not self._tap_match("btn_home", match):
            return False

        self._wait(0.55, 0.85)
        return True

    def _find_explore_button_with_scroll(self):
        """Tìm nút vàng trước, rồi cuộn danh sách tối đa hai lần."""
        for attempt in range(self.MAX_SCOUT_SCROLLS + 1):
            if self.stop.is_set():
                return None

            match = self._find("btn_explore_1")
            if match is not None:
                self.log(
                    f"Tìm thấy nút Khám phá sau {attempt} lần cuộn; "
                    f"score={match['score']:.3f}."
                )
                return match

            if attempt < self.MAX_SCOUT_SCROLLS:
                self.log(
                    f"Chưa thấy btn_explore_1; "
                    f"vuốt lần {attempt + 1}/{self.MAX_SCOUT_SCROLLS}."
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
            return

        try:
            self.adb.back()
            self._wait(0.35, 0.55)
            self._return_home_if_visible()
        except Exception as exc:
            self.log(f"Không thể đóng bảng trinh sát: {exc}")

    # --------------------------------------------------
    # Fog exploration
    # --------------------------------------------------
    def run_fog_cycle(self):
        """
        Gửi lần lượt từng trinh sát rảnh.
        Trả status='exhausted' khi không còn btn_explore_1 sau tối đa
        hai lần cuộn; main.py sẽ ngủ theo thời gian người dùng cấu hình.
        """
        sent_count = 0

        while not self.stop.is_set():
            self.log("========== CHU TRÌNH DÒ MÂY ==========")

            # STEP 1: Nếu btn_home xuất hiện, quay về thành phố.
            if not self._return_home_if_visible():
                return {"status": "error", "sent": sent_count}

            # STEP 2: Mở Trại Trinh Sát và nhấn biểu tượng ống nhòm.
            self.log("Bước 2: Tìm Trại Trinh Sát.")
            camp_match = self._wait_for_template(
                "scout_camp",
                timeout=7,
            )
            if camp_match is None:
                self.log(
                    "Không tìm thấy scout_camp. "
                    "Dừng để kiểm tra trạng thái màn hình."
                )
                return {"status": "error", "sent": sent_count}

            if not self._tap_match("scout_camp", camp_match):
                return {"status": "stopped", "sent": sent_count}

            self._wait(0.4, 0.65)

            scout_icon_match = self._wait_for_template(
                "scout_icon",
                timeout=7,
            )
            if scout_icon_match is None:
                self.log("Không tìm thấy scout_icon sau khi chọn Trại Trinh Sát.")
                return {"status": "error", "sent": sent_count}

            if not self._tap_match("scout_icon", scout_icon_match):
                return {"status": "stopped", "sent": sent_count}

            self._wait(0.4, 0.65)

            # STEP 3: Tìm nút vàng Khám phá; cuộn tối đa hai lần.
            self.log("Bước 3: Tìm nút Khám phá của trinh sát rảnh.")
            explore_1_match = self._find_explore_button_with_scroll()

            if self.stop.is_set():
                return {"status": "stopped", "sent": sent_count}

            if explore_1_match is None:
                self.log(
                    "Không còn btn_explore_1 sau hai lần cuộn. "
                    "Hoàn tất đợt gửi trinh sát."
                )
                self._close_scout_panel_and_return_home()
                return {"status": "exhausted", "sent": sent_count}

            if not self._tap_match("btn_explore_1", explore_1_match):
                return {"status": "stopped", "sent": sent_count}

            # STEP 4: Chờ camera chuyển đến vùng sương mù.
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
                    "Không tìm thấy btn_explore_2. "
                    "Dừng để tránh nhấn sai giao diện."
                )
                return {"status": "error", "sent": sent_count}

            if not self._tap_match("btn_explore_2", explore_2_match):
                return {"status": "stopped", "sent": sent_count}

            self._wait(0.35, 0.55)

            # STEP 5: Nhấn nút Gửi trên bảng điều quân.
            send_match = self._wait_for_template(
                "btn_send_scout",
                timeout=9,
            )
            if send_match is None:
                self.log(
                    "Không tìm thấy btn_send_scout. "
                    "Dừng để kiểm tra bảng điều quân."
                )
                return {"status": "error", "sent": sent_count}

            if not self._tap_match("btn_send_scout", send_match):
                return {"status": "stopped", "sent": sent_count}

            sent_count += 1
            self.log(
                f"Đã gửi trinh sát thứ {sent_count}. "
                "Quay lại Bước 1 để kiểm tra trinh sát tiếp theo."
            )
            self._wait(0.6, 0.9)

            # STEP 6: Không giữ lại tọa độ cũ; vòng lặp chụp ảnh mới
            # và quay lại Bước 1 để kiểm tra btn_home.
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
