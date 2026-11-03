# Tool Auto

App desktop Windows để dựng video theo mẫu và đăng tự động lên YouTube, TikTok, Facebook Fanpage, Instagram.
Kế hoạch đầy đủ nằm trong [PLAN.md](PLAN.md).

## Chạy app

Bấm đúp vào **`run.bat`**. Lần đầu chạy, file này tự tạo môi trường Python và cài thư viện.
Cần có sẵn **Google Chrome** (để đăng nhập và đăng bài) và **FFmpeg** (để đọc thông tin video).

## Dựng video theo mẫu

1. Trang **Dựng video → Chọn video mẫu...**. Tool đo kích thước, nhịp cắt (độ dài từng cảnh), màu và viền đen của mẫu
   (mất vài giây tới vài phút tùy độ dài video).
2. Thêm **video gốc**: bấm "Thêm video..." hoặc kéo thả file vào danh sách.
3. Chọn **cách dựng**:

   | Cách dựng | Kết quả |
   |---|---|
   | Cắt ghép theo nhịp của mẫu | 1 video dài bằng mẫu, ghép từ các đoạn của video gốc theo đúng nhịp cảnh của mẫu |
   | Cắt video dài thành nhiều clip | Nhiều video, mỗi video lấy từ một phần của video gốc |
   | Giữ nguyên nội dung | Giữ đủ video gốc, chỉ đổi khung hình, màu, chữ, phụ đề |
   | Tự động chọn | Video gốc dài gần bằng mẫu thì giữ nguyên; dài gấp 3 lần trở lên thì cắt nhiều clip; còn lại thì cắt ghép theo nhịp |

4. Tùy chỉnh nếu cần: kích thước, khung hình (cắt đầy khung / nền mờ / viền đen), chỉnh màu giống mẫu, zoom nhẹ,
   mờ dần khi chuyển cảnh, chữ tiêu đề, phụ đề `.srt`.
5. Bấm **Dựng video**. Video thành phẩm nằm trong `E:\ToolAuto-data\renders`.

Muốn dùng lại phong cách cho lần sau: bấm **Lưu thành mẫu phong cách...**, lần sau chọn ở ô "mẫu đã lưu".

Giới hạn hiện tại (chưa có AI):
- Tool chỉ nhận **file video trên máy**, không tải từ link YouTube/TikTok/Facebook.
- Đoạn lấy từ video gốc được rải đều theo thời gian và nhích về điểm chuyển cảnh gần nhất, chưa biết chọn "đoạn hay".
- Chữ trong video mẫu chưa đọc được, bạn tự nhập tiêu đề và phụ đề.
- Chuyển cảnh quá nhẹ (hai cảnh gần giống nhau về màu) có thể không được nhận ra.

## Đăng video lên YouTube lần đầu

1. **Tài khoản → + Thêm tài khoản**, chọn YouTube và đặt tên gợi nhớ.
2. Tool mở một cửa sổ Chrome riêng. Đăng nhập Google trong đó, chờ vào được YouTube Studio rồi **đóng hẳn cửa sổ Chrome**.
   Tool tự kiểm tra, trạng thái chuyển sang **Đang hoạt động**.
3. **Chờ duyệt → + Tạo bài đăng**: chọn video, tick tài khoản, nhập tiêu đề, mô tả, hashtag và giờ đăng.
4. Chọn bài, sửa nội dung nếu cần, bấm **Duyệt**. Bài chuyển sang **Lịch đăng**.
5. Đến giờ, tool tự mở YouTube Studio và đăng. Muốn đăng ngay thì chọn bài trong Lịch đăng và bấm **Đăng ngay**.

Lần đầu nên đăng ở chế độ **Riêng tư** và để bật "Hiện cửa sổ trình duyệt khi đăng" (trang Cài đặt) để theo dõi.

### Khi đăng bị lỗi

- Trang **Lịch đăng → Lỗi / cần xử lý** ghi lý do. Bấm **Ảnh chụp lỗi** để xem màn hình lúc lỗi.
- **Lỗi** thông thường (mạng chậm...): tool tự thử lại sau 5 phút, tối đa theo số lần trong Cài đặt.
- **Cần bạn xử lý** (hết phiên đăng nhập, YouTube báo vượt giới hạn, không thấy xác nhận...): tool không tự thử lại để tránh đăng trùng.
  Xử lý xong thì bấm **Thử lại**.
- Nếu YouTube đổi giao diện khiến tool không tìm thấy nút bấm, sửa file
  [app/uploaders/selectors/youtube.yaml](app/uploaders/selectors/youtube.yaml), không cần khởi động lại app.
- Tool nhận biết "đang tải lên" qua chữ trên YouTube Studio (tiếng Anh hoặc tiếng Việt). Nếu Studio của bạn dùng ngôn ngữ khác,
  thêm chữ đó vào mục `uploading_texts` trong file trên.

## Dữ liệu được lưu ở đâu

| Thứ | Vị trí |
|---|---|
| Cài đặt | `%APPDATA%\ToolAuto\settings.json` |
| API key của AI | Windows Credential Manager (không lưu trong file) |
| Database, hồ sơ Chrome từng tài khoản, ảnh chụp lỗi, nhật ký | Mặc định `E:\ToolAuto-data`, đổi được trong trang Cài đặt |

Tool không lưu mật khẩu. Phiên đăng nhập nằm trong hồ sơ Chrome riêng của từng tài khoản (`profiles\`).

## Chạy test

```bash
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

```bash
.venv\Scripts\python.exe -m pytest -q
```

Test bộ đăng YouTube chạy trên một trang YouTube Studio giả (`tests/fixtures/fake_studio.html`) bằng Chrome thật, không cần mạng hay tài khoản.

## Cấu trúc mã nguồn

```
app\
  main.py          khởi động app
  core\            cài đặt, database, model dữ liệu, quy tắc duyệt và lịch đăng (posting.py)
  editor\          phân tích video mẫu (analyzer), lập kế hoạch cắt (planner), dựng bằng FFmpeg (renderer), phụ đề
  automation\      mở Chrome, luồng nền chạy Playwright
  uploaders\       bộ đăng cho từng nền tảng + selectors\*.yaml
  ai\              giao diện chung cho các nhà cung cấp AI (làm ở GĐ5)
  ui\              cửa sổ chính, các trang, bộ hẹn giờ đăng (scheduler.py)
tests\
```

## Tiến độ

- [x] GĐ0 – Nền móng: khung app, các trang, database, cài đặt
- [x] GĐ1 – Đăng YouTube: tài khoản, tạo bài, duyệt, lịch đăng, tự đăng, thử lại
- [ ] GĐ2 – TikTok, Facebook Fanpage, Instagram (tạm hoãn, ưu tiên phần dựng video)
- [x] GĐ3 – Dựng video theo mẫu (bản không dùng AI)
- [ ] GĐ4 – Khay hệ thống, khởi động cùng Windows, thông báo, đóng gói `.exe`
- [ ] GĐ5 – AI
