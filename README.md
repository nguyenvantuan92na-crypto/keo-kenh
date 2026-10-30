# Tool kéo kênh YouTube

Tool tự động thực hiện quy trình dùng **kênh mạnh** để kéo view cho **kênh yếu**: ghim bình luận, màn hình kết thúc, thẻ, tính năng cộng tác, tùy chỉnh kênh. Mọi thao tác được ghi vào Excel (và Google Sheets nếu bật) với trạng thái ✅ DONE / ⚠️ CẦN KIỂM TRA / ❌ LỖI. Từ báo cáo này, tool gỡ lại được.


## Thư mục của tool và dữ liệu
```
Thư mục tool (giải nén ở đâu cũng được)
  Mo_Tool.bat     nhấp đúp để mở tool
  Cai_dat.bat     chạy 1 lần khi cài trên máy mới
  README.md       hướng dẫn này
  bieu_mau\       biểu mẫu điền thông tin kênh
  he_thong\       mã chạy tool – không cần mở

C:\Users\<tên máy>\KeoKenh_du_lieu\   DỮ LIỆU CỦA BẠN – cố định, không nằm trong thư mục tool
  kenh\ (file kênh) · profiles\ (đăng nhập) · logs\ · Excel kết quả / đối soát · *.db · cài đặt · sao_luu\
```
- **Cập nhật tool:** giải nén bản mới ở bất kỳ đâu rồi mở Mo_Tool.bat – kênh, đăng nhập, cài đặt giữ nguyên,
  không phải đặt lại gì.
- Lần đầu chạy bản này, tool tự chuyển dữ liệu từ thư mục tool cũ (du_lieu\ hoặc ngoài cùng) sang thư mục cố định;
  không thấy thì tự tìm bản tool cũ trong Downloads / Desktop / Documents và chép sang.
- **Sao lưu tự động:** mỗi ngày 1 bản (file kênh, cài đặt, Excel, lịch sử) trong `KeoKenh_du_lieu\sao_luu\`,
  giữ 14 ngày. Muốn khôi phục: giải nén bản sao lưu đè vào `KeoKenh_du_lieu\`.
- Nút **Thư mục dữ liệu** ở trang Kết quả mở thẳng thư mục này.
- Chuyển máy: chép cả thư mục `KeoKenh_du_lieu` sang cùng vị trí trên máy mới.

## Kéo nhiều kênh
- Mỗi kênh cần kéo là 1 bộ thông tin riêng, lưu thành 1 file trong thư mục `kenh\` (kenh_01.yaml, kenh_02.yaml...).
  Lần đầu mở bản này, thông tin cũ (config.yaml + videos_to_pull.txt) tự chuyển thành **kênh số 1**, giữ nguyên đăng nhập.
- Trang **Thông tin kênh** → thanh **KÊNH ĐANG CHỌN**: chọn kênh, **+ Thêm kênh**, **Nhân bản**, **↑ ↓** đổi thứ tự,
  **Xóa kênh**, ô **Bật khi chạy tất cả kênh**.
- Kênh mới: điền thông tin → **Lưu** → sang **Chạy tool** → đăng nhập kênh mạnh / kênh cần kéo (bước 1–2) **cho kênh đó**.
  Nếu kênh mới dùng **cùng kênh mạnh** với kênh đã có, tool dùng chung đăng nhập, không cần đăng nhập lại.
- **▶ Kéo kênh đang chọn**: chỉ chạy kênh đang chọn.
- **▶▶ Chạy tất cả kênh**: chạy LẦN LƯỢT các kênh đang bật theo thứ tự. Kênh chưa có video thì tool tự tìm video đang có view
  trước. Xong mỗi kênh tool đóng trình duyệt của kênh đó rồi mới sang kênh sau. 1 kênh lỗi không làm dừng các kênh khác.
- Mỗi tài khoản có hồ sơ đăng nhập + cổng điều khiển riêng nên các kênh không bao giờ lẫn phiên đăng nhập.

## Nhiều kênh mạnh kéo cho 1 kênh & gỡ chính xác
- Thông tin kênh → **Thêm kênh mạnh**: tạo thêm 1 bộ kéo cho đúng kênh cần kéo đang chọn, chỉ cần điền kênh mạnh mới.
  Chạy tất cả kênh → các kênh mạnh lần lượt kéo cho kênh đó.
- Ô "Video cần kéo view" nhận bao nhiêu link cũng được: video mới hoặc các video đang ít view.
- Nhật ký ghi: kênh mạnh (tên + ID), kênh cần kéo, video kênh mạnh đã dùng, mã các video đã gắn, file kênh.
- Kết quả → lọc theo kênh mạnh / kênh cần kéo / tìm kiếm → chọn dòng → **Gỡ các dòng đã chọn**.
  Tool đăng nhập đúng kênh mạnh của từng dòng, đối chiếu nội dung bình luận, số thẻ, số ô màn hình kết thúc
  với nhật ký trước khi xóa; khác nhau thì không xóa mà đánh dấu "Gỡ thủ công".

## File đối soát (doi_soat_keo_kenh.xlsx)
Tự tạo sau mỗi lần kéo / gỡ, hoặc bấm Kết quả → Xuất file đối soát. Gồm 5 sheet:
- Đối soát chi tiết: mỗi dòng = 1 vị trí đã gắn (bình luận ghim, màn hình kết thúc ô 1/2, thẻ 1–5 + mốc thời gian,
  cộng tác, hồ sơ/Trang chủ) trên 1 video kênh mạnh → link + tiêu đề video được kéo, trạng thái hiện tại, thời gian gỡ.
- Theo video được kéo: mỗi video kênh cần kéo đang được những video kênh mạnh nào trỏ tới.
- Theo video kênh mạnh: trên mỗi video kênh mạnh đang gắn những gì.
- Tổng hợp theo kênh: mỗi cặp kênh mạnh → kênh cần kéo.
- Cách đối soát.

## Thư mục biểu mẫu (bieu_mau)
- `1_BIEU_MAU_TRONG.txt`: biểu mẫu trống cho 1 bộ kênh (mở bằng Notepad). Copy ra file mới cho mỗi kênh.
- `2_VI_DU_DA_DIEN.txt`: ví dụ đã điền. `3_CACH_DIEN.txt`: quy tắc điền từng ô.
- Trang Thông tin kênh: **Nạp biểu mẫu** (tool tự điền đúng vào từng ô), **Xuất kênh ra biểu mẫu**,
  **Mở thư mục biểu mẫu**. Nạp xong kiểm tra lại rồi bấm Lưu thông tin.

## Bước 3 – Tùy chỉnh kênh mạnh (Hồ sơ · Thẻ Trang chủ · Bài đăng)
Điền ở trang **Thông tin kênh → thẻ "Tùy chỉnh kênh mạnh (bước 3)"**, bấm Lưu, rồi chạy **Bước 3** ở trang Chạy tool.
- **Hồ sơ → Đường liên kết**: tiêu đề + URL (dán link video cần kéo; để trống = link kênh cần kéo). Đã có link đó thì bỏ qua.
- **Video giới thiệu kênh cho người chưa đăng ký** và **Video nổi bật dành cho người đăng ký cũ**: dán link video.
  Tool dán link vào hộp chọn và CHỈ bấm vào kết quả có đúng mã video đó, rồi kiểm tra lại mục trên Thẻ Trang chủ
  đang hiện đúng video mới bấm Xuất bản. Video đang đúng sẵn thì giữ nguyên. Video cũ được ghi lại trong file đối soát.
- **Bài đăng có video**: mỗi dòng 1 link = 1 bài đăng (trang kênh → Bài đăng → Video → dán link → Đăng).
  Tool kiểm tra khung soạn đã đính kèm đúng video rồi mới bấm Đăng; video đã đăng bài trước đó thì bỏ qua.
- Tích/bỏ tích từng mục ở dòng "Bước 3 sẽ làm".

## Màn hình kết thúc & thẻ – số video
- Màn hình kết thúc 2 video cần **ít nhất 2 link khác nhau**; thẻ cần đủ số link theo "Số thẻ video".
  Thiếu link thì tool gắn được bao nhiêu gắn bấy nhiêu và báo ⚠️ CẦN KIỂM TRA, nói rõ thiếu mấy link.
- Mỗi thẻ được đặt đúng mốc (0:00, 5:00, 10:00...) bằng ô thời gian của CHÍNH thẻ vừa thêm, cuối cùng tool đọc lại
  toàn bộ mốc thẻ trước khi Lưu.

## Đã đúng sẵn → bỏ qua, báo ✅ hoàn thành
Trước khi làm mỗi bước, tool xem kênh/video ĐÃ có đúng nội dung bạn điền chưa:
- Màn hình kết thúc: đủ ô video và các video đang hiện đều là link trong danh sách video kênh cần kéo.
- Thẻ: đủ số thẻ, đúng mốc (0/5/10 phút…), video trong thẻ là link kênh cần kéo.
- Bình luận: bình luận đang ghim đúng nội dung bạn điền.
- Cộng tác: kênh cần kéo đã có trong mục Cộng tác.
- Hồ sơ: đã có đường liên kết bạn điền. Bài đăng: video đó đã có bài đăng.
Đúng sẵn → KHÔNG xóa, KHÔNG làm lại (kể cả khi tích "Thay thế cái cũ"), nhật ký ghi
"✅ DONE – Đã hoàn thành – đã đúng sẵn trên kênh: …" rồi chạy sang bước tiếp theo.
Nếu 1 bước báo lỗi giữa chừng, tool mở lại YouTube kiểm tra kết quả thật: đã đúng như yêu cầu thì ghi ✅ hoàn thành
(không báo lỗi); chưa đúng mới báo lỗi kèm ảnh chụp. Dòng "đã đúng sẵn" không bị gỡ khi bấm Gỡ.

## Module Phân tích video (bật / tắt ở thanh bên → MODULE)
Tìm 4–6 video cùng chủ đề với kênh mục tiêu trên Trang chủ YouTube, mở mỗi video 1 tab, đọc phụ đề / bản chép lời
của khoảng 6–10 phút bạn chọn, AI chấm điểm /100, phân loại Hay / Trung bình / Chưa hay kèm lý do, đề xuất
Like / Bỏ qua / Dislike (Dislike chỉ khi có căn cứ) và viết 3 bình luận khác nhau
(English, Tagalog, Ilocano, Bisaya, Tiếng Việt).
- Dùng trình duyệt + đăng nhập sẵn có của tool (chọn Kênh cần kéo hoặc Kênh mạnh). Video được dừng phát ngay.
- Tool KHÔNG tự Like / Dislike / bình luận: bạn chọn 1 dòng → "Xác nhận Like/Dislike"; bình luận bấm nút sao chép
  → "Mở video để bình luận" (tool mở ô bình luận) → bạn dán Ctrl+V và tự bấm Bình luận.
- AI: "Ollama – AI chạy trên máy" (mặc định, miễn phí, tự động). Bấm nút "Cài / kiểm tra Ollama" ngay trên trang:
  tool tự tải bộ cài từ ollama.com (bạn bấm Install), tự mở Ollama và tự tải model. Hoặc API Claude / OpenAI /
  Gemini (cần khóa, trả phí; khóa chỉ lưu trên máy bạn).
- Số video mỗi lượt: 1–10. "Chỉ chấm theo tiêu đề" (mặc định) không đọc lời thoại.
- START / PAUSE / RESUME / STOP; lịch sử lưu phan_tich.db (SQLite); xuất CSV / Excel; nhật ký logs/phan_tich.log.
- Chạy cùng lượt kéo: trang Chạy tool → thẻ Kéo kênh → tích "Phân tích video cùng chủ đề (AI)". Bấm "Kéo kênh
  đang chọn" hoặc "Chạy tất cả kênh": kéo xong kênh nào tool phân tích luôn cho kênh đó (kênh mục tiêu = kênh cần kéo
  của kênh đó, các cài đặt AI / số video / ngôn ngữ lấy ở trang Phân tích video), rồi mới sang kênh sau.
  Chỉ tích ô này (bỏ các bước kéo) = chỉ phân tích. Kết quả chờ bạn duyệt ở trang Phân tích video; Like / Dislike
  được làm bằng đúng tài khoản của kênh đã phân tích video đó.

## Cách kéo: cho kênh khác (2 kênh) hoặc cho chính kênh (1 kênh)
Chọn ở mục **CÁCH KÉO** đầu trang Thông tin kênh.
- **Kéo cho kênh khác**: kênh mạnh đẩy người xem sang 1 kênh khác (như trước). Đăng nhập cả 2 kênh.
- **Kéo cho chính kênh**: video đang nhiều view của kênh gắn màn hình kết thúc, thẻ, bình luận ghim trỏ sang
  video cần đẩy của CHÍNH kênh đó. Chỉ điền 1 kênh, đăng nhập 1 lần (bước 2 tự ẩn).
  - Video cần đẩy: dán link / video mới nhất của kênh / tự chọn video ít view nhất trong 20 video mới nhất.
  - Bình luận ghim để trống → tool tự soạn "Xem tiếp video mới của kênh: <link>".
  - Trang chủ (bước 3) để trống → tool tự chọn mỗi lần chạy: Video giới thiệu (người chưa ĐK) = video MỚI NHẤT;
    Video nổi bật (người ĐK cũ) = video NHIỀU VIEW NHẤT trong 7 ngày gần nhất (khác video giới thiệu).
    Ô nào bạn đã dán link thì tool dùng đúng link đó.
  - Tool không bao giờ gắn 1 video vào chính nó; tự bỏ Cộng tác và Kênh nổi bật (YouTube không cho / vô nghĩa).
  - Ghi nhật ký, xuất đối soát và gỡ chính xác như chế độ 2 kênh.

## Trả lời bình luận (trang Trả lời bình luận, hoặc ô "Trả lời bình luận" khi Kéo kênh)
- Tool mở lần lượt video của KÊNH MẠNH đang chọn, tải HẾT bình luận (sắp xếp Mới nhất).
- Bình luận KHEN → trả lời cảm ơn đúng ngôn ngữ người viết (English, Tagalog, Bisaya, Ilocano, Tiếng Việt,
  Español, 日本語, 한국어... 26 ngôn ngữ), thả tim, bấm thích – theo các ô bạn tích.
- Câu hỏi, góp ý, chê, quảng cáo / link, bình luận của chính kênh → KHÔNG trả lời. Lọc "Cần bạn xem" để tự trả lời.
- Không trả lời trùng: bình luận kênh đã trả lời (tool đọc phần phản hồi trên YouTube) hoặc tool đã trả lời
  (lưu trong binh_luan.db) đều bỏ qua.
- Gửi xong tool đọc lại đúng bình luận đó, thấy câu trả lời hiện ra mới ghi ✅.
- Lần đầu nên bấm "Xem trước (chỉ đọc, không gửi)" để xem tool xếp loại đúng chưa.
- "AI kiểm tra lại": dùng Ollama ở trang Phân tích video; chỉ trả lời khi cả tool và AI đều thấy là lời khen.
- Tool kiểm tra đúng kênh mạnh trước khi làm; tài khoản không có kênh đó → dừng, không trả lời gì.

## Gỡ khỏi kênh mạnh (trang Kết quả)
- **Gỡ theo hạng mục**: chọn kênh mạnh + tích hạng mục (Bình luận ghim, Màn hình kết thúc, Thẻ, Cộng tác,
  Hồ sơ – đường liên kết, Thẻ Trang chủ, Bài đăng video) → tool tự vào đúng chỗ trên kênh mạnh để gỡ.
- **Gỡ dòng đã chọn**: chọn dòng trong bảng (Ctrl/Shift) → gỡ đúng các dòng đó.
- **GỠ SẠCH TẤT CẢ**: gỡ mọi thứ tool đã kéo (kênh mạnh đang lọc, hoặc tất cả) – gõ XOA để xác nhận.
An toàn: chỉ gỡ đúng thứ tool đã gắn (đối chiếu nội dung bình luận, mã video, link, số thẻ / ô màn hình kết thúc);
thứ đang có khác với thứ tool gắn → không đụng, đánh dấu "Gỡ thủ công". Video giới thiệu / nổi bật ở Trang chủ:
nếu trước đó có video cũ thì tool TRẢ LẠI video cũ. Gỡ xong tool mở lại từng chỗ kiểm tra; còn sót → báo lỗi.
Kéo nhiều lần trên cùng video → chỉ gỡ 1 lần, mọi dòng cũ đều được đánh dấu đã gỡ.

## Ẩn trình duyệt
Tích **Ẩn trình duyệt khi chạy** ở trang Chạy tool. Tool vẫn dùng trình duyệt THẬT (Cốc Cốc/Chrome) như bình thường,
chỉ đặt cửa sổ ra ngoài màn hình (giữ kích thước 1600x1000 để YouTube Studio hiển thị đầy đủ) – không dùng chế độ
"headless" vì chế độ đó dễ bị Google nhận là bot và làm sai bố cục trang. Đăng nhập và Ghi thao tác mẫu luôn hiện cửa sổ.

## Cách dùng nhanh (có giao diện)
1. Nhấp đúp **Cai_dat.bat** (chỉ lần đầu).
2. Nhấp đúp **Mo_Tool.bat** để mở cửa sổ tool.
3. Tab **① Thông tin kênh**: điền thông tin, bấm **Lưu**.
4. Tab **② Chạy tool**: bấm lần lượt các bước 1 → 5. Khi tool cần bạn thao tác (đăng nhập...), nút **Tiếp tục** sẽ sáng lên.
5. Tab **③ Kết quả**: xem bảng xanh/vàng/đỏ, nhấp đúp dòng lỗi để xem ảnh chụp.

Phần dưới đây là cách dùng bằng dòng lệnh (không bắt buộc).

## 1. Cài đặt (làm 1 lần)
Cần Python 3.10+ và Google Chrome.
```
pip install -r requirements.txt
playwright install chromium
copy config.example.yaml config.yaml      (macOS/Linux: cp ...)
```
Mở `config.yaml` và điền 5 hạng mục của kênh yếu, ID kênh mạnh, nội dung bình luận ghim.

## 2. Đăng nhập (lưu phiên/cookie)
```
python main.py login strong
python main.py login weak
```
Một cửa sổ Chrome mở ra. Bạn đăng nhập và chọn đúng kênh, rồi nhấn Enter. Phiên được lưu trong thư mục `profiles/`, nên lần sau không cần đăng nhập lại.
Nếu muốn dùng cookie có sẵn: xuất cookie bằng extension *Cookie-Editor* (định dạng JSON), rồi điền đường dẫn vào `cookies_file`.

## 3. Quy trình chạy
| Lệnh | Việc làm |
|---|---|
| `python main.py setup-channel` | Thêm liên kết kênh yếu vào Hồ sơ, thêm vào thẻ Trang chủ: video nổi bật cho người đăng ký cũ, danh sách phát đơn, kênh nổi bật |
| `python main.py scan` | Đọc Số liệu thời gian thực, lọc video ≥ 20 view/60 phút, lưu vào `videos_to_pull.txt` |
| `python main.py pull` | Với từng video: ghim bình luận → màn hình kết thúc (2 video + DS phát + kênh) → 5 thẻ cách 5 phút → cộng tác |
| `python main.py pull --only cards endscreen` | Chỉ chạy lại một số bước (ví dụ để làm lại bước bị lỗi) |
| `python main.py revert` | Gỡ toàn bộ phần đã kéo dựa vào file báo cáo, đánh dấu "Đã gỡ" |
| `python main.py report` | Xem tổng kết |

Bạn có thể tự sửa `videos_to_pull.txt` (mỗi dòng 1 link) thay vì dùng `scan`.

## 4. Báo cáo
File `ket_qua_keo_kenh.xlsx`: mỗi dòng là 1 thao tác trên 1 video, có tô màu xanh/vàng/đỏ, kèm lỗi cụ thể và **ảnh chụp màn hình lúc lỗi** (trong `logs/screenshots/`), để bạn vào sửa đúng mục đó. Cột "Tình trạng gỡ" theo dõi phần nào đã gỡ.
Để đồng bộ Google Sheets: tạo Service Account trên Google Cloud, tải file khóa JSON, chia sẻ quyền sửa Sheet cho email của service account, rồi bật `google_sheet.enabled: true`.

## 5. Lần đầu dùng: hiệu chỉnh (quan trọng)
YouTube Studio đổi giao diện thường xuyên và có giao diện khác nhau giữa các tài khoản. Tool tìm nút **theo chữ hiển thị**, các chữ này nằm trong `labels.py`. Cách làm:
1. Chạy thử với `videos_to_pull.txt` chỉ có **1 video**, để `headless: false` để quan sát.
2. Bước nào báo ❌ "Không tìm thấy nút 'xxx'": mở ảnh chụp lỗi, xem chữ thật trên nút, rồi sửa hoặc thêm vào `labels.py`.
3. Ổn định rồi mới chạy hàng loạt.

Những phần tool sẽ báo ⚠️ để bạn làm tay:
- Sắp xếp vị trí các phần trên thẻ Trang chủ.
- Vị trí 4 góc của màn hình kết thúc (YouTube tự xếp; bạn chỉnh lại nếu muốn).
- Gỡ phần Hồ sơ / Trang chủ / Cộng tác.

## 6. Lưu ý
- Đăng nhập bằng cookie và thao tác hàng loạt có thể khiến Google yêu cầu xác minh lại hoặc tạm khóa phiên. Tool đã có nghỉ ngẫu nhiên giữa các bước (`delay_range_sec`); không nên giảm quá thấp.
- `clear_existing: true` sẽ **xóa màn hình kết thúc / thẻ cũ** của video trước khi gắn mới, và lệnh `revert` sẽ xóa sạch hai phần này.
- Việc tự động hóa giao diện có thể không phù hợp Điều khoản dịch vụ của YouTube; bạn tự cân nhắc khi sử dụng.
