import sys, os, json, threading, time, uuid, webbrowser, socket, re
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BASE = Path(__file__).resolve().parent
if sys.stdout is None: sys.stdout = open(os.devnull, "w")
if sys.stderr is None: sys.stderr = open(BASE / "server.log", "a", encoding="utf-8")
PORT = 8765
URL = f"http://127.0.0.1:{PORT}/"

def busy():
    s = socket.socket(); s.settimeout(0.5)
    try: return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally: s.close()

if busy():
    webbrowser.open(URL); sys.exit(0)

import core
JOBS = {}

def start_job(topic, mode):
    jid = uuid.uuid4().hex[:8]
    job = {"state": "running", "log": [], "report_id": None, "error": None}
    JOBS[jid] = job
    def log(m): job["log"].append(time.strftime("%H:%M:%S ") + m)
    def work():
        try:
            job["report_id"] = core.run_job(topic, mode, log); job["state"] = "done"
        except Exception as e:
            job["error"] = str(e); job["state"] = "error"; log("HATA: " + str(e))
    threading.Thread(target=work, daemon=True).start()
    return jid

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/":
            self.send(200, (BASE / "ui.html").read_text(encoding="utf-8"), "text/html")
        elif p == "/api/health":
            self.send(200, json.dumps({
                "gemini_configured": bool(core.KEY),
                "brave_configured": bool(core.BRAVE_KEY),
                "repo_found": bool(core.find_script())
            }, ensure_ascii=False))
        elif p == "/api/history":
            self.send(200, json.dumps(core.list_reports(), ensure_ascii=False))
        elif p.startswith("/api/report/"):
            rid = p.split("/")[-1]
            f = core.REPORTS / f"report-{rid}.json"
            if re.fullmatch(r"[\w\-]+", rid) and f.exists(): self.send(200, f.read_text(encoding="utf-8"))
            else: self.send(404, "{}")
        elif p.startswith("/api/status/"):
            j = JOBS.get(p.split("/")[-1])
            self.send(200 if j else 404, json.dumps(j or {}, ensure_ascii=False))
        else:
            self.send(404, "{}")
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/start":
            topic = (data.get("topic") or "").strip()
            if not topic: return self.send(400, json.dumps({"error": "konu bos"}))
            self.send(200, json.dumps({"job": start_job(topic, data.get("mode") or "normal")}))
        elif self.path == "/api/history/clear":
            deleted = 0
            for report_file in core.REPORTS.glob("report-*.json"):
                try:
                    report_file.unlink()
                    deleted += 1
                except OSError as exc:
                    self.send(500, json.dumps({"error": str(exc)}, ensure_ascii=False))
                    return
            self.send(200, json.dumps({"deleted": deleted}, ensure_ascii=False))
        elif self.path == "/api/shutdown":
            self.send(200, "{}"); threading.Timer(0.5, lambda: os._exit(0)).start()
        else:
            self.send(404, "{}")

srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
threading.Timer(1.0, lambda: webbrowser.open(URL)).start()
srv.serve_forever()