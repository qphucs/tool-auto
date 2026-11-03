# Tool Auto

App desktop Windows biến **video kiến thức dài** thành **các video ngắn 45–90 giây** dạng dọc 9:16:
AI chép lời, chia kiến thức, viết kịch bản tiếng Việt, rồi dựng hình động kiểu motion graphics nền tối
kèm giọng AI đọc và phụ đề tô sáng theo từng từ.

Kế hoạch đầy đủ nằm trong [PLAN.md](PLAN.md).

## Cần có trên máy

- **Google Chrome** (dựng hình, chụp trang web) và **FFmpeg** (xử lý video).
- **API key của ít nhất một hãng AI** để viết kịch bản: Gemini, Claude, Groq hoặc OpenRouter. Hoặc Ollama chạy trên máy.

## Cách dùng

Bấm đúp **`run.bat`** (lần đầu tự tạo môi trường Python và cài thư viện).

1. **Cài đặt**: nhập API key, chọn hãng AI và model ở mục "Viết kịch bản" (bấm "Lấy danh sách model" để chọn đúng tên).
   Bấm **Thử giọng** để nghe giọng đọc. Bấm **Lưu cài đặt**.
2. **Dự án → + Thêm video gốc** (hoặc kéo thả file vào bảng) → **Phân tích**.
   Tool chép lời, AI tìm các kiến thức và viết kịch bản cho từng video ngắn.
   Lần đầu sẽ tải model Whisper (~0.5GB) vào thư mục dữ liệu.
3. **Kịch bản**: xem từng video ngắn, sửa chữ, lời đọc, hình minh họa của từng cảnh; thêm/xóa/đổi thứ tự cảnh.
   Bấm **Duyệt và dựng nháp**.
4. **Xem nháp**: xem video 540x960. Cảnh nào chưa ưng thì chọn cảnh đó → **Sửa cảnh đã chọn**,
   sửa xong bấm **Dựng lại nháp** (chỉ các cảnh đã đổi được dựng lại). Chọn nhạc nền nếu muốn.
5. **Dựng bản cuối 1080x1920**. Video nằm ở trang **Thành phẩm** và thư mục `outputs`.
6. **Thương hiệu**: đổi màu, font, logo, tên kênh, cảnh kêu gọi cuối video; bấm **Xem trước** để xem thử.

## Chạy test

```bash
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

```bash
.venv\Scripts\python.exe -m pytest -q
```

Test chạy trọn luồng với video thật nhỏ, Chrome và FFmpeg thật; AI và giọng đọc được thay bằng bản giả
nên không cần mạng hay API key.

Đo tốc độ dựng trên máy: **Cài đặt → Kiểm tra máy**, hoặc `.venv\Scripts\python.exe -m app.render.bench bench-output`.

## Dữ liệu được lưu ở đâu

| Thứ | Vị trí |
|---|---|
| Cài đặt | `%APPDATA%\ToolAuto\settings.json` |
| API key | Windows Credential Manager (không lưu trong file) |
| Dự án (bản chép lời, khung hình, giọng đọc, nháp) | `<thư mục dữ liệu>\projects\<id>\` |
| Video thành phẩm | `<thư mục dữ liệu>\outputs\` |
| Model Whisper | `<thư mục dữ liệu>\models\` |

Thư mục dữ liệu mặc định là `E:\ToolAuto-data`, đổi được trong trang Cài đặt.

## Cách dựng hình

Mỗi cảnh là một trang HTML/CSS/JS trong [app/render/assets](app/render/assets) (`scenes.js` chứa 9 loại cảnh).
Mọi chuyển động chạy theo đồng hồ của tool (`window.__seek(t)`), không dùng CSS animation. Bộ dựng mở trang bằng
Chrome, nhảy tới từng khung hình, chụp ảnh và đẩy thẳng vào FFmpeg; 3 tab Chrome dựng song song.
Mỗi cảnh được lưu đệm theo nội dung, nên sửa một cảnh chỉ phải dựng lại cảnh đó.

## Cấu trúc mã nguồn

```
app\
  main.py          khởi động app
  core\            cài đặt, API key, database (dự án, video ngắn), nhật ký, đọc thông tin video
  ai\              lớp AI dùng chung + Claude (SDK chính thức), Gemini, Groq/OpenRouter/Ollama
  pipeline\        chép lời (transcribe), AI viết kịch bản (writer), khung hình (frames), hình minh họa (visuals),
                   giọng đọc (tts), ghép kịch bản thành cảnh (assemble), điều phối các bước (runner)
  render\          dựng HTML → video (html_renderer), ghép clip + âm thanh (clip), khuôn các loại cảnh (scenes)
    assets\        runtime.js (bộ chạy hoạt ảnh), theme.css, scenes.js, boot.js
  editor\          chạy FFmpeg, tìm điểm chuyển cảnh, phụ đề SRT
  ui\              cửa sổ chính, các trang, ô sửa cảnh, thanh tiến độ chung
tests\
```
