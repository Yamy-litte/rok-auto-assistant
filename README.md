# RoK ADB Assistant (prototype)

Công cụ mẫu điều khiển giả lập Android qua ADB và nhận diện giao diện bằng OpenCV.
Không inject bộ nhớ, không đọc dữ liệu nội bộ game. Đây là bộ khung cần hiệu chỉnh
template theo đúng phiên bản game, ngôn ngữ và giao diện giả lập của bạn.

## 1. Cài đặt

- Cài Android SDK Platform Tools và thêm `adb` vào PATH.
- Mở RoK trong giả lập, bật ADB debugging / Android debugging.
- Đặt độ phân giải giả lập 1280x720 và DPI 240.
- Python 3.10+.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 2. Kết nối

Nhập địa chỉ ADB của giả lập, ví dụ `127.0.0.1:5555`.
Port phụ thuộc giả lập; kiểm tra trong cài đặt ADB của BlueStacks/LDPlayer/MEmu.
Không mặc định mọi giả lập đều dùng cùng port.

## 3. Template cần tự chụp

Cắt ảnh PNG sát biểu tượng/nút, không kèm vùng nền thừa, từ screenshot 1280x720:

- `scout_icon.png`: kính viễn vọng/trinh sát trên màn hình chính.
- `scout_camp.png`: nút mở Scout Camp (nếu dùng cách này).
- `explore.png`: nút Explore trong giao diện trinh sát.
- `explore_confirm.png`: nút Explore xác nhận nếu phiên bản game có bước này.
- `send.png`: nút Send.
- `world_map.png`: nút trở về bản đồ thế giới.
- `search_icon.png`: kính lúp tìm kiếm.
- `food.png`, `wood.png`, `stone.png`, `gold.png`: biểu tượng loại mỏ trong bảng tìm kiếm.
- `level_1.png` ... `level_6.png`: lựa chọn cấp mỏ.
- `search_button.png`: nút Search trong bảng tìm kiếm.
- `resource_node.png`: một mẫu nhận diện mỏ trên bản đồ (cắt vùng biểu tượng mỏ).
- `gather.png`: nút Gather.
- `new_troops.png`: nút New Troops.
- `march.png`: nút March.

Các template phải khớp tỷ lệ hiển thị. Nếu game có nhiều giao diện khác nhau,
hãy chụp template riêng và bổ sung logic lựa chọn. Không dùng ảnh nén/mờ.

## 4. Những phần cần hiệu chỉnh trước khi chạy thật

- Luồng RoK có thể khác theo phiên bản, trạng thái tài khoản, nhiệm vụ hướng dẫn,
  popup, ngôn ngữ và số lượng đội quân. Prototype này chỉ thao tác khi tìm thấy template.
- Chức năng farm hiện chưa có OCR để đọc chính xác `0/5`, chưa tự kiểm tra mỏ bị chiếm
  và chưa tự đổi cấp mỏ. Cần bổ sung template trạng thái mỏ bận / quân đang tới,
  hoặc OCR vùng số lượt và vòng lặp cấp độ có giới hạn.
- `run_farm_cycle` hiện chọn tài nguyên đầu tiên được tích. Để luân phiên ưu tiên,
  có thể mở rộng hàng đợi tài nguyên.
- Không có cơ chế đảm bảo tránh phát hiện/khóa tài khoản. Random delay chỉ giúp UI
  có thời gian phản hồi và giảm lỗi thao tác quá nhanh. Việc tự động hóa có thể vi phạm
  điều khoản trò chơi; tự chịu trách nhiệm khi sử dụng.

## 5. Lưu ý an toàn

Chạy thử từng nút với tài khoản phụ, quan sát màn hình và dùng Stop nếu giao diện
khác dự kiến. Không chạy khi có popup hoặc màn hình chưa được nhận diện.
