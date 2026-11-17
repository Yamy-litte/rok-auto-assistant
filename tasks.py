import random
import time
from pathlib import Path


class RoKTasks:
    """RoK tasks controlled by ADB and OpenCV templates."""

    # BlueStacks/game screenshot is expected to be 1280x720.
    # Scroll inside the scout list, from bottom to top.
    SCOUT_SCROLL_START = (640, 625)
    SCOUT_SCROLL_END = (640, 355)
    SCOUT_SCROLL_DURATION_MS = 350
    MAX_SCOUT_SCROLLS = 2

    def __init__(self, adb, recognizer, log, stop_event):
        self.adb = adb
        self.rec = recognizer
        self.log = log
        self.stop = stop_event
        self.last_screen = str(Path(__file__).resolve().parent / "rok_screen.png")

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------
    def _wait(self, low=0.25, high=0.55):
        self.stop.wait(random.uniform(low, high))

    def _capture(self):
        return self.adb.screenshot(self.last_screen)

    def _locate(self, screenshot, template_name):
        # The available-scout button is yellow. Use color matching to
        # distinguish it from the blue "Đi" buttons of busy scouts.
        if template_name == "btn_explore_1":
            return self.rec.locate_color(screenshot, template_name)
        return self.rec.locate(screenshot, template_name)

    def _find(self, template_name):
        screenshot = self._capture()
        return self._locate(screenshot, template_name)

    def _tap_match(self, template_name, match):
        if self.stop.is_set() or match is None:
            return False
        x = match["x"] + random.randint(-2, 2)
        y = match["y"] + random.randint(-2, 2)
        self.log(
            f"Nhận diện {template_name}: score={match['score']:.3f}, "
            f"tọa độ=({match['x']},{match['y']})"
        )
        self.adb.tap(x, y)
        self._wait()
        return True

    def _wait_for_template(self, template_name, timeout=8.0, interval=0.35):
        deadline = time.monotonic() + timeout
        while not self.stop.is_set() and time.monotonic() < deadline:
            screenshot = self._capture()
            match = self._locate(screenshot, template_name)
            if match is not None:
                self.log(f"Đã nhận diện {template_name}: {match['score']:.3f}")
                return match
            self.stop.wait(interval)
        return None

    def _return_home_if_visible(self):
        """At cycle start, tap btn_home only when it is visible."""
        if self.stop.is_set():
            return False
        match = self._find("btn_home")
        if match is None:
            self.log("Không thấy btn_home; tiếp tục với màn hình hiện tại.")
            return True
        self.log("Phát hiện btn_home; đang quay về thành phố.")
        if not self._tap_match("btn_home", match):
            return False
        self._wait(0.5, 0.9)
        return True

    def _find_explore_button_with_scroll(self):
        """Search once, then swipe up at most twice and search after each swipe."""
        for attempt in range(self.MAX_SCOUT_SCROLLS + 1):
            if self.stop.is_set():
                return None

            match = self._find("btn_explore_1")
            if match is not None:
                self.log(
                    f"Tìm thấy nút Khám phá màu vàng sau {attempt} lần cuộn; "
                    f"score={match['score']:.3f}."
                )
                return match

            if attempt < self.MAX_SCOUT_SCROLLS:
                self.log(
                    f"Chưa thấy btn_explore_1; vuốt danh sách "
                    f"lần {attempt + 1}/{self.MAX_SCOUT_SCROLLS}."
                )
                sx, sy = self.SCOUT_SCROLL_START
                ex, ey = self.SCOUT_SCROLL_END
                self.adb.swipe(
                    sx, sy, ex, ey,
                    duration_ms=self.SCOUT_SCROLL_DURATION_MS
                )
                self._wait(0.45, 0.7)

        return None

    def _close_scout_panel_and_return_home(self):
        """Close the scout overlay, then use btn_home if it appears."""
        if self.stop.is_set():
            return
        try:
            self.adb.back()
            self._wait(0.35, 0.6)
            self._return_home_if_visible()
        except Exception as exc:
            self.log(f"Không thể đóng bảng trinh sát: {exc}")

    # --------------------------------------------------
    # Fog exploration
    # --------------------------------------------------
    def run_fog_cycle(self):
        """Send all currently free scouts once; return a status dict.

        status='exhausted' means btn_explore_1 was not found after the
        initial scan and at most two upward swipes. main.py then applies
        the configured rest period before beginning a new scan.
        """
        sent_count = 0

        while not self.stop.is_set():
            self.log("========== CHU TRÌNH DÒ MÂY ==========")

            # STEP 1: Return to city if the Home button is currently visible.
            if not self._return_home_if_visible():
                return {"status": "error", "sent": sent_count}

            # STEP 2: Open Scout Camp.
            self.log("Bước 2: Tìm Trại Trinh Sát.")
            camp_match = self._wait_for_template("scout_camp", timeout=6)
            if camp_match is None:
                self.log("Không tìm thấy scout_camp; dừng chu trình để kiểm tra giao diện.")
                return {"status": "error", "sent": sent_count}

            if not self._tap_match("scout_camp", camp_match):
                return {"status": "stopped", "sent": sent_count}

            self._wait(0.35, 0.6)

            # Tap the binocular/scout icon below the selected building.
            scout_icon_match = self._wait_for_template("scout_icon", timeout=6)
            if scout_icon_match is None:
                self.log("Không tìm thấy scout_icon dưới Trại Trinh Sát.")
                return {"status": "error", "sent": sent_count}

            if not self._tap_match("scout_icon", scout_icon_match):
                return {"status": "stopped", "sent": sent_count}

            self._wait(0.35, 0.6)

            # STEP 3: Find the yellow Explore button. Scroll upward at most twice.
            self.log("Bước 3: Tìm nút Khám phá của trinh sát rảnh.")
            explore_1_match = self._find_explore_button_with_scroll()

            if self.stop.is_set():
                return {"status": "stopped", "sent": sent_count}

            if explore_1_match is None:
                self.log(
                    "Không còn btn_explore_1 sau tối đa hai lần cuộn. "
                    "Đợt gửi trinh sát đã hoàn tất."
                )
                self._close_scout_panel_and_return_home()
                return {"status": "exhausted", "sent": sent_count}

            if not self._tap_match("btn_explore_1", explore_1_match):
                return {"status": "stopped", "sent": sent_count}

            # STEP 4: Wait for map camera movement, then tap Explore 2.
            wait_for_map = random.uniform(1.8, 2.5)
            self.log(f"Chờ bản đồ di chuyển {wait_for_map:.2f} giây.")
            if self.stop.wait(wait_for_map):
                return {"status": "stopped", "sent": sent_count}

            explore_2_match = self._wait_for_template("btn_explore_2", timeout=8)
            if explore_2_match is None:
                self.log("Không tìm thấy btn_explore_2; dừng để tránh thao tác nhầm.")
                return {"status": "error", "sent": sent_count}

            if not self._tap_match("btn_explore_2", explore_2_match):
                return {"status": "stopped", "sent": sent_count}

            self._wait(0.35, 0.6)

            # STEP 5: Find and tap Send Scout on the troop panel.
            send_match = self._wait_for_template("btn_send_scout", timeout=8)
            if send_match is None:
                self.log("Không tìm thấy btn_send_scout; dừng để kiểm tra bảng điều quân.")
                return {"status": "error", "sent": sent_count}

            if not self._tap_match("btn_send_scout", send_match):
                return {"status": "stopped", "sent": sent_count}

            sent_count += 1
            self.log(f"Đã gửi trinh sát thứ {sent_count} trong đợt hiện tại.")
            self._wait(0.6, 1.0)

            # STEP 6: Start the next scout from STEP 1. The Home button
            # is checked again at the top of this loop.

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

        self.log("Đã thực hiện thao tác hành quân; cần xác nhận trên game.")
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
