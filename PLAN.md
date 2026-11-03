# Kế hoạch: Tool Auto – Biến video kiến thức dài thành video ngắn

> Trạng thái: **Đã làm P0–P5**, trừ đóng gói `.exe`. Chưa thử với API key AI thật (Claude/Gemini/Groq/OpenRouter),
> Google Cloud TTS và giọng Windows; đã thử thật Edge TTS, Whisper, dựng hình.
>
> Thay đổi so với kế hoạch ban đầu (đều do đo thực tế):
> - Mỗi cảnh dựng thành một file riêng và lưu đệm theo nội dung, thay vì cả clip trên một dòng thời gian:
>   sửa một cảnh chỉ dựng lại cảnh đó.
> - Cảnh kêu gọi cuối video do tool tự thêm từ trang Thương hiệu, AI không viết cảnh này.
> - Edge TTS lỗi ngẫu nhiên ~40% yêu cầu vào lúc dịch vụ kém ổn định: tool thử lại tối đa 7 lần, xen kẽ hai chế độ đọc.
> - faster-whisper 1.2 lỗi khi đọc file với PyAV 19: tool tự đọc WAV rồi đưa dữ liệu thẳng cho Whisper.
> - Tốc độ dựng đo được trên máy (RTX 2050, i5-11400H): nháp 540x960 ~0.9 giây/giây video,
>   bản cuối 1080x1920 ~1.1–1.4 giây/giây video. Không cần phương án dự phòng.
>
> Bản mới **thay thế** app cũ (đăng bài YouTube và dựng theo mẫu). Code cũ vẫn nằm trong lịch sử git
> (commit `1c367a7`) để lấy lại khi cần, ví dụ phần đăng bài.

## 1. Mục tiêu

Bạn đưa vào **một video gốc dài** (hướng dẫn, chia sẻ kiến thức, slide, người nói, quay màn hình...).
Tool tự:

1. Chép lời video gốc (tiếng Việt hoặc tiếng Anh).
2. Dùng AI tìm các **kiến thức** trong đó, mỗi kiến thức thành **một video ngắn 45–90 giây**.
3. Viết **kịch bản tiếng Việt ngắn gọn** cho từng video, chia thành các cảnh.
4. Chờ **bạn duyệt kịch bản**.
5. Dựng **video nháp** (độ phân giải thấp, nhanh) để bạn xem và sửa từng cảnh.
6. Dựng **bản cuối 1080x1920**: hình động kiểu motion graphics nền tối, giọng AI đọc, phụ đề tô sáng theo từng từ, nhạc nền.

Video mẫu bạn gửi **chỉ dùng tham khảo phong cách**. Tool không sao chép chữ, số liệu, logo hay ảnh của video đó.

## 2. Những gì đã chốt

| Hạng mục | Quyết định |
|---|---|
| Video gốc | Mọi dạng: slide, người nói, quay màn hình, video trên mạng, podcast |
| Ngôn ngữ | Gốc tiếng Việt hoặc tiếng Anh, thành phẩm luôn tiếng Việt |
| Số video, độ dài | AI tự quyết, mỗi video 45–90 giây |
| AI viết kịch bản | Nhiều hãng, chọn trong Cài đặt: Gemini, Claude, Groq, OpenRouter, Ollama |
| Chép lời | Whisper chạy trên máy (miễn phí, offline) |
| Giọng đọc | AI đọc (TTS), nhiều lựa chọn, mặc định Edge TTS giọng **nữ** |
| Duyệt | Duyệt kịch bản trước khi dựng, sau đó xem nháp và sửa từng cảnh |
| Hình minh họa | Khung hình từ video gốc, hình vẽ bằng code, ảnh chụp trang web được nhắc tới |
| Màu sắc | Bản đầu dùng theme tối công nghệ. Trang Thương hiệu để bạn đổi màu, logo sau |
| Kênh | Logo/tên kênh ở góc và cảnh kêu gọi cuối video, bật/tắt và sửa trong Cài đặt |
| Nhạc nền | Chọn file nhạc mỗi lần dựng (tùy chọn) |
| Độ phân giải | Bản cuối 1080x1920, 30fps. Bản nháp 540x960 cho nhanh |
| App | Thay thế app cũ |

## 3. Luồng hoạt động

```
Video gốc
  │ 1. Đọc thông tin, tách âm thanh (FFmpeg)
  │ 2. Chép lời có mốc thời gian (Whisper)
  │ 3. Tách khung hình ứng viên tại các điểm chuyển cảnh (FFmpeg)
  ▼
Bản chép lời + khung hình
  │ 4. AI chia kiến thức, viết kịch bản tiếng Việt cho từng video (dạng JSON theo khuôn cố định)
  ▼
Kịch bản ──► [Bạn duyệt: sửa chữ, bỏ/thêm cảnh, đổi thứ tự, bỏ cả video]
  │ 5. Chuẩn bị hình: AI chọn khung hình hợp với từng cảnh, chụp trang web, hoặc vẽ bằng code
  │ 6. Tạo giọng đọc (TTS) + mốc thời gian từng từ
  │ 7. Dựng nháp 540x960
  ▼
Video nháp ──► [Bạn xem, sửa từng cảnh: chữ, hình, giọng đọc lại] ──► dựng lại cảnh đó
  │ 8. Dựng bản cuối 1080x1920 + nhạc nền
  ▼
Video thành phẩm
```

**Trạng thái của mỗi video:**
`Đang phân tích → Chờ duyệt kịch bản → Đang dựng nháp → Chờ xem nháp → Đang dựng bản cuối → Xong`

## 4. Phần AI

### 4.1 Lớp AI dùng chung
- Một giao diện chung cho mọi hãng, gồm 2 khả năng: **viết chữ** và **đọc ảnh**.
- Groq, OpenRouter, Ollama dùng chung chuẩn API kiểu OpenAI. Gemini và Claude có bộ chuyển riêng.
- Có thể chọn **hãng khác nhau cho từng việc**, ví dụ Gemini viết kịch bản, Ollama đọc ảnh.
- API key lưu trong **Windows Credential Manager**, không lưu trong file.
- Nút **"Thử kết nối"** trong Cài đặt cho từng hãng.

### 4.2 AI làm những việc gì
| Việc | Đầu vào | Đầu ra |
|---|---|---|
| Chia kiến thức | Bản chép lời có mốc thời gian | Danh sách video: tiêu đề, đoạn thời gian trong video gốc |
| Viết kịch bản | Bản chép lời của đoạn đó | Các cảnh: loại cảnh, tiêu đề, từ nhấn màu, ý ngắn, lời đọc |
| Dịch | Bản chép lời tiếng Anh | Kịch bản tiếng Việt (làm chung bước viết kịch bản) |
| Chọn khung hình | Khung hình ứng viên + nội dung cảnh | Khung hình hợp nhất (hoặc "không dùng ảnh") |
| Tìm trang web | Bản chép lời | Các địa chỉ web được nhắc tới để chụp |

- AI phải trả lời đúng **khuôn JSON**. Tool kiểm tra, sai thì tự hỏi lại.
- Nếu không có model đọc ảnh: tool chọn khung hình rõ nét nhất trong đoạn thời gian của cảnh.

### 4.3 Chép lời và giọng đọc
- **Whisper** (thư viện faster-whisper) chạy bằng CPU mặc định. Model `small` khoảng 0.5GB, lưu ở ổ E.
  GPU chỉ bật nếu cài đủ thư viện CUDA (tùy chọn, không bắt buộc).
- **TTS:** Edge TTS (miễn phí, cần mạng, thư viện không chính thức), Google Cloud TTS (chính thức, có hạn mức miễn phí),
  hoặc giọng chạy trên máy. Mặc định: Edge TTS giọng nữ `vi-VN-HoaiMyNeural`.
- **Phụ đề tô sáng** lấy mốc thời gian từ chính giọng đọc AI (không phải từ video gốc).
  Nếu dịch vụ TTS không trả mốc từng từ, tool chạy Whisper trên file giọng đọc để lấy.

## 5. Phần hình ảnh

### 5.1 Cách dựng
- Mỗi cảnh là một trang **HTML/CSS/JS**. Mọi chuyển động chạy theo **đồng hồ của tool**, không theo thời gian thực.
- Playwright mở trang, nhảy tới từng khung hình (1/30 giây), chụp ảnh và đẩy thẳng vào FFmpeg.
- Kết quả giống hệt nhau mỗi lần dựng, và không bị giật dù máy chậm.

### 5.2 Các loại cảnh (bản đầu)
| Loại | Dùng cho |
|---|---|
| Mở đầu (hook) | Tiêu đề lớn 2 dòng, một từ nhấn màu, các nhãn chủ đề |
| Con số | Số liệu lớn chạy từ 0, kèm chú thích |
| Câu hỏi / vấn đề | Câu hỏi lớn + hình minh họa |
| Ảnh chụp | Ảnh trong khung trình duyệt hoặc thẻ, có phóng to vào chi tiết |
| Các bước | Danh sách đánh số xuất hiện lần lượt ("01 — ÁP DỤNG") |
| Sơ đồ | Các nút nối nhau bằng mũi tên (A → B → C) |
| Lưu ý / cảnh báo | Thẻ nhấn màu đỏ/vàng |
| Tóm tắt | Danh sách tích xanh |
| Kêu gọi | Câu hỏi gợi bình luận + nút Đăng ký/Theo dõi (bật/tắt được) |

Thành phần dùng chung: nền tối có hạt sáng chuyển động, logo/tên kênh ở góc, phụ đề tô sáng phía dưới.

### 5.3 Nguồn hình
- **Khung hình từ video gốc:** tách tại điểm chuyển cảnh, AI chọn khung phù hợp.
- **Ảnh chụp trang web:** chỉ trang công khai, không đăng nhập.
- **Vẽ bằng code:** icon, thẻ, sơ đồ, biểu đồ.
- **Ảnh bạn thêm:** khi duyệt kịch bản hoặc khi sửa nháp.

### 5.4 Thương hiệu
Trang **Thương hiệu**: màu nền, màu chữ, 4 màu nhấn, font, logo, tên kênh, câu kêu gọi, bật/tắt logo và cảnh kêu gọi.
Đổi ở đây thì mọi video dựng sau đều theo.

## 6. Giao diện app mới

| Trang | Nội dung |
|---|---|
| **Dự án** | Danh sách video gốc đã đưa vào, trạng thái, nút "Thêm video gốc" (chọn file hoặc kéo thả) |
| **Kịch bản** | Các video ngắn AI đề xuất. Sửa từng cảnh: loại cảnh, chữ, lời đọc, hình. Bỏ hoặc thêm cảnh. Duyệt để dựng nháp |
| **Xem nháp** | Xem video nháp, chọn một cảnh để sửa và dựng lại riêng cảnh đó, chọn nhạc nền, dựng bản cuối |
| **Thành phẩm** | Các video đã xong, mở file, mở thư mục |
| **Thương hiệu** | Màu, logo, tên kênh, cảnh kêu gọi |
| **Cài đặt** | Hãng AI và API key cho từng việc, Whisper, TTS và giọng, thư mục dữ liệu |
| **Nhật ký** | Nhật ký hoạt động |

Việc nặng (chép lời, gọi AI, dựng video) chạy ở luồng nền, có thanh tiến độ và nút Hủy.

## 7. Công nghệ

| Phần | Công nghệ | Ghi chú |
|---|---|---|
| App | Python 3.12 + PySide6 | Giữ từ bản cũ |
| Database | SQLite | Bảng mới: dự án, video ngắn, cảnh, hình |
| Video | FFmpeg | Đã có trên máy |
| Dựng hình | HTML/CSS/JS + Playwright + Chrome | Đã có trên máy |
| Chép lời | faster-whisper | Cài mới, khoảng 0.5GB model |
| TTS | edge-tts, Google Cloud TTS (tùy chọn) | Cài mới, nhỏ |
| AI | httpx gọi API trực tiếp | Không cần thư viện riêng của từng hãng |

**Giữ lại từ bản cũ:** cài đặt, lưu API key, database, nhật ký, chạy FFmpeg, mở Chrome bằng Playwright, đọc phụ đề.
**Gỡ đi:** đăng bài YouTube, tài khoản, lịch đăng, dựng theo mẫu, các trang cũ.

## 8. Lộ trình

| Giai đoạn | Nội dung | Kết quả bạn kiểm tra được |
|---|---|---|
| **P0 – Thử tốc độ + dọn app** | Gỡ phần cũ, khung app mới. Dựng thử 1 cảnh 10 giây bằng HTML → video để **đo tốc độ trên máy bạn** | Video 10 giây theme tối + số liệu tốc độ dựng |
| **P1 – Thư viện cảnh** | 9 loại cảnh, theme tối, phụ đề tô sáng. Dựng từ một kịch bản viết tay | Video 60 giây hoàn chỉnh (chưa có giọng) |
| **P2 – Giọng đọc** | Edge TTS, Google TTS, giọng trên máy. Khớp phụ đề theo giọng | Video có giọng đọc khớp phụ đề |
| **P3 – AI viết kịch bản** | Whisper, lớp AI nhiều hãng, chia kiến thức, viết kịch bản, trang Kịch bản để duyệt | Đưa video gốc vào → ra các kịch bản để duyệt |
| **P4 – Hình ảnh + nháp** | Khung hình từ video gốc, chụp web, xem nháp, sửa từng cảnh, nhạc nền, bản cuối | **Luồng đầy đủ** từ video gốc tới thành phẩm |
| **P5 – Hoàn thiện** | Trang Thương hiệu, đóng gói `.exe`, hướng dẫn sử dụng | Cài và dùng như phần mềm bình thường |

Hết mỗi giai đoạn mình báo để bạn thử, rồi mới làm tiếp.

## 9. Rủi ro và giới hạn

- **Tốc độ dựng:** chụp 30 khung hình mỗi giây video có thể chậm (ước tính vài phút cho mỗi video 60 giây).
  P0 sẽ đo thực tế. Nếu quá chậm, phương án dự phòng: dựng các lớp tĩnh bằng HTML rồi để FFmpeg làm chuyển động.
- **Edge TTS không chính thức:** có thể ngừng hoạt động bất cứ lúc nào. Vì vậy có sẵn Google TTS và giọng trên máy để đổi.
- **Chất lượng AI:** kịch bản tiếng Việt tốt hay không phụ thuộc hãng AI. Model nhỏ chạy trên GPU 4GB sẽ yếu.
  Gói miễn phí của các hãng có giới hạn và hay thay đổi.
- **Chép lời chậm trên CPU:** video 30 phút có thể mất 10 phút trở lên.
- **Bản quyền:** khung hình và nội dung lấy từ video của người khác vẫn thuộc về họ.
  Tool viết lại lời và dựng hình mới, nhưng dùng khung hình gốc vẫn có rủi ro. Bạn tự chịu trách nhiệm với nguồn video.
- **Ổ đĩa:** model Whisper, khung hình tạm và video đều để ở **ổ E** (ổ C chỉ còn khoảng 3GB).

## 10. Cần bạn chuẩn bị

1. **API key của ít nhất một hãng AI** để viết kịch bản (nên có Gemini). Cần từ P3.
2. **Một video gốc để thử** (5–15 phút, nên là video của bạn hoặc được phép dùng). Cần từ P3.
3. Vài file nhạc nền có quyền dùng (không bắt buộc). Cần từ P4.
