
import subprocess
from pathlib import Path
import time


class ADBController:
    """Điều khiển BlueStacks thông qua Android Debug Bridge."""

    def __init__(self, adb_path=r"C:\Users\nghia\platform-tools\adb.exe"):
        self.adb_path = str(Path(adb_path))
        self.serial = None

        # Kiểm tra adb.exe có tồn tại không.
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
            timeout=timeout
        )

        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip()
                or result.stdout.strip()
                or "ADB command failed"
            )

        return result.stdout.strip()

    def connect(self, address):
        """Kết nối tới BlueStacks qua địa chỉ host:port."""

        result = subprocess.run(
            [self.adb_path, "connect", address],
            capture_output=True,
            text=True,
            timeout=15
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
        return output

    def devices(self):
        """Lấy danh sách thiết bị ADB."""

        output = subprocess.run(
            [self.adb_path, "devices"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True
        ).stdout

        return [
            line.split()[0]
            for line in output.splitlines()[1:]
            if len(line.split()) >= 2
            and line.split()[1] == "device"
        ]

    def screenshot(self, destination="screen.png"):
        """Chụp màn hình BlueStacks và lưu thành PNG."""

        cmd = [self.adb_path]

        if self.serial:
            cmd += ["-s", self.serial]

        result = subprocess.run(
            cmd + ["exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=30
        )

        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.decode(errors="ignore")
            )

        path = Path(destination)
        path.write_bytes(result.stdout)

        return str(path.resolve())

    def tap(self, x, y):
        """Chạm vào tọa độ màn hình."""

        self._run(
            "shell", "input", "tap",
            str(int(x)), str(int(y))
        )

        time.sleep(0.15)

    def swipe(self, x1, y1, x2, y2, duration_ms=450):
        """Vuốt màn hình."""

        self._run(
            "shell", "input", "swipe",
            str(int(x1)), str(int(y1)),
            str(int(x2)), str(int(y2)),
            str(int(duration_ms))
        )

    def back(self):
        """Nhấn nút Back của Android."""

        self._run("shell", "input", "keyevent", "4")
