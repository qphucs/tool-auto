# Kế hoạch dự án: Tool Auto – Dựng & đăng video tự động

> Trạng thái: **Đã duyệt**. GĐ0, GĐ1 và GĐ3 đã xong. GĐ1 chưa thử với tài khoản YouTube thật.
> Theo yêu cầu, làm GĐ3 (dựng video theo mẫu) trước GĐ2; phần tài khoản và đăng bài tạm hoãn.
> GĐ3 dùng FFmpeg để phát hiện chuyển cảnh thay cho PySceneDetect, nên không phải cài thêm thư viện.
>
> Thay đổi so với kế hoạch ban đầu: lịch đăng dùng bộ hẹn giờ của Qt kiểm tra database mỗi 15 giây thay cho APScheduler
> (đơn giản hơn, không cần thêm thư viện). Trang Lịch đăng hiện dạng bảng, chưa có kéo thả theo lịch tuần.

## 1. Mục tiêu

App desktop Windows giúp bạn:

1. **Dựng video theo mẫu**: đưa vào một video mẫu, tool phân tích phong cách (nhịp cắt, khung hình, chữ, phụ đề) rồi dựng video gốc của bạn theo đúng phong cách đó.
2. **Đăng tự động** lên YouTube, TikTok, Facebook Fanpage, Instagram, với nhiều tài khoản trên mỗi nền tảng.
3. **Duyệt trước khi đăng**: mọi video phải được bạn duyệt rồi mới vào lịch đăng.
4. **Tích hợp AI** (giai đoạn sau): viết tiêu đề, mô tả, hashtag, hiểu nội dung video, chọn đoạn hay, ra lệnh bằng chat.

## 2. Những gì đã chốt

| Hạng mục | Quyết định |
|---|---|
| Nền tảng | YouTube, TikTok, Facebook Fanpage, Instagram |
| Số tài khoản | Nhiều tài khoản mỗi nền tảng, thiết kế từ đầu |
| Cách đăng | Tự động thao tác trình duyệt (không dùng API chính thức) |
| Giao diện | App desktop Windows |
| Duyệt bài | Bắt buộc duyệt trước khi đăng |
| Máy chạy | Bật gần như 24/7, tool chạy nền dưới khay hệ thống |
| Số lượng | Dưới 10 video/ngày |
| Phiên bản đầu | Cả dựng video lẫn đăng bài, ở mức cơ bản |
| AI | Làm sau. Bản đầu chỉ chừa sẵn chỗ cắm để thêm AI |
| Nguồn video | Bạn tự chịu trách nhiệm. Tool chỉ làm việc với file video có sẵn trên máy |

## 3. Công nghệ

| Phần | Công nghệ | Lý do |
|---|---|---|
| Ngôn ngữ | Python 3.12 (đã có trên máy) | Hệ sinh thái xử lý video và tự động hóa mạnh |
| Giao diện | PySide6 (Qt) | App desktop thật, chạy mượt, có icon khay hệ thống |
| Tự động trình duyệt | Playwright + Chrome | Ổn định, mỗi tài khoản có một hồ sơ trình duyệt riêng |
| Xử lý video | FFmpeg (đã có trên máy) + PySceneDetect | Cắt, ghép, đổi khung hình, chèn chữ, đo nhịp cắt |
| Cơ sở dữ liệu | SQLite | Gọn, không cần cài server |
| Lịch đăng | APScheduler | Hẹn giờ, đăng bù khi lỡ lịch |
| Đóng gói | PyInstaller | Xuất ra file `.exe` để chạy như phần mềm bình thường |

## 4. Luồng hoạt động

```
Video gốc ──► [Dựng theo mẫu] ──► Video thành phẩm
                    ▲                    │
             Mẫu phong cách              ▼
         (phân tích từ video mẫu)  Soạn bài đăng: tiêu đề, mô tả, hashtag,
                                   chọn tài khoản, chọn giờ đăng
                                         │
                                         ▼
                                  Hàng chờ duyệt ──► Bạn duyệt / sửa / từ chối
                                         │
                                         ▼
                                  Lịch đăng ──► Đăng qua trình duyệt ──► Nhật ký
                                                        │
                                          Lỗi/captcha ──► Dừng + báo bạn
```

Trạng thái của mỗi bài đăng: `Nháp → Chờ duyệt → Đã lên lịch → Đang đăng → Thành công / Lỗi / Cần bạn xử lý`

## 5. Các module chính

### 5.1 Quản lý tài khoản
- Mỗi tài khoản có **một hồ sơ trình duyệt riêng** để lưu phiên đăng nhập, các tài khoản không lẫn vào nhau.
- Lần đầu thêm tài khoản: tool mở trình duyệt, **bạn tự đăng nhập** (kể cả xác minh 2 bước). Tool không lưu mật khẩu.
- Tool kiểm tra định kỳ xem phiên đăng nhập còn hiệu lực không và báo khi cần đăng nhập lại.
- Có thể gắn nhãn hoặc nhóm tài khoản (ví dụ "Kênh nấu ăn") để đăng hàng loạt.

### 5.2 Bộ đăng bài (uploader)
- Cùng một khuôn chung, mỗi nền tảng có một bộ đăng riêng:
  - **YouTube**: qua YouTube Studio. Hỗ trợ video thường và Shorts, tiêu đề, mô tả, thẻ, chế độ hiển thị, hẹn giờ ngay trên YouTube.
  - **TikTok**: qua TikTok Studio trên web. Hỗ trợ mô tả, hashtag, quyền riêng tư.
  - **Facebook Fanpage** và **Instagram**: qua Meta Business Suite trên web, một nơi đăng được cả hai. Nếu không ổn định thì chuyển sang đăng trực tiếp trên facebook.com và instagram.com.
- Vị trí các nút bấm (selector) được **tách ra file cấu hình riêng**. Khi nền tảng đổi giao diện, chỉ cần sửa file này, không phải sửa code.
- Đăng **lần lượt từng video**, có khoảng nghỉ tối thiểu giữa hai lần đăng (cài đặt được).
- Khi lỗi: chụp màn hình và lưu nhật ký, thử lại tối đa N lần.
- Khi gặp captcha hoặc bước xác minh: **dừng lại và báo bạn tự xử lý**. Tool không vượt captcha.

### 5.3 Dựng video theo mẫu (bản cơ bản, chưa dùng AI)
- **Phân tích video mẫu** tự động: thời lượng, tỉ lệ khung hình, độ phân giải, fps, số cảnh, độ dài trung bình mỗi cảnh (nhịp cắt).
- Kết quả lưu thành **Mẫu phong cách**, dùng lại được và sửa tay được, gồm:
  - Khung hình: 9:16 hoặc 16:9, cắt giữa hoặc nền mờ
  - Nhịp cắt: độ dài mỗi đoạn, tổng thời lượng
  - Chữ tiêu đề: nội dung, font, cỡ chữ, màu, vị trí, thời điểm hiện
  - Phụ đề: kiểu chữ, vị trí
  - Hiệu ứng cơ bản: zoom nhẹ, chuyển cảnh mờ dần
- **Dựng video**: áp mẫu lên video gốc, chạy được cho cả 3 loại:
  - Video dài: cắt ra nhiều clip ngắn theo điểm chuyển cảnh và nhịp của mẫu
  - Nhiều cảnh quay thô: ghép lại theo nhịp mẫu
  - Video đã hoàn chỉnh: chỉ đổi khung hình, chèn chữ và phụ đề
- Bản cơ bản lấy phụ đề từ file `.srt` bạn đưa vào. Phụ đề tự động sẽ có ở giai đoạn AI.
- Có xem trước trước khi dựng, dựng ở chế độ nền và hiện tiến độ.

### 5.4 Hàng chờ, duyệt và lịch đăng
- Trang **Chờ duyệt**: xem video, sửa tiêu đề, mô tả, hashtag cho từng nền tảng, rồi bấm Duyệt hoặc Từ chối.
- Trang **Lịch đăng**: xem theo ngày hoặc tuần, kéo thả để đổi giờ.
- Một video đăng được lên nhiều tài khoản hoặc nền tảng cùng lúc, mỗi nơi một nội dung riêng.
- Nếu máy tắt đúng giờ đăng: khi mở lại, tool hỏi bạn có đăng bù hay không.

### 5.5 Lớp AI (chỉ dựng khung ở bản đầu)
- Có sẵn một giao diện chung cho mọi nhà cung cấp AI, sau này cắm vào mà không phải sửa phần khác:
  - **Ollama** (chạy trên máy, miễn phí; với GPU 4GB chỉ chạy được model nhỏ)
  - **Gemini API** (có gói miễn phí, hiểu được video trực tiếp)
  - **Claude API** (viết tiếng Việt tốt nhất)
- Bản đầu có trang Cài đặt AI để chọn nhà cung cấp và nhập địa chỉ hoặc key, nhưng chưa có tính năng AI nào chạy.

### 5.6 Giao diện
Các trang: **Tổng quan** · **Tài khoản** · **Dựng video** · **Mẫu phong cách** · **Chờ duyệt** · **Lịch đăng** · **Nhật ký** · **Cài đặt**

- Thu nhỏ xuống khay hệ thống và tự khởi động cùng Windows.
- Thông báo Windows khi đăng xong, khi lỗi hoặc khi cần bạn xử lý.
- Giao diện tiếng Việt.

## 6. Lưu trữ

Ổ C và D gần đầy (còn 5.2GB và 9.2GB), nên dữ liệu mặc định để ở **`E:\ToolAuto-data`** (đổi được trong Cài đặt):

```
E:\ToolAuto-data\
  profiles\     hồ sơ trình duyệt của từng tài khoản
  renders\      video đã dựng
  templates\    mẫu phong cách
  screenshots\  ảnh chụp khi lỗi
  logs\         nhật ký
  toolauto.db   cơ sở dữ liệu
```

Tool cảnh báo khi ổ đầy và có nút dọn video đã đăng xong.

## 7. Cấu trúc mã nguồn

```
D:\Tool Auto\
  app\
    main.py
    ui\           các trang giao diện
    core\         cấu hình, database, hàng chờ, lịch đăng, thông báo
    accounts\     quản lý tài khoản và hồ sơ trình duyệt
    uploaders\    base.py, youtube.py, tiktok.py, meta.py
      selectors\  vị trí nút bấm của từng nền tảng (file YAML)
    editor\       analyzer.py (phân tích mẫu), template.py, renderer.py (FFmpeg)
    ai\           giao diện chung + khung cho Ollama, Gemini, Claude
  docs\           hướng dẫn sử dụng
  tests\
  requirements.txt
  PLAN.md
```

## 8. Lộ trình

| Giai đoạn | Nội dung | Kết quả bạn kiểm tra được |
|---|---|---|
| **GĐ0 – Nền móng** | Khung app, các trang giao diện, database, cài đặt | Mở được app, chuyển qua lại giữa các trang |
| **GĐ1 – Đăng YouTube từ đầu đến cuối** | Thêm tài khoản, soạn bài, duyệt, lịch, đăng lên YouTube | Đăng thật một video lên kênh YouTube của bạn theo lịch |
| **GĐ2 – Thêm nền tảng** | TikTok, Facebook Fanpage, Instagram | Đăng một video lên cả 4 nền tảng |
| **GĐ3 – Dựng video theo mẫu** | Phân tích mẫu, mẫu phong cách, dựng video, xem trước | Đưa video mẫu và video gốc vào, nhận video thành phẩm |
| **GĐ4 – Hoàn thiện** | Khay hệ thống, khởi động cùng Windows, thông báo, đăng bù, đóng gói `.exe` | Cài và chạy như phần mềm bình thường |
| **GĐ5 – AI (sau)** | Phụ đề tự động (Whisper), viết tiêu đề, mô tả, hashtag, chọn đoạn hay, ra lệnh bằng chat | Làm khi bạn đã chọn hướng AI |

Hết mỗi giai đoạn mình sẽ báo để bạn chạy thử, rồi mới làm tiếp giai đoạn sau.

## 9. Rủi ro và giới hạn (cần biết trước)

- **Rủi ro tài khoản**: tự động thao tác trình duyệt vi phạm điều khoản của một số nền tảng. Các nền tảng có thể yêu cầu xác minh hoặc khóa tài khoản, đặc biệt khi có nhiều tài khoản. Nên **thử trên tài khoản phụ trước**.
- **Giao diện nền tảng thay đổi** thì bộ đăng sẽ hỏng và cần cập nhật selector. Đây là việc bảo trì định kỳ.
- **Đăng nhập Google** đôi khi chặn trình duyệt tự động. Khi đó bạn đăng nhập trong cửa sổ Chrome tool mở ra.
- **Captcha và xác minh**: tool dừng lại và báo bạn, không tự vượt.
- **Máy phải bật** thì mới đăng được. Riêng YouTube có thể hẹn giờ trên server của YouTube để giảm phụ thuộc vào máy.
- **Chưa có tính năng tải video từ kênh khác** và không có kỹ thuật né hệ thống nhận diện bản quyền.

## 10. Cần bạn chuẩn bị

1. Ít nhất một tài khoản thử nghiệm trên mỗi nền tảng, nên dùng tài khoản phụ.
2. Một Fanpage và một tài khoản Instagram để thử.
3. Một video mẫu và vài video gốc để thử phần dựng (GĐ3).
4. Xác nhận dùng ổ **E:** để lưu dữ liệu.
