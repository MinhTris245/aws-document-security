from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs"


def run(text, bold=False, italic=False, size=None, color=None, font="Arial"):
    props = [f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}"/>']
    if bold:
        props.append("<w:b/>")
    if italic:
        props.append("<w:i/>")
    if size:
        props.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    if color:
        props.append(f'<w:color w:val="{color}"/>')
    safe = escape(str(text))
    return f'<w:r><w:rPr>{"".join(props)}</w:rPr><w:t xml:space="preserve">{safe}</w:t></w:r>'


def para(text="", style=None, align=None, before=0, after=120, line=276, bold=False, italic=False, size=None, color=None, keep=False):
    ppr = []
    if style:
        ppr.append(f'<w:pStyle w:val="{style}"/>')
    if align:
        ppr.append(f'<w:jc w:val="{align}"/>')
    ppr.append(f'<w:spacing w:before="{before}" w:after="{after}" w:line="{line}" w:lineRule="auto"/>')
    if keep:
        ppr.append("<w:keepNext/>")
    return f'<w:p><w:pPr>{"".join(ppr)}</w:pPr>{run(text, bold, italic, size, color)}</w:p>'


def bullet(text, level=0):
    left = 720 + level * 360
    return (
        f'<w:p><w:pPr><w:spacing w:after="70"/><w:ind w:left="{left}" w:hanging="300"/>'
        f'</w:pPr>{run("•", bold=True)}{run("  " + text)}</w:p>'
    )


def code(text):
    lines = str(text).splitlines() or [""]
    result = []
    for line in lines:
        result.append(
            '<w:p><w:pPr><w:shd w:val="clear" w:color="auto" w:fill="F3F4F6"/>'
            '<w:spacing w:after="0"/><w:ind w:left="240" w:right="240"/></w:pPr>'
            + run(line, size=18, font="Consolas") + '</w:p>'
        )
    result.append(para("", after=70))
    return "".join(result)


def page_break():
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def table(headers, rows, widths=None):
    cols = len(headers)
    widths = widths or [int(9000 / cols)] * cols
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)

    def cell(value, width, header=False):
        fill = '<w:shd w:val="clear" w:color="auto" w:fill="1F4E78"/>' if header else ""
        color = "FFFFFF" if header else None
        return (
            f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{fill}'
            '<w:tcMar><w:top w:w="80" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
            '<w:bottom w:w="80" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tcMar></w:tcPr>'
            + para(value, after=0, bold=header, color=color) + '</w:tc>'
        )

    trs = ['<w:tr>' + "".join(cell(v, widths[i], True) for i, v in enumerate(headers)) + '</w:tr>']
    for row in rows:
        trs.append('<w:tr>' + "".join(cell(row[i], widths[i]) for i in range(cols)) + '</w:tr>')
    return (
        '<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/>'
        '<w:tblBorders><w:top w:val="single" w:sz="4" w:color="B7C9DB"/>'
        '<w:left w:val="single" w:sz="4" w:color="B7C9DB"/><w:bottom w:val="single" w:sz="4" w:color="B7C9DB"/>'
        '<w:right w:val="single" w:sz="4" w:color="B7C9DB"/><w:insideH w:val="single" w:sz="4" w:color="D9E2F3"/>'
        '<w:insideV w:val="single" w:sz="4" w:color="D9E2F3"/></w:tblBorders></w:tblPr>'
        f'<w:tblGrid>{grid}</w:tblGrid>{"".join(trs)}</w:tbl>' + para("")
    )


def heading(text, level=1):
    return para(text, style=f"Heading{level}", keep=True)


def cover(title, subtitle):
    return "".join([
        para("AWS DOCUMENT MANAGEMENT & AUTOMATED SECURITY RESPONSE", align="center", before=900, after=380, bold=True, size=24, color="4472C4"),
        para(title, align="center", before=300, after=300, bold=True, size=44, color="1F4E78"),
        para(subtitle, align="center", after=900, italic=True, size=25, color="595959"),
        para("Nền tảng: AWS • React • Flask • Grafana", align="center", after=180, size=22),
        para("Khu vực triển khai: Asia Pacific (Singapore) – ap-southeast-1", align="center", after=180, size=22),
        para("Ngày hoàn thiện tài liệu: 14/07/2026", align="center", before=1200, size=21, color="666666"),
        page_break(),
    ])


STYLES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr></w:rPrDefault></w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="300" w:after="140"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:color w:val="1F4E78"/><w:sz w:val="32"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="220" w:after="100"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:color w:val="2F5597"/><w:sz w:val="27"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="180" w:after="80"/><w:outlineLvl w:val="2"/></w:pPr><w:rPr><w:b/><w:color w:val="4472C4"/><w:sz w:val="24"/></w:rPr></w:style>
</w:styles>'''


def make_docx(path: Path, body: str, subject: str):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    document = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<w:body>{body}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080" w:header="500" w:footer="500"/><w:footerReference w:type="default" r:id="rId3"/></w:sectPr></w:body></w:document>'''
    footer = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:t>Trang </w:t></w:r><w:fldSimple w:instr="PAGE"><w:r><w:t>1</w:t></w:r></w:fldSimple></w:p></w:ftr>'''
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/><Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>'''
    doc_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/></Relationships>'''
    core = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>{escape(subject)}</dc:title><dc:creator>Nhóm dự án AWS</dc:creator><dc:subject>{escape(subject)}</dc:subject><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>'''
    app = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Microsoft Office Word</Application><AppVersion>16.0000</AppVersion></Properties>'''
    settings = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:zoom w:percent="100"/><w:defaultTabStop w:val="720"/><w:characterSpacingControl w:val="doNotCompress"/></w:settings>'''
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/settings.xml", settings)
        z.writestr("word/footer1.xml", footer)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)


def report_body():
    b = [cover("BÁO CÁO TỔNG THỂ DỰ ÁN", "Hệ thống quản lý tài liệu và phản ứng sự cố bảo mật tự động trên AWS")]
    b += [heading("MỤC LỤC NỘI DUNG", 1)]
    for item in ["1. Tóm tắt dự án", "2. Mục tiêu và phạm vi", "3. Kiến trúc tổng thể", "4. Thành phần phần mềm", "5. Các dịch vụ AWS", "6. Luồng nghiệp vụ", "7. API và dữ liệu", "8. An toàn thông tin", "9. Giám sát bằng Grafana", "10. Kiểm thử và kết quả", "11. Hạn chế và định hướng", "12. Kết luận"]:
        b.append(bullet(item))
    b += [page_break(), heading("1. TÓM TẮT DỰ ÁN", 1)]
    b.append(para("Dự án xây dựng một ứng dụng web quản lý tài liệu riêng tư kết hợp cơ chế phát hiện và phản ứng sự cố bảo mật tự động trên AWS. Người dùng đăng nhập, tải tài liệu lên S3, xem danh sách và nhận liên kết tải có thời hạn; metadata được lưu trong DynamoDB. GuardDuty và Security Hub cung cấp nguồn phát hiện, EventBridge chuyển sự kiện đến Lambda, Lambda ghi incident vào DynamoDB và gửi cảnh báo qua SNS. CloudWatch thu thập metric/log, còn Grafana cung cấp ba dashboard dành cho quản trị viên."))
    b += [heading("2. MỤC TIÊU VÀ PHẠM VI", 1)]
    for x in ["Quản lý upload, danh sách, download và xóa tài liệu theo vai trò.", "Lưu file trong bucket S3 private; chỉ phát hành presigned URL có thời hạn.", "Lưu metadata tài liệu và incident bảo mật trong DynamoDB.", "Tự động tiếp nhận GuardDuty finding qua EventBridge và Lambda.", "Gửi cảnh báo qua SNS; hỗ trợ quản trị trạng thái incident.", "Giám sát hạ tầng, dịch vụ AWS và log bằng CloudWatch/Grafana.", "Truy cập máy chủ bằng Systems Manager Session Manager thay vì mở SSH công khai."]:
        b.append(bullet(x))
    b += [heading("3. KIẾN TRÚC TỔNG THỂ", 1), para("Kiến trúc được chia thành lớp trình bày, API nghiệp vụ, lưu trữ, bảo mật tự động và quan sát hệ thống.")]
    b.append(table(["Lớp", "Thành phần", "Vai trò"], [
        ["Trình bày", "React 19, Vite 8, Bootstrap", "Giao diện đăng nhập, dashboard tài liệu, upload và incident."],
        ["API", "Flask 3.1, Gunicorn", "REST API, xác thực JWT, phân quyền user/admin."],
        ["Reverse proxy", "Nginx", "Phục vụ React, chuyển /api đến Flask, ghi access/error log."],
        ["Dữ liệu", "S3, DynamoDB", "Lưu file private, metadata Documents và SecurityIncidents."],
        ["Bảo mật", "GuardDuty, Security Hub, EventBridge, Lambda, SNS", "Phát hiện, định tuyến, xử lý, lưu và cảnh báo sự cố."],
        ["Quan sát", "CloudWatch, Grafana", "Metric, log, dashboard hạ tầng/dịch vụ/bảo mật."],
        ["Quản trị", "Systems Manager", "Kết nối EC2 và port-forward Grafana an toàn."],
    ], [1400, 2800, 4800]))
    b += [heading("3.1 Luồng kiến trúc", 2)]
    b.append(code("Người dùng → Nginx → React / Flask API\nFlask → S3 (file) + DynamoDB Documents (metadata)\nGuardDuty → Security Hub/EventBridge → Lambda SecurityIncidentResponse\nLambda → DynamoDB SecurityIncidents + SNS + CloudWatch Logs\nCloudWatch Metrics/Logs → Grafana dashboards"))
    b += [heading("4. THÀNH PHẦN PHẦN MỀM", 1), heading("4.1 Frontend", 2)]
    for x in ["Login và lưu JWT/role trong localStorage.", "Dashboard tổng hợp tài liệu, dung lượng, incident rủi ro cao và health AWS.", "Upload tối đa 20 MB; cho phép PDF, Office, ảnh và TXT.", "Tìm kiếm, lọc loại file, download qua presigned URL; admin được xóa.", "Trang incident tự refresh mỗi 30 giây, lọc severity/status/type và cập nhật trạng thái cho admin."]:
        b.append(bullet(x))
    b += [heading("4.2 Backend", 2)]
    b.append(table(["Nhóm", "Nội dung"], [
        ["Framework", "Flask, Flask-CORS, Gunicorn"], ["Xác thực", "PyJWT HS256; token hết hạn sau 8 giờ"], ["AWS SDK", "boto3"], ["Blueprint", "auth, documents, incidents, health"], ["Bảo vệ API", "require_auth và require_role('admin')"],
    ], [2600, 6400]))
    b += [heading("5. CÁC DỊCH VỤ AWS", 1)]
    b.append(table(["Dịch vụ/Tài nguyên", "Cấu hình hiện tại", "Chức năng"], [
        ["EC2", "i-0f86ac8ae3872226e", "Host Nginx, Flask, Grafana và CloudWatch Agent."],
        ["S3", "aws-s3-duanthuctap", "Bucket private lưu tài liệu."],
        ["DynamoDB", "Documents", "Metadata tài liệu."],
        ["DynamoDB", "SecurityIncidents", "Incident từ Lambda."],
        ["Lambda", "SecurityIncidentResponse", "Xử lý finding và phát cảnh báo."],
        ["EventBridge", "GuardDutyToSecurityIncident", "Định tuyến GuardDuty finding."],
        ["SNS", "SecurityAlerts", "Gửi thông báo bảo mật."],
        ["Region", "ap-southeast-1", "Khu vực Singapore."],
    ], [2400, 3100, 3500]))
    b += [heading("6. LUỒNG NGHIỆP VỤ", 1), heading("6.1 Quản lý tài liệu", 2)]
    for x in ["Người dùng đăng nhập và nhận JWT.", "Frontend gửi multipart/form-data đến POST /api/documents/upload.", "Backend kiểm tra token, extension và kích thước ≤ 20 MB.", "File được đổi tên bằng UUID rồi upload lên S3.", "Metadata được ghi vào bảng Documents.", "Download sử dụng presigned URL hiệu lực mặc định 3.600 giây.", "Xóa tài liệu yêu cầu role admin và xóa cả S3 object lẫn metadata."]:
        b.append(bullet(x))
    b += [heading("6.2 Phản ứng sự cố", 2)]
    for x in ["GuardDuty phát hiện hoặc sinh sample finding.", "EventBridge rule nhận sự kiện và gọi SecurityIncidentResponse.", "Lambda phân tích finding, ghi CloudWatch Logs và lưu SecurityIncidents.", "SNS SecurityAlerts gửi thông báo đến subscription đã xác nhận.", "Trang web và Grafana hiển thị incident/metric/log để điều tra."]:
        b.append(bullet(x))
    b += [heading("7. API VÀ DỮ LIỆU", 1)]
    b.append(table(["Method", "Endpoint", "Quyền", "Mục đích"], [
        ["POST", "/api/login", "Public", "Đăng nhập, nhận JWT."], ["GET", "/api/verify", "Authenticated", "Kiểm tra token."], ["GET", "/api/health", "Public", "Health S3 và DynamoDB."], ["GET", "/api/documents", "Authenticated", "Danh sách tài liệu."], ["POST", "/api/documents/upload", "Authenticated", "Upload file."], ["GET", "/api/documents/download/{id}", "Authenticated", "Tạo presigned URL."], ["DELETE", "/api/documents/{id}", "Admin", "Xóa file và metadata."], ["GET", "/api/incidents", "Authenticated", "Danh sách/lọc incident."], ["GET", "/api/incidents/{id}", "Authenticated", "Chi tiết incident."], ["PATCH", "/api/incidents/{id}/status", "Admin", "Đổi OPEN/INVESTIGATING/RESOLVED."],
    ], [1000, 3300, 1700, 3000]))
    b += [heading("8. AN TOÀN THÔNG TIN", 1)]
    for x in ["S3 private; không đưa AWS key vào frontend.", "EC2 sử dụng IAM role và credential tạm thời.", "JWT bảo vệ API; thao tác nhạy cảm yêu cầu admin.", "Tên file được chuẩn hóa, whitelist extension và giới hạn 20 MB.", "Security Group chỉ nên mở HTTP/HTTPS; quản trị EC2 qua SSM.", "Grafana chỉ truy cập qua SSM port forwarding localhost, không công khai port 3000.", "CloudWatch/Grafana dùng quyền read-only; CloudWatch Agent chỉ có quyền gửi telemetry."]:
        b.append(bullet(x))
    b.append(para("Lưu ý: tài khoản admin/user đang hard-code phục vụ demo. Mật khẩu demo và JWT lưu ở localStorage không phù hợp production; nên chuyển sang Cognito/IdP, HTTPS, secret manager và cookie HttpOnly.", bold=True, color="C00000"))
    b += [heading("9. GIÁM SÁT BẰNG GRAFANA", 1)]
    b.append(table(["Dashboard", "Nội dung chính"], [
        ["Document App - EC2 Monitoring", "CPU, Network In/Out, Status Check."],
        ["Document App - AWS Services Monitoring", "Lambda, DynamoDB, S3, SNS và EventBridge."],
        ["Document App - Security Logs Monitoring", "HTTP requests, 4xx/5xx, Lambda logs, Nginx access/error, system logs."],
    ], [3600, 5400]))
    b.append(para("Các dashboard JSON được lưu trong thư mục grafana/. AWS Services có 14 panel; Security Logs có 8 panel. Tần suất refresh mặc định là 1 phút. S3 storage metrics cập nhật theo ngày nên có thể tạm thời không có dữ liệu."))
    b += [heading("10. KIỂM THỬ VÀ KẾT QUẢ", 1)]
    b.append(table(["Hạng mục", "Kết quả quan sát"], [
        ["EC2", "CPU thấp, StatusCheckFailed = 0."], ["Lambda", "3 invocations, 0 errors, 0 throttles; duration khoảng 510–535 ms."], ["DynamoDB", "Có read/write metric; SystemErrors = 0."], ["SNS", "5 notification delivered; 0 failure."], ["EventBridge", "Có invocation; FailedInvocations = 0."], ["Security logs", "136 HTTP request, 9 phản hồi 4xx, không ghi nhận 5xx trong khoảng quan sát."], ["Nginx", "Access log có dữ liệu, error log không có lỗi trong khoảng quan sát."],
    ], [3000, 6000]))
    b += [heading("11. HẠN CHẾ VÀ ĐỊNH HƯỚNG", 1)]
    for x in ["Thay user hard-code bằng Amazon Cognito hoặc cơ sở dữ liệu người dùng có hash mật khẩu.", "Bật HTTPS bằng domain và TLS; thêm CSRF/rate limiting nếu chuyển sang cookie.", "Dùng DynamoDB Query + index và pagination thay cho Scan khi dữ liệu lớn.", "Bổ sung antivirus/malware scanning cho file upload.", "Triển khai IaC bằng Terraform/CloudFormation và CI/CD.", "Thiết lập Grafana/CloudWatch alarms gửi SNS khi 5xx, Lambda error hoặc CPU vượt ngưỡng.", "Áp dụng retention cho CloudWatch Logs và lifecycle cho S3."]:
        b.append(bullet(x))
    b += [heading("12. KẾT LUẬN", 1), para("Dự án đã hoàn thiện chuỗi nghiệp vụ từ quản lý tài liệu đến phát hiện, phản ứng và quan sát sự cố trên AWS. Kết quả kiểm thử cho thấy website, S3, DynamoDB, Lambda, SNS, EventBridge, CloudWatch và ba dashboard Grafana phối hợp đúng. Kiến trúc phù hợp cho bài trình bày/demo và là nền tảng tốt để nâng cấp thành môi trường production sau khi hoàn thiện quản lý danh tính, HTTPS, IaC và cảnh báo chủ động.")]
    return "".join(b)


def guide_body():
    b = [cover("HƯỚNG DẪN CHẠY DỰ ÁN", "Dành cho người mới clone repository")]
    b += [heading("1. TỔNG QUAN", 1), para("Tài liệu hướng dẫn hai chế độ: chạy local để phát triển và triển khai trên EC2. Frontend gọi /api; Vite proxy sang Flask khi chạy local, còn Nginx proxy sang Gunicorn khi chạy production.")]
    b += [heading("2. YÊU CẦU", 1)]
    b.append(table(["Công cụ", "Phiên bản khuyến nghị", "Kiểm tra"], [
        ["Git", "2.x", "git --version"], ["Python", "3.10+", "python --version"], ["Node.js", "18+ (theo package hiện tại nên dùng bản tương thích Vite 8)", "node --version"], ["npm", "9+", "npm --version"], ["AWS CLI", "2.x", "aws --version"],
    ], [2200, 4300, 2500]))
    b.append(para("Bạn cần AWS credentials hoặc IAM role có quyền tối thiểu với bucket S3 và hai bảng DynamoDB. Không commit .env, access key hoặc JWT secret."))
    b += [heading("3. CLONE VÀ CẤU TRÚC", 1)]
    b.append(code("git clone <repository-url>\ncd aws"))
    b.append(table(["Thư mục", "Nội dung"], [["backend/", "Flask API và AWS services."], ["frontend/", "React/Vite UI."], ["grafana/", "Dashboard JSON để import."], ["docs/", "Báo cáo và hướng dẫn Word."]], [2500, 6500]))
    b += [heading("4. CẤU HÌNH AWS", 1), heading("4.1 Tài nguyên cần có", 2)]
    for x in ["S3 bucket private.", "DynamoDB table Documents với partition key document_id (String).", "DynamoDB table SecurityIncidents với partition key incident_id (String).", "IAM user/role cho phép đọc/ghi đúng các tài nguyên trên."]:
        b.append(bullet(x))
    b += [heading("4.2 Tạo backend/.env", 2), para("Sao chép file mẫu và thay placeholder:")]
    b.append(code("# Windows PowerShell\nCopy-Item backend\\.env.example backend\\.env\n\n# Linux/macOS\ncp backend/.env.example backend/.env"))
    b.append(code("AWS_REGION=ap-southeast-1\nS3_BUCKET_NAME=<ten-bucket-cua-ban>\nDYNAMODB_DOCUMENTS_TABLE=Documents\nDYNAMODB_INCIDENTS_TABLE=SecurityIncidents\nJWT_SECRET_KEY=<chuoi-ngau-nhien-it-nhat-32-ky-tu>\nFLASK_DEBUG=1"))
    b.append(para("Tạo JWT secret nhanh: python -c \"import secrets; print(secrets.token_hex(32))\". Tuyệt đối không gửi hoặc commit giá trị này."))
    b += [heading("4.3 Cấu hình credential khi chạy local", 2)]
    b.append(code("aws configure\naws sts get-caller-identity"))
    b.append(para("Trên EC2 nên gắn IAM instance profile thay vì lưu access key trong .env."))
    b += [heading("5. CHẠY BACKEND LOCAL", 1)]
    b.append(code("cd backend\npython -m venv .venv\n\n# Windows PowerShell\n.\\.venv\\Scripts\\Activate.ps1\n\n# Linux/macOS\nsource .venv/bin/activate\n\npip install -r requirements.txt\npython app.py"))
    b.append(para("Backend chạy tại http://127.0.0.1:5000. Giữ terminal này mở."))
    b += [heading("6. CHẠY FRONTEND LOCAL", 1)]
    b.append(code("cd frontend\nnpm ci\nnpm run dev"))
    b.append(para("Mở URL Vite hiển thị trong terminal, thường là http://localhost:5173. Vite đã proxy /api đến 127.0.0.1:5000 nên không cần VITE_API_URL."))
    b += [heading("7. ĐĂNG NHẬP VÀ KIỂM TRA", 1)]
    b.append(table(["Tài khoản demo", "Mật khẩu", "Vai trò"], [["admin", "admin123", "Xem và xóa tài liệu, cập nhật incident."], ["user1", "password1", "Xem, upload và download."]], [2500, 2500, 4000]))
    b.append(para("Chỉ sử dụng các tài khoản này cho demo/local. Không sử dụng trong production."))
    b.append(code("# Health check\ncurl http://127.0.0.1:5000/api/health"))
    b.append(para("Kết quả tốt có status=ok và s3/documents_table/incidents_table đều ok=true."))
    b += [heading("8. KIỂM THỬ CHỨC NĂNG", 1)]
    for x in ["Đăng nhập admin hoặc user1.", "Upload file hợp lệ ≤ 20 MB.", "Kiểm tra object xuất hiện trong S3 và metadata trong Documents.", "Download file từ dashboard.", "Đăng nhập admin để thử xóa; xác nhận cả S3 và DynamoDB cùng được xóa.", "Mở Incidents và thử lọc severity/status/type."]:
        b.append(bullet(x))
    b += [heading("9. BUILD FRONTEND", 1)]
    b.append(code("cd frontend\nnpm run lint\nnpm run build\nnpm run preview"))
    b.append(para("Build production nằm tại frontend/dist/."))
    b += [heading("10. TRIỂN KHAI TRÊN EC2", 1), heading("10.1 Cài gói", 2)]
    b.append(code("sudo apt update\nsudo apt install -y python3 python3-venv python3-pip nginx nodejs npm\ngit clone <repository-url> /app\ncd /app"))
    b += [heading("10.2 Backend với Gunicorn", 2)]
    b.append(code("cd /app/backend\npython3 -m venv venv\nsource venv/bin/activate\npip install -r requirements.txt\n# Tạo .env như mục 4\ngunicorn -w 4 -b 127.0.0.1:5000 app:app"))
    b.append(para("Khuyến nghị tạo systemd service để Gunicorn tự khởi động lại. WorkingDirectory phải trỏ đến /app/backend và EnvironmentFile đến /app/backend/.env."))
    b += [heading("10.3 Frontend và Nginx", 2)]
    b.append(code("cd /app/frontend\nnpm ci\nnpm run build\nsudo cp -r dist/* /var/www/html/"))
    b.append(code("server {\n    listen 80 default_server;\n    server_name _;\n    root /var/www/html;\n    index index.html;\n\n    location /api/ {\n        proxy_pass http://127.0.0.1:5000;\n        proxy_set_header Host $host;\n        proxy_set_header X-Real-IP $remote_addr;\n        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n        proxy_set_header X-Forwarded-Proto $scheme;\n        client_max_body_size 20M;\n    }\n\n    location / {\n        try_files $uri $uri/ /index.html;\n    }\n}"))
    b.append(code("sudo nginx -t\nsudo systemctl reload nginx\nsudo systemctl enable nginx"))
    b += [heading("11. GRAFANA QUA SSM PORT FORWARDING", 1)]
    b.append(para("Grafana nên lắng nghe 127.0.0.1:3000 và không mở public port 3000. Trên máy cá nhân chạy:"))
    b.append(code("aws ssm start-session --target <instance-id> --document-name AWS-StartPortForwardingSession --parameters \"portNumber=3000,localPortNumber=3000\" --region ap-southeast-1"))
    b.append(para("Giữ terminal mở và truy cập http://localhost:3000."))
    b += [heading("12. IMPORT DASHBOARD GRAFANA", 1)]
    for x in ["Grafana → Dashboards → New → Import.", "Upload grafana/aws-services-monitoring.json; chọn data source cloudwatch.", "Upload grafana/security-logs-monitoring.json; chọn data source cloudwatch.", "Dashboard EC2 có thể tạo thủ công hoặc export từ môi trường đã cấu hình.", "Chọn Last 24 hours/Last 7 days và Refresh 1m."]:
        b.append(bullet(x))
    b += [heading("13. DEMO LUỒNG BẢO MẬT", 1)]
    for x in ["Tạo GuardDuty sample finding.", "Xác nhận EventBridge gọi Lambda SecurityIncidentResponse.", "Kiểm tra SecurityIncidents có item mới.", "Kiểm tra SNS subscription nhận cảnh báo.", "Mở AWS Services Monitoring xem invocation/error.", "Mở Security Logs Monitoring xem Lambda và Nginx logs."]:
        b.append(bullet(x))
    b += [heading("14. XỬ LÝ LỖI THƯỜNG GẶP", 1)]
    b.append(table(["Hiện tượng", "Kiểm tra/cách xử lý"], [
        ["Frontend không gọi API", "Backend có chạy port 5000; Vite proxy/Nginx location /api đúng."],
        ["Health degraded", "Kiểm tra .env, region, tên bucket/table và IAM permission."],
        ["AccessDenied", "Đọc Action trong lỗi và cấp đúng quyền tối thiểu cho user/role."],
        ["Upload 413", "Đặt client_max_body_size 20M trong Nginx."],
        ["Grafana No data", "Chọn đúng region/dimension, mở rộng time range, tạo traffic/sample finding."],
        ["S3 size/object trống", "Storage metrics S3 cập nhật theo ngày; thử Last 7 days."],
        ["localhost:3000 không mở", "Giữ phiên SSM port forwarding hoạt động; kiểm tra grafana-server."],
        ["React route trả 404", "Nginx location / phải có try_files ... /index.html."],
    ], [2800, 6200]))
    b += [heading("15. CHECKLIST BÀN GIAO", 1)]
    for x in ["Không có secret trong Git.", "Backend và frontend khởi động thành công.", "Health API trả ok.", "Upload/download và phân quyền admin hoạt động.", "GuardDuty → EventBridge → Lambda → DynamoDB/SNS hoạt động.", "CloudWatch có metric/log.", "Ba dashboard Grafana hiển thị đúng.", "Nginx và Gunicorn được enable/restart theo cơ chế hệ thống."]:
        b.append(bullet("☐ " + x))
    return "".join(b)


def main():
    make_docx(OUT / "Bao_cao_tong_the_du_an_AWS.docx", report_body(), "Báo cáo tổng thể dự án AWS")
    make_docx(OUT / "Huong_dan_chay_du_an_sau_khi_clone.docx", guide_body(), "Hướng dẫn chạy dự án sau khi clone")
    print(OUT / "Bao_cao_tong_the_du_an_AWS.docx")
    print(OUT / "Huong_dan_chay_du_an_sau_khi_clone.docx")


if __name__ == "__main__":
    main()
