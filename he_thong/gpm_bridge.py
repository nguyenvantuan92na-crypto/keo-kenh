"""
CẦU NỐI GPM-LOGIN – chạy trên MÁY CÓ GPM-LOGIN, để tool Kéo Kênh ở MÁY KHÁC dùng được các profile GPM của máy này.

Vì sao cần: GPM-Login và trình duyệt GPM mở ra chỉ nhận lệnh từ CHÍNH máy đó (127.0.0.1). Cầu nối nhận lệnh từ
máy khác (phải đúng MÃ KẾT NỐI), chuyển cho GPM, và mở 1 đường chuyển tiếp tới trình duyệt vừa mở – chỉ cho đúng
máy vừa gửi lệnh (đúng mã) được vào.

Chạy: nhấp đúp Cau_noi_GPM.bat (hoặc: python he_thong\\gpm_bridge.py). Cửa sổ hiện địa chỉ + mã kết nối để điền
vào tool ở máy kia. Đóng cửa sổ = tắt cầu nối.
An toàn: chỉ nên dùng trong cùng mạng nội bộ (cùng wifi / LAN) hoặc qua mạng riêng ảo như Tailscale / ZeroTier.
KHÔNG mở cổng ra Internet trên modem.
"""
import json
import os
import re
import secrets
import socket
import sys
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths   # noqa: E402

PORT = 19996
CONF = os.path.join(paths.DATA, "cau_noi_gpm.json")
LOCAL_GPM = "http://127.0.0.1:19995"


def _conf():
    try:
        with open(CONF, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    if not d.get("key"):
        d["key"] = secrets.token_hex(4).upper()          # 8 ký tự, vd 3FA9C21B
    d.setdefault("port", PORT)
    d.setdefault("gpm", LOCAL_GPM)
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    with open(CONF, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    return d


def lan_ips():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass
    return sorted(ips)


# ------------------------------------------------------------------ chuyển tiếp tới trình duyệt GPM
class Forward:
    """Nghe ở cổng `lport` (mọi card mạng), chuyển nguyên vẹn tới 127.0.0.1:`dport`. Chỉ nhận máy trong `allow`."""

    def __init__(self, dport, allow):
        self.dport, self.allow = dport, set(allow)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        for p in (dport + 10000, 0):
            try:
                self.sock.bind(("0.0.0.0", p if p < 65536 else 0))
                break
            except OSError:
                continue
        self.lport = self.sock.getsockname()[1]
        self.sock.listen(64)
        self.alive = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.alive:
            try:
                c, addr = self.sock.accept()
            except OSError:
                break
            if addr[0] not in self.allow:
                c.close()
                continue
            try:
                u = socket.create_connection(("127.0.0.1", self.dport), timeout=10)
                u.settimeout(None)
            except OSError:
                c.close()
                continue
            for a, b in ((c, u), (u, c)):
                threading.Thread(target=self._pipe, args=(a, b), daemon=True).start()

    @staticmethod
    def _pipe(a, b):
        try:
            while True:
                d = a.recv(65536)
                if not d:
                    break
                b.sendall(d)
        except OSError:
            pass
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def stop(self):
        self.alive = False
        try:
            self.sock.close()
        except OSError:
            pass


FWD = {}   # mã profile -> Forward


def _local(path):
    req = urllib.request.Request(CFG["gpm"].rstrip("/") + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, r.read()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(u.query)
        key = self.headers.get("X-Keo-Key") or (q.get("key") or [""])[0]
        client = self.client_address[0]
        if not secrets.compare_digest(str(key).upper(), CFG["key"].upper()):
            print(f"  ✖ từ chối {client}: sai mã kết nối", flush=True)
            return self._send(403, {"success": False, "message": "Sai mã kết nối cầu nối GPM"})
        if u.path == "/keo/ping":
            return self._send(200, {"success": True, "data": {"bridge": True}, "message": "OK"})
        q.pop("key", None)
        path = u.path + ("?" + urllib.parse.urlencode(q, doseq=True) if q else "")
        try:
            st, body = _local(path)
        except Exception as e:
            return self._send(502, {"success": False, "message": f"Cầu nối không gọi được GPM-Login trên máy này: {e}"})
        m = re.match(r"^/api/v\d+/profiles/(start|close|stop)/([^/?]+)", u.path)
        if m and m.group(1) == "start":
            try:
                res = json.loads(body)
                d = res.get("data") or {}
                addr = str(d.get("remote_debugging_address") or "")
                dport = int(addr.rsplit(":", 1)[1]) if ":" in addr else int(d.get("remote_debugging_port") or 0)
                if dport:
                    old = FWD.pop(m.group(2), None)
                    if old:
                        old.stop()
                    fw = Forward(dport, [client])
                    FWD[m.group(2)] = fw
                    host = (self.headers.get("Host") or "").rsplit(":", 1)[0] or lan_ips()[0]
                    d["remote_debugging_address"] = f"{host}:{fw.lport}"
                    d.pop("websocket_debugging_url", None)
                    res["data"] = d
                    body = json.dumps(res, ensure_ascii=False).encode("utf-8")
                    print(f"  ▶ {client} mở profile {m.group(2)} – chuyển tiếp cổng {fw.lport} → {dport}", flush=True)
            except Exception as e:
                print(f"  ⚠ không đọc được kết quả mở profile: {e}", flush=True)
        elif m:
            fw = FWD.pop(m.group(2), None)
            if fw:
                fw.stop()
            print(f"  ■ {client} đóng profile {m.group(2)}", flush=True)
        return self._send(st, body)


CFG = {}


def main():
    CFG.update(_conf())
    try:
        _local("/api/v3/profiles?page=1&per_page=1")
        gpm_ok = "đang mở ✔"
    except Exception:
        gpm_ok = "CHƯA mở – hãy mở phần mềm GPM-Login trên máy này"
    srv = ThreadingHTTPServer(("0.0.0.0", int(CFG["port"])), H)
    ips = lan_ips()
    print("=" * 64)
    print("  CẦU NỐI GPM-LOGIN đang chạy – để cửa sổ này mở trong lúc máy kia dùng tool")
    print("=" * 64)
    print(f"  GPM-Login trên máy này : {gpm_ok}")
    for ip in ips or ["(không đọc được IP – xem bằng lệnh ipconfig)"]:
        print(f"  Địa chỉ điền vào tool  : http://{ip}:{CFG['port']}")
    print(f"  Mã kết nối             : {CFG['key']}")
    print("  (Windows hỏi cho phép qua tường lửa -> bấm Cho phép / Allow cho mạng Riêng tư)")
    print("  Chỉ dùng trong cùng mạng nội bộ hoặc Tailscale / ZeroTier – KHÔNG mở cổng ra Internet.")
    print("-" * 64, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
