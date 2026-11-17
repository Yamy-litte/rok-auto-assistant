import re
import subprocess
import time
from pathlib import Path


class ADBController:
    """Điều khiển BlueStacks qua ADB và đồng bộ tọa độ screenshot/input."""

    def __init__(self, adb_path=r"C:\Users\nghia\platform-tools\adb.exe"):
        self.adb_path = str(Path(adb_path))
        self.serial = None
        self.screenshot_size = None
        self._display_size_cache = None

        if not Path(self.adb_path).is_file():
            raise FileNotFoundError(
                f"Không tìm thấy adb.exe tại: {self.adb_path}"
            )

    def _run(self, *args, timeout=20):
        cmd = [self.adb_path]
        if self.serial:
            cmd += ["-s", self.serial]
        cmd += list(args)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip()
                or result.stdout.strip()
                or "ADB command failed"
            )

        return result.stdout.strip()

    def connect(self, address):
        result = subprocess.run(
            [self.adb_path, "connect", address],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = (result.stdout or result.stderr).strip()

        if (
            result.returncode != 0
            or "unable" in output.lower()
            or "failed" in output.lower()
        ):
            self.serial = None
            raise RuntimeError(output or "Không thể kết nối ADB.")

        self.serial = address
        self._display_size_cache = None
        return output

    def devices(self):
        result = subprocess.run(
            [self.adb_path, "devices"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return [
            line.split()[0]
            for line in result.stdout.splitlines()[1:]
            if len(line.split()) >= 2 and line.split()[1] == "device"
        ]

    def get_display_size(self, refresh=False):
        """Lấy kích thước input thực tế của Android; ưu tiên Override size."""
        if self._display_size_cache is not None and not refresh:
            return self._display_size_cache

        output = self._run("shell", "wm", "size")
        matches = re.findall(
            r"(?:Physical|Override) size:\s*(\d+)x(\d+)",
            output,
        )

        if not matches:
            raise RuntimeError(
                f"Không đọc được kích thước Android từ 'wm size': {output}"
            )

        width, height = map(int, matches[-1])
        self._display_size_cache = (width, height)
        return self._display_size_cache

    def screenshot(self, destination="screen.png"):
        """Chụp PNG và lưu kích thước nguồn để map tọa độ tap/swipe."""
        cmd = [self.adb_path]
        if self.serial:
            cmd += ["-s", self.serial]

        result = subprocess.run(
            cmd + ["exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.decode(errors="ignore")
                or "ADB screencap thất bại."
            )

        data = result.stdout
        png_signature = b"\x89PNG\r\n\x1a\n"

        if len(data) < 24 or data[:8] != png_signature:
            raise RuntimeError(
                "ADB không trả về PNG hợp lệ. Kiểm tra kết nối và màn hình giả lập."
            )

        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        if width <= 0 or height <= 0:
            raise RuntimeError("Kích thước screenshot không hợp lệ.")

        self.screenshot_size = (width, height)

        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path.resolve())

    def map_coordinates(self, x, y):
        """Quy đổi tọa độ ảnh chụp sang tọa độ Android input."""
        if self.screenshot_size is None:
            raise RuntimeError(
                "Chưa có screenshot gần nhất. Hãy chụp màn hình trước khi tap/swipe."
            )

        source_w, source_h = self.screenshot_size
        target_w, target_h = self.get_display_size()

        source_ratio = source_w / source_h
        target_ratio = target_w / target_h
        ratio_difference = abs(source_ratio - target_ratio) / source_ratio

        if ratio_difference > 0.02:
            raise RuntimeError(
                "Tỷ lệ screenshot và Android khác nhau quá 2%: "
                f"screenshot={source_w}x{source_h}, "
                f"Android={target_w}x{target_h}. "
                "Dừng click để tránh bấm sai vị trí."
            )

        mapped_x = round(float(x) * target_w / source_w)
        mapped_y = round(float(y) * target_h / source_h)

        mapped_x = max(0, min(mapped_x, target_w - 1))
        mapped_y = max(0, min(mapped_y, target_h - 1))
        return mapped_x, mapped_y

    def tap(self, x, y):
        mapped_x, mapped_y = self.map_coordinates(x, y)
        self._run(
            "shell", "input", "tap",
            str(mapped_x), str(mapped_y),
        )
        return mapped_x, mapped_y

    def swipe(self, x1, y1, x2, y2, duration_ms=450):
        start_x, start_y = self.map_coordinates(x1, y1)
        end_x, end_y = self.map_coordinates(x2, y2)

        self._run(
            "shell", "input", "swipe",
            str(start_x), str(start_y),
            str(end_x), str(end_y),
            str(int(duration_ms)),
        )

        return (start_x, start_y), (end_x, end_y)

    def back(self):
        self._run("shell", "input", "keyevent", "4")
        time.sleep(0.1)
