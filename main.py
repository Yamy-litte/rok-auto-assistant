import random
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from adb_controller import ADBController
from image_recognition import ImageRecognizer
from tasks import RoKTasks


BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
ADB_PATH = r"C:\Users\nghia\platform-tools\adb.exe"
DEFAULT_DEVICE = "127.0.0.1:6610"
IMAGE_THRESHOLD = 0.82

FOG_TEMPLATES = [
    "btn_home.png",
    "scout_camp.png",
    "scout_icon.png",
    "btn_explore_1.png",
    "btn_explore_2.png",
    "btn_send_scout.png",
]

FARM_TEMPLATES = [
    "world_map.png", "search_icon.png",
    "food.png", "wood.png", "stone.png", "gold.png",
    "level_1.png", "level_2.png", "level_3.png",
    "level_4.png", "level_5.png", "level_6.png",
    "search_button.png", "resource_node.png",
    "gather.png", "new_troops.png", "march.png",
]


class RoKAutoApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("RoK Assistant - ADB")
        self.geometry("800x740")
        self.minsize(720, 680)

        self.stop_event = threading.Event()
        self.worker = None
        self.tasks = None
        self.adb_connected = False

        self.adb = ADBController(adb_path=ADB_PATH)
        self.recognizer = ImageRecognizer(
            template_dir=str(TEMPLATE_DIR),
            threshold=IMAGE_THRESHOLD,
        )

        self.device_var = tk.StringVar(value=DEFAULT_DEVICE)
        self.enable_fog = tk.BooleanVar(value=True)
        self.enable_farm = tk.BooleanVar(value=False)
        self.scout_wait_var = tk.StringVar(value="120")
        self.resource_vars = {
            name: tk.BooleanVar(value=(name == "Food"))
            for name in ("Food", "Wood", "Stone", "Gold")
        }
        self.level_var = tk.StringVar(value="4")
        self.status_var = tk.StringVar(value="Chưa kết nối ADB")

        self._build_ui()
        self._log(f"Thư mục template: {TEMPLATE_DIR}")
        self._log("Sẵn sàng. Kết nối BlueStacks trước khi chạy.")
        self.protocol("WM_DELETE_WINDOW", self.close_app)

    def _build_ui(self):
        ctk.CTkLabel(
            self,
            text="Rise of Kingdoms - ADB Assistant",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=12)

        connection = ctk.CTkFrame(self)
        connection.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(connection, text="ADB host:port").pack(side="left", padx=8)
        ctk.CTkEntry(connection, textvariable=self.device_var, width=175).pack(side="left", padx=5)
        ctk.CTkButton(connection, text="Kết nối", command=self.connect_device).pack(side="left", padx=5)
        ctk.CTkButton(connection, text="Kiểm tra", command=self.check_device, fg_color="gray").pack(side="left", padx=5)

        ctk.CTkLabel(self, textvariable=self.status_var, text_color="#16A34A").pack(anchor="w", padx=20)

        feature_frame = ctk.CTkFrame(self)
        feature_frame.pack(fill="x", padx=16, pady=7)
        ctk.CTkLabel(feature_frame, text="Tính năng", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=6)
        ctk.CTkCheckBox(feature_frame, text="Auto dò mây (Scout)", variable=self.enable_fog).pack(anchor="w", padx=12, pady=4)
        ctk.CTkCheckBox(feature_frame, text="Auto farm tài nguyên", variable=self.enable_farm).pack(anchor="w", padx=12, pady=4)

        wait_row = ctk.CTkFrame(feature_frame, fg_color="transparent")
        wait_row.pack(fill="x", padx=8, pady=(4, 8))
        ctk.CTkLabel(wait_row, text="Nghỉ khi hết trinh sát (giây)").pack(side="left", padx=5)
        ctk.CTkEntry(wait_row, textvariable=self.scout_wait_var, width=90).pack(side="left", padx=6)
        ctk.CTkLabel(wait_row, text="Mặc định 120 giây, ngẫu nhiên ±10 giây", text_color="gray").pack(side="left", padx=5)

        farm_frame = ctk.CTkFrame(self)
        farm_frame.pack(fill="x", padx=16, pady=7)
        ctk.CTkLabel(farm_frame, text="Tài nguyên ưu tiên", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=6)
        resource_row = ctk.CTkFrame(farm_frame, fg_color="transparent")
        resource_row.pack(fill="x", padx=8)
        for name, var in self.resource_vars.items():
            ctk.CTkCheckBox(resource_row, text=name, variable=var).pack(side="left", padx=9)

        level_row = ctk.CTkFrame(farm_frame, fg_color="transparent")
        level_row.pack(fill="x", padx=8, pady=8)
        ctk.CTkLabel(level_row, text="Cấp mỏ ưu tiên").pack(side="left", padx=5)
        ctk.CTkOptionMenu(level_row, variable=self.level_var, values=[str(i) for i in range(1, 7)]).pack(side="left", padx=8)

        controls = ctk.CTkFrame(self)
        controls.pack(fill="x", padx=16, pady=7)
        ctk.CTkButton(controls, text="Start", width=130, command=self.start_tasks).pack(side="left", padx=7, pady=10)
        ctk.CTkButton(controls, text="Stop", width=130, command=self.stop_tasks, fg_color="#9B3434", hover_color="#762828").pack(side="left", padx=7, pady=10)
        ctk.CTkButton(controls, text="Chụp màn hình", width=130, command=self.save_screenshot, fg_color="gray").pack(side="left", padx=7, pady=10)
        ctk.CTkButton(controls, text="Kiểm tra template", width=150, command=self.check_templates).pack(side="left", padx=7, pady=10)

        ctk.CTkLabel(self, text="Log hoạt động", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=18, pady=(8, 0))
        self.log_box = ctk.CTkTextbox(self, height=250)
        self.log_box.pack(fill="both", expand=True, padx=16, pady=8)

    def _log(self, message):
        def write_log():
            if self.winfo_exists():
                self.log_box.insert("end", message + "\n")
                self.log_box.see("end")
        self.after(0, write_log)

    def connect_device(self):
        address = self.device_var.get().strip()
        if not address:
            messagebox.showwarning("ADB", "Hãy nhập địa chỉ ADB.")
            return
        try:
            output = self.adb.connect(address)
            devices = self.adb.devices()
            if address not in devices:
                raise RuntimeError("Thiết bị chưa xuất hiện trong adb devices.")
            self.adb_connected = True
            self.status_var.set(f"Đã kết nối: {address}")
            self._log(f"ADB: {output}")
            self._log("Kết nối BlueStacks thành công.")
        except Exception as exc:
            self.adb_connected = False
            self.status_var.set("Kết nối ADB thất bại")
            self._log(f"Lỗi ADB: {exc}")
            messagebox.showerror("Lỗi ADB", str(exc))

    def check_device(self):
        try:
            devices = self.adb.devices()
            address = self.device_var.get().strip()
            self.adb_connected = address in devices
            self.status_var.set(f"Đã kết nối: {address}" if self.adb_connected else "Thiết bị chưa kết nối")
            self._log("Thiết bị ADB: " + (", ".join(devices) if devices else "Không có thiết bị"))
        except Exception as exc:
            self._log(f"Lỗi kiểm tra ADB: {exc}")

    def check_templates(self):
        required = []
        if self.enable_fog.get():
            required.extend(FOG_TEMPLATES)
        if self.enable_farm.get():
            required.extend(FARM_TEMPLATES)
        missing = sorted(set(name for name in required if not (TEMPLATE_DIR / name).is_file()))
        self._log("========== KIỂM TRA TEMPLATE ==========")
        self._log(f"Thư mục: {TEMPLATE_DIR}")
        if missing:
            self._log("Thiếu template: " + ", ".join(missing))
            messagebox.showwarning("Thiếu template", "Các file còn thiếu:\n\n" + "\n".join(missing))
        else:
            self._log("Đã tìm thấy đủ template cho các tính năng đang chọn.")
            messagebox.showinfo("Template", "Đã tìm thấy đủ template cho các tính năng đang chọn.")

    def save_screenshot(self):
        if not self.adb_connected:
            messagebox.showwarning("ADB", "Hãy kết nối BlueStacks trước.")
            return
        try:
            path = self.adb.screenshot(str(BASE_DIR / "screen_debug.png"))
            self._log(f"Đã lưu screenshot: {path}")
            messagebox.showinfo("Screenshot", f"Đã chụp màn hình:\n{path}")
        except Exception as exc:
            self._log(f"Lỗi chụp màn hình: {exc}")
            messagebox.showerror("Screenshot", str(exc))

    def start_tasks(self):
        if self.worker and self.worker.is_alive():
            self._log("Tác vụ đang chạy.")
            return
        if not self.adb_connected:
            messagebox.showwarning("ADB", "Hãy kết nối BlueStacks trước.")
            return

        fog_enabled = self.enable_fog.get()
        farm_enabled = self.enable_farm.get()
        if not fog_enabled and not farm_enabled:
            messagebox.showwarning("Tác vụ", "Hãy chọn ít nhất một tính năng.")
            return

        try:
            scout_wait_seconds = int(self.scout_wait_var.get().strip())
            if not 10 <= scout_wait_seconds <= 3600:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Thời gian nghỉ", "Nhập số nguyên từ 10 đến 3600 giây.")
            return

        resources = [name for name, var in self.resource_vars.items() if var.get()]
        if farm_enabled and not resources:
            messagebox.showwarning("Farm", "Hãy chọn ít nhất một loại tài nguyên.")
            return

        required = []
        if fog_enabled:
            required.extend(FOG_TEMPLATES)
        if farm_enabled:
            required.extend(FARM_TEMPLATES)
        missing = sorted(set(name for name in required if not (TEMPLATE_DIR / name).is_file()))
        if missing:
            messagebox.showerror("Thiếu template", "Không thể chạy. Thiếu:\n\n" + "\n".join(missing))
            return

        preferred_level = int(self.level_var.get())
        self.stop_event.clear()
        self.tasks = RoKTasks(self.adb, self.recognizer, self._log, self.stop_event)
        self.worker = threading.Thread(
            target=self._run_tasks,
            args=(fog_enabled, farm_enabled, resources, preferred_level, scout_wait_seconds),
            daemon=True,
        )
        self.worker.start()
        self._log("Đã khởi chạy tác vụ.")

    def _run_tasks(self, fog_enabled, farm_enabled, resources, preferred_level, scout_wait_seconds):
        try:
            while not self.stop_event.is_set():
                fog_result = None
                if fog_enabled and not self.stop_event.is_set():
                    self._log("Bắt đầu đợt dò mây.")
                    fog_result = self.tasks.run_fog_cycle()

                if farm_enabled and not self.stop_event.is_set():
                    self._log("Bắt đầu chu kỳ Auto Farm.")
                    self.tasks.run_farm_cycle(resources, preferred_level)

                if self.stop_event.is_set():
                    break

                if fog_enabled and isinstance(fog_result, dict) and fog_result.get("status") == "exhausted":
                    jitter = random.uniform(-10.0, 10.0)
                    rest_seconds = max(1.0, scout_wait_seconds + jitter)
                    sent = fog_result.get("sent", 0)
                    self._log(
                        f"Hết trinh sát rảnh. Đã gửi {sent} trinh sát trong đợt. "
                        f"Nghỉ {rest_seconds:.1f} giây trước lần kiểm tra tiếp theo."
                    )
                    self.stop_event.wait(rest_seconds)
                elif fog_enabled and isinstance(fog_result, dict) and fog_result.get("status") == "error":
                    self._log("Chu trình dò mây gặp trạng thái không mong đợi. Nghỉ 10 giây rồi kiểm tra lại.")
                    self.stop_event.wait(10)
                elif not fog_enabled and farm_enabled:
                    self.stop_event.wait(5)
        except Exception as exc:
            self._log(f"Tác vụ dừng do lỗi: {exc}")
        finally:
            self._log("Worker đã kết thúc.")

    def stop_tasks(self):
        if not self.worker or not self.worker.is_alive():
            self._log("Hiện không có tác vụ nào đang chạy.")
            return
        self.stop_event.set()
        self._log("Đã gửi yêu cầu Stop. Chương trình sẽ dừng sau thao tác hiện tại.")

    def close_app(self):
        self.stop_event.set()
        self.destroy()


if __name__ == "__main__":
    app = RoKAutoApp()
    app.mainloop()
