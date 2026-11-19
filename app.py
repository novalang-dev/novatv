import os, json, base64, subprocess, threading, urllib.request, urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

PORT = int(os.environ.get("PORT", 8000))
HLS_DIR = "/app/hls"
os.makedirs(HLS_DIR, exist_ok=True)
DB_FILE = "/app/ayarlar.json"
LOG_FILE = "/app/ffmpeg.log"

DEFAULT_DB = {
    "kanal": "NovaTV",
    "logo_konum": "top-right",
    "mod": "surekli",          # "surekli" veya "zamanli"
    "baslangic_saati": "20:00",
    "bitis_saati": "02:00",
    "gh_token": "",
    "videolar": [
        {"ad": "Big Buck Bunny (Test)", "url": "https://archive.org/download/BigBuckBunny_328/BigBuckBunny_512kb.mp4"}
    ]
}

ffmpeg_proc = None
durum_mesaji = "Başlatılıyor..."

def get_token(db):
    env_tok = os.environ.get("GH_TOKEN", "").strip()
    return env_tok if env_tok else db.get("gh_token", "").strip()

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            for k, v in DEFAULT_DB.items():
                d.setdefault(k, v)
            return d
    try:
        req = urllib.request.urlopen("https://raw.githubusercontent.com/novalang-dev/novatv/main/ayarlar.json", timeout=5)
        data = json.loads(req.read().decode("utf-8"))
        for k, v in DEFAULT_DB.items():
            data.setdefault(k, v)
        save_local(data)
        return data
    except Exception:
        save_local(DEFAULT_DB)
        return dict(DEFAULT_DB)

def save_local(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def sync_github(data):
    token = get_token(data)
    if not token:
        return
    api = "https://api.github.com/repos/novalang-dev/novatv/contents/ayarlar.json"
    headers = {
        "Authorization": f"token {token}",
        "User-Agent": "NovaTV",
        "Accept": "application/vnd.github.v3+json"
    }
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
    payload = {"message": "NovaTV kontrol merkezi guncellemesi", "content": content_b64}
    if sha:
        payload["sha"] = sha
    try:
        req = urllib.request.Request(api, data=json.dumps(payload).encode("utf-8"), headers=headers, method="PUT")
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass

def yayin_saati_uygun_mu(db):
    if db.get("mod", "surekli") != "zamanli":
        return True
    try:
        now_m = datetime.now().hour * 60 + datetime.now().minute
        sh, sm = map(int, db.get("baslangic_saati", "20:00").split(":"))
        eh, em = map(int, db.get("bitis_saati", "02:00").split(":"))
        start_m = sh * 60 + sm
        end_m = eh * 60 + em
        if start_m == end_m:
            return True
        if start_m < end_m:
            return start_m <= now_m < end_m
        else:
            return now_m >= start_m or now_m < end_m
    except Exception:
        return True

def stop_stream():
    global ffmpeg_proc
    if ffmpeg_proc and ffmpeg_proc.poll() is None:
        ffmpeg_proc.terminate()
        try:
            ffmpeg_proc.wait(timeout=5)
        except Exception:
            ffmpeg_proc.kill()
    ffmpeg_proc = None

def start_stream():
    global ffmpeg_proc, durum_mesaji
    stop_stream()
    for f in os.listdir(HLS_DIR):
        try:
            os.remove(os.path.join(HLS_DIR, f))
        except Exception:
            pass

    db = load_db()
    videolar = db.get("videolar", [])
    if not videolar:
        durum_mesaji = "Listede video yok (Yayında değil)"
        return

    if not yayin_saati_uygun_mu(db):
        durum_mesaji = f"Schedule Beklemede ({db.get('baslangic_saati')} - {db.get('bitis_saati')} arası yayın aktif)"
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
        f"{HLS_DIR}/canli.m3u8"
    ]
    log_f = open(LOG_FILE, "w", encoding="utf-8")
    ffmpeg_proc = subprocess.Popen(cmd, stdout=log_f, stderr=subprocess.STDOUT)
    durum_mesaji = f"Canlı Yayında ({len(videolar)} video döngüde)"

def schedule_watcher():
    import time
    while True:
        time.sleep(30)
        db = load_db()
        uygun = yayin_saati_uygun_mu(db)
        aktif = ffmpeg_proc is not None and ffmpeg_proc.poll() is None
        if uygun and not aktif and db.get("videolar"):
            start_stream()
        elif not uygun and aktif:
            start_stream()

HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__KANAL__ Kontrol Merkezi</title>
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<style>
  *{box-sizing:border-box}
  body{margin:0;font-family:system-ui,-apple-system,sans-serif;background:#090d16;color:#f1f5f9;padding:20px}
  .wrap{max-width:1020px;margin:auto;display:grid;gap:18px}
  .card{background:#111827;border:1px solid #1f2937;border-radius:14px;padding:20px}
  .top{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:12px}
  h1,h2{margin:0;font-size:19px;display:flex;align-items:center;gap:10px}
  .pill{background:#16a34a;color:#fff;font-size:12px;padding:4px 10px;border-radius:99px;font-weight:600}
  .pill.wait{background:#d97706}
  video{width:100%;border-radius:12px;background:#000;aspect-ratio:16/9}
  .row{display:flex;gap:10px;margin-top:12px;flex-wrap:wrap}
  input,select{padding:10px 12px;border-radius:8px;border:1px solid #374151;background:#090d16;color:#fff;font-size:14px}
  input[type=text],input[type=password]{flex:1;min-width:180px}
  button{background:#2563eb;color:#fff;border:none;padding:10px 16px;border-radius:8px;font-weight:600;cursor:pointer}
  button:hover{background:#1d4ed8}
  .btn-sm{padding:6px 10px;font-size:12px}
  .btn-gray{background:#374151}
  .btn-gray:hover{background:#4b5563}
  .btn-red{background:#dc2626}
  .btn-red:hover{background:#b91c1c}
  .item{display:flex;justify-content:space-between;align-items:center;background:#090d16;border:1px solid #1f2937;padding:12px;border-radius:10px;margin-bottom:8px;gap:10px}
  .actions{display:flex;gap:6px}
  .url{color:#9ca3af;font-size:12px;word-break:break-all;margin-top:2px}
  .hint{font-size:12px;color:#9ca3af;margin-top:8px}
  pre{background:#090d16;border:1px solid #1f2937;padding:12px;border-radius:10px;color:#cbd5e1;font-size:12px;max-height:170px;overflow:auto;margin:0}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <div class="top">
      <h1>📺 __KANAL__ Canlı Yayın</h1>
      <span class="pill __PILL_CLASS__">__DURUM__</span>
    </div>
    <video id="tv" controls autoplay muted></video>
    <div class="row">
      <input id="m3u" type="text" readonly>
      <button onclick="navigator.clipboard.writeText(document.getElementById('m3u').value);alert('M3U Linki Kopyalandı!')">📋 M3U Kopyala</button>
      <form method="POST" action="/yeniden-baslat" style="margin:0"><button type="submit" class="btn-gray">🔄 Yayını Tazele</button></form>
    </div>
  </div>

  <div class="card">
    <h2>🕒 Yayın Zamanlaması (Schedule)</h2>
    <form method="POST" action="/schedule">
      <div class="row">
        <select name="mod">
          <option value="surekli" __MOD_SUR__>7/24 Sürekli Yayın</option>
          <option value="zamanli" __MOD_ZAM__>Saat Aralıklı Yayın (Schedule)</option>
        </select>
        <label style="display:flex;align-items:center;gap:6px;font-size:14px">Başlangıç: <input type="time" name="baslangic_saati" value="__BASLANGIC__"></label>
        <label style="display:flex;align-items:center;gap:6px;font-size:14px">Bitiş: <input type="time" name="bitis_saati" value="__BITIS__"></label>
        <button type="submit">⏱️ Zamanlamayı Kaydet</button>
      </div>
      <div class="hint">Sunucu saati (UTC): __SAAT_NOW__ — Saat aralıklı mod seçersen belirlenen saatler dışında yayın otomatik durur, saat gelince otomatik başlar.</div>
    </form>
  </div>

  <div class="card">
    <h2>🎬 Yayın Listesi (__VIDEO_SAYISI__ İçerik)</h2>
    <form class="row" method="POST" action="/ekle" style="margin-bottom:14px">
      <input type="text" name="ad" placeholder="İçerik Adı (örn: Akşam Filmi)" required>
      <input type="text" name="url" placeholder="MP4 veya M3U8 Bağlantısı (https://...)" required>
      <button type="submit">➕ Ekle</button>
    </form>
    __VIDEO_LISTESI__
  </div>

  <div class="card">
    <h2>⚙️ Kanal ve GitHub Kalıcılık Ayarları</h2>
    <form method="POST" action="/ayar">
      <div class="row">
        <input type="text" name="kanal" value="__KANAL__" placeholder="Kanal Adı">
        <select name="logo_konum">
          <option value="top-right" __SEL_TR__>Logo: Sağ Üst</option>
          <option value="top-left" __SEL_TL__>Logo: Sol Üst</option>
          <option value="bottom-right" __SEL_BR__>Logo: Sağ Alt</option>
          <option value="bottom-left" __SEL_BL__>Logo: Sol Alt</option>
        </select>
        <input type="password" name="gh_token" value="__TOKEN__" placeholder="GitHub Token (veya Render'da GH_TOKEN env)">
        <button type="submit">💾 Ayarları Kaydet</button>
      </div>
    </form>
  </div>

  <div class="card">
    <h2>📜 Canlı Motor Logu (FFmpeg)</h2>
    <pre>__LOG_ICERIK__</pre>
  </div>
</div>
<script>
  const base = window.location.origin;
  document.getElementById('m3u').value = base + '/novatv.m3u';
  const v = document.getElementById('tv');
  const s = base + '/hls/canli.m3u8';
  if (Hls.isSupported()) {
    const h = new Hls({ liveSyncDurationCount: 2 });
    h.loadSource(s);
    h.attachMedia(v);
  } else if (v.canPlayType('application/vnd.apple.mpegurl')) {
    v.src = s;
  }
</script>
</body>
</html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            db = load_db()
            vids = db.get("videolar", [])
            items = ""
            for i, v in enumerate(vids):
                items += (
                    f'<div class="item"><div><b>{i+1}. {v["ad"]}</b><div class="url">{v["url"]}</div></div>'
                    f'<div class="actions">'
                    f'<form method="POST" action="/tasi" style="margin:0"><input type="hidden" name="idx" value="{i}"><input type="hidden" name="yon" value="yukari"><button class="btn-sm btn-gray">▲</button></form>'
                    f'<form method="POST" action="/tasi" style="margin:0"><input type="hidden" name="idx" value="{i}"><input type="hidden" name="yon" value="asagi"><button class="btn-sm btn-gray">▼</button></form>'
                    f'<form method="POST" action="/sil" style="margin:0"><input type="hidden" name="idx" value="{i}"><button class="btn-sm btn-red">Sil</button></form>'
                    f'</div></div>'
                )
            if not items:
                items = '<div class="hint">Listede henüz içerik yok. Yukarıdan bağlantı ekleyebilirsin.</div>'

            k = db.get("logo_konum", "top-right")
            mod = db.get("mod", "surekli")
            log_text = "Henüz log oluşmadı."
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as lf:
                    lines = lf.readlines()[-12:]
                    if lines:
                        log_text = "".join(lines)

            aktif = ffmpeg_proc is not None and ffmpeg_proc.poll() is None
            page = (HTML
                .replace("__KANAL__", db.get("kanal", "NovaTV"))
                .replace("__DURUM__", durum_mesaji)
                .replace("__PILL_CLASS__", "" if aktif else "wait")
                .replace("__MOD_SUR__", "selected" if mod == "surekli" else "")
                .replace("__MOD_ZAM__", "selected" if mod == "zamanli" else "")
                .replace("__BASLANGIC__", db.get("baslangic_saati", "20:00"))
                .replace("__BITIS__", db.get("bitis_saati", "02:00"))
                .replace("__SAAT_NOW__", datetime.now().strftime("%H:%M"))
                .replace("__VIDEO_SAYISI__", str(len(vids)))
                .replace("__VIDEO_LISTESI__", items)
                .replace("__TOKEN__", db.get("gh_token", ""))
                .replace("__SEL_TR__", "selected" if k == "top-right" else "")
                .replace("__SEL_TL__", "selected" if k == "top-left" else "")
                .replace("__SEL_BR__", "selected" if k == "bottom-right" else "")
                .replace("__SEL_BL__", "selected" if k == "bottom-left" else "")
                .replace("__LOG_ICERIK__", log_text)
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode("utf-8"))
        elif path == "/novatv.m3u":
            db = load_db()
            host = self.headers.get("Host", "")
            proto = self.headers.get("X-Forwarded-Proto", "https")
            kanal = db.get("kanal", "NovaTV")
            m3u = f'#EXTM3U\n#EXTINF:-1 tvg-logo="{proto}://{host}/logo.png" group-title="{kanal}",{kanal}\n{proto}://{host}/hls/canli.m3u8\n'
            self.send_response(200)
            self.send_header("Content-Type", "audio/x-mpegurl")
            self.end_headers()
            self.wfile.write(m3u.encode("utf-8"))
        elif path == "/logo.png":
            with open("/app/logo.png", "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(data)
        elif path.startswith("/hls/"):
            fpath = "/app" + path
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
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        db = load_db()
        yayin_guncelle = True

        if path == "/ekle":
            ad = form.get("ad", ["Video"])[0].strip()
            url = form.get("url", [""])[0].strip()
            if url:
                db["videolar"].append({"ad": ad, "url": url})
        elif path == "/sil":
            idx = int(form.get("idx", [-1])[0])
            if 0 <= idx < len(db["videolar"]):
                db["videolar"].pop(idx)
        elif path == "/tasi":
            idx = int(form.get("idx", [-1])[0])
            yon = form.get("yon", [""])[0]
            vids = db["videolar"]
            if yon == "yukari" and idx > 0:
                vids[idx - 1], vids[idx] = vids[idx], vids[idx - 1]
            elif yon == "asagi" and 0 <= idx < len(vids) - 1:
                vids[idx + 1], vids[idx] = vids[idx], vids[idx + 1]
        elif path == "/schedule":
            db["mod"] = form.get("mod", ["surekli"])[0]
            db["baslangic_saati"] = form.get("baslangic_saati", ["20:00"])[0]
            db["bitis_saati"] = form.get("bitis_saati", ["02:00"])[0]
        elif path == "/ayar":
            db["kanal"] = form.get("kanal", ["NovaTV"])[0].strip() or "NovaTV"
            db["logo_konum"] = form.get("logo_konum", ["top-right"])[0]
            db["gh_token"] = form.get("gh_token", [""])[0].strip()
        elif path == "/yeniden-baslat":
            yayin_guncelle = True

        save_local(db)
        threading.Thread(target=sync_github, args=(db,), daemon=True).start()
        if yayin_guncelle:
            threading.Thread(target=start_stream, daemon=True).start()

        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

if __name__ == "__main__":
    load_db()
    threading.Thread(target=start_stream, daemon=True).start()
    threading.Thread(target=schedule_watcher, daemon=True).start()
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
