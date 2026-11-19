import os, json, base64, subprocess, threading, urllib.request, urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("PORT", 8000))
os.makedirs("/app/hls", exist_ok=True)
DB_FILE = "/app/ayarlar.json"
DEFAULT_DB = {
    "kanal": "NovaTV",
    "logo_konum": "top-right",
    "gh_token": "",
    "videolar": [
        {"ad": "Big Buck Bunny (Test)", "url": "https://archive.org/download/BigBuckBunny_328/BigBuckBunny_512kb.mp4"}
    ]
}
ffmpeg_proc = None

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    try:
        req = urllib.request.urlopen("https://raw.githubusercontent.com/novalang-dev/novatv/main/ayarlar.json", timeout=5)
        data = json.loads(req.read().decode("utf-8"))
        save_local(data)
        return data
    except Exception:
        save_local(DEFAULT_DB)
        return DEFAULT_DB

def save_local(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def sync_github(data):
    token = data.get("gh_token", "").strip()
    if not token:
        return
    api = "https://api.github.com/repos/novalang-dev/novatv/contents/ayarlar.json"
    headers = {"Authorization": f"token {token}", "User-Agent": "NovaTV", "Accept": "application/vnd.github.v3+json"}
    sha = None
    try:
        req = urllib.request.Request(api, headers=headers)
        res = json.loads(urllib.request.urlopen(req, timeout=8).read().decode("utf-8"))
        sha = res.get("sha")
    except Exception:
        pass
    clean_data = dict(data)
    clean_data["gh_token"] = ""
    content_b64 = base64.b64encode(json.dumps(clean_data, ensure_ascii=False, indent=2).encode("utf-8")).decode("utf-8")
    payload = {"message": "NovaTV panel ayarlari guncellendi", "content": content_b64}
    if sha:
        payload["sha"] = sha
    try:
        req = urllib.request.Request(api, data=json.dumps(payload).encode("utf-8"), headers=headers, method="PUT")
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass

def start_stream():
    global ffmpeg_proc
    if ffmpeg_proc and ffmpeg_proc.poll() is None:
        ffmpeg_proc.terminate()
        ffmpeg_proc.wait()
    for f in os.listdir("/app/hls"):
        os.remove(os.path.join("/app/hls", f))

    db = load_db()
    videolar = db.get("videolar", [])
    if not videolar:
        return

    with open("/app/concat.txt", "w", encoding="utf-8") as f:
        for v in videolar:
            f.write(f"file '{v['url']}'\n")

    konum_map = {
        "top-right": "W-w-25:25",
        "top-left": "25:25",
        "bottom-right": "W-w-25:H-h-25",
        "bottom-left": "25:H-h-25"
    }
    ov = konum_map.get(db.get("logo_konum", "top-right"), "W-w-25:25")

    cmd = [
        "ffmpeg", "-re", "-stream_loop", "-1",
        "-f", "concat", "-safe", "0", "-protocol_whitelist", "file,http,https,tcp,tls",
        "-i", "/app/concat.txt",
        "-i", "/app/logo.png",
        "-filter_complex", f"[1:v]scale=110:-1[logo];[0:v]scale=1280:720[bg];[bg][logo]overlay={ov}",
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", "1500k", "-maxrate", "1500k", "-bufsize", "3000k",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-f", "hls", "-hls_time", "4", "-hls_list_size", "5", "-hls_flags", "delete_segments",
        "/app/hls/canli.m3u8"
    ]
    ffmpeg_proc = subprocess.Popen(cmd)

HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NovaTV Kontrol Merkezi</title>
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<style>
  *{box-sizing:border-box}
  body{margin:0;font-family:system-ui,-apple-system,sans-serif;background:#0b1120;color:#f1f5f9;padding:20px}
  .wrap{max-width:960px;margin:auto;display:grid;gap:20px}
  .card{background:#1e293b;border:1px solid #334155;border-radius:16px;padding:20px}
  h1,h2{margin:0 0 12px;font-size:20px;display:flex;align-items:center;gap:10px}
  .live{background:#dc2626;font-size:12px;padding:3px 10px;border-radius:99px}
  video{width:100%;border-radius:12px;background:#000;aspect-ratio:16/9}
  .bar{display:flex;gap:10px;margin-top:12px}
  input,select{padding:10px 12px;border-radius:8px;border:1px solid #475569;background:#0f172a;color:#fff;font-size:14px}
  input[type=text],input[type=password]{flex:1}
  button{background:#2563eb;color:#fff;border:none;padding:10px 16px;border-radius:8px;font-weight:600;cursor:pointer}
  button:hover{background:#1d4ed8}
  .del{background:#dc2626;padding:6px 12px;font-size:13px}
  .del:hover{background:#b91c1c}
  .item{display:flex;justify-content:space-between;align-items:center;background:#0f172a;padding:12px;border-radius:10px;margin-bottom:8px;gap:10px}
  .url{color:#94a3b8;font-size:12px;word-break:break-all}
  .hint{font-size:12px;color:#94a3b8;margin-top:6px}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1>📺 __KANAL__ Canlı Yayın Ekranı <span class="live">● CANLI</span></h1>
    <video id="tv" controls autoplay muted></video>
    <div class="bar">
      <input id="m3u" type="text" readonly>
      <button onclick="navigator.clipboard.writeText(document.getElementById('m3u').value);alert('M3U adresi kopyalandı!')">📋 M3U Linkini Kopyala</button>
    </div>
  </div>

  <div class="card">
    <h2>🎬 Yayın Akışı (Videolar)</h2>
    <form class="bar" method="POST" action="/ekle" style="margin-bottom:16px;flex-wrap:wrap">
      <input type="text" name="ad" placeholder="Video Adı (örn: Film 1)" required>
      <input type="text" name="url" placeholder="MP4 veya M3U8 Linki (https://...)" required>
      <button type="submit">➕ Listeye Ekle</button>
    </form>
    __VIDEO_LISTESI__
  </div>

  <div class="card">
    <h2>⚙️ Kanal ve Otomatik Yedek Ayarları</h2>
    <form method="POST" action="/ayar">
      <div class="bar" style="flex-wrap:wrap">
        <input type="text" name="kanal" value="__KANAL__" placeholder="Kanal Adı">
        <select name="logo_konum">
          <option value="top-right" __SEL_TR__>Logo: Sağ Üst</option>
          <option value="top-left" __SEL_TL__>Logo: Sol Üst</option>
          <option value="bottom-right" __SEL_BR__>Logo: Sağ Alt</option>
          <option value="bottom-left" __SEL_BL__>Logo: Sol Alt</option>
        </select>
        <input type="password" name="gh_token" value="__TOKEN__" placeholder="GitHub Token (İsteğe bağlı: ayarları GitHub'a otomatik kaydeder)">
        <button type="submit">💾 Ayarları Kaydet</button>
      </div>
      <div class="hint">GitHub Token girersen eklediğin her video otomatik olarak GitHub repona kaydedilir ve asla silinmez.</div>
    </form>
  </div>
</div>
<script>
  const base = window.location.origin;
  document.getElementById('m3u').value = base + '/novatv.m3u';
  const v = document.getElementById('tv');
  const s = base + '/hls/canli.m3u8';
  if (Hls.isSupported()) { const h = new Hls(); h.loadSource(s); h.attachMedia(v); }
  else if (v.canPlayType('application/vnd.apple.mpegurl')) { v.src = s; }
</script>
</body>
</html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            db = load_db()
            items = ""
            for i, v in enumerate(db.get("videolar", [])):
                items += f'<div class="item"><div><b>{i+1}. {v["ad"]}</b><div class="url">{v["url"]}</div></div><form method="POST" action="/sil"><input type="hidden" name="idx" value="{i}"><button class="del">Sil</button></form></div>'
            if not items:
                items = '<div class="hint">Henüz video eklenmedi. Yukarıdan link yapıştırıp ekleyebilirsin.</div>'
            k = db.get("logo_konum", "top-right")
            page = (HTML
                .replace("__KANAL__", db.get("kanal", "NovaTV"))
                .replace("__VIDEO_LISTESI__", items)
                .replace("__TOKEN__", db.get("gh_token", ""))
                .replace("__SEL_TR__", "selected" if k=="top-right" else "")
                .replace("__SEL_TL__", "selected" if k=="top-left" else "")
                .replace("__SEL_BR__", "selected" if k=="bottom-right" else "")
                .replace("__SEL_BL__", "selected" if k=="bottom-left" else "")
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode("utf-8"))
        elif self.path == "/novatv.m3u":
            db = load_db()
            host = self.headers.get("Host", "")
            proto = self.headers.get("X-Forwarded-Proto", "https")
            kanal = db.get("kanal", "NovaTV")
            m3u = f'#EXTM3U\n#EXTINF:-1 tvg-logo="{proto}://{host}/logo.png" group-title="{kanal}",{kanal}\n{proto}://{host}/hls/canli.m3u8\n'
            self.send_response(200)
            self.send_header("Content-Type", "audio/x-mpegurl")
            self.end_headers()
            self.wfile.write(m3u.encode("utf-8"))
        elif self.path == "/logo.png":
            with open("/app/logo.png", "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(data)
        elif self.path.startswith("/hls/"):
            fpath = "/app" + self.path.split("?")[0]
            if os.path.exists(fpath):
                with open(fpath, "rb") as f:
                    data = f.read()
                self.send_response(200)
                ctype = "application/vnd.apple.mpegurl" if fpath.endswith(".m3u8") else "video/mp2t"
                self.send_header("Content-Type", ctype)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        db = load_db()
        if self.path == "/ekle":
            ad = form.get("ad", ["Video"])[0].strip()
            url = form.get("url", [""])[0].strip()
            if url:
                db["videolar"].append({"ad": ad, "url": url})
        elif self.path == "/sil":
            idx = int(form.get("idx", [-1])[0])
            if 0 <= idx < len(db["videolar"]):
                db["videolar"].pop(idx)
        elif self.path == "/ayar":
            db["kanal"] = form.get("kanal", ["NovaTV"])[0].strip() or "NovaTV"
            db["logo_konum"] = form.get("logo_konum", ["top-right"])[0]
            db["gh_token"] = form.get("gh_token", [""])[0].strip()
        save_local(db)
        threading.Thread(target=sync_github, args=(db,), daemon=True).start()
        threading.Thread(target=start_stream, daemon=True).start()
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

if __name__ == "__main__":
    load_db()
    threading.Thread(target=start_stream, daemon=True).start()
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
