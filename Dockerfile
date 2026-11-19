FROM jasongdove/ersatztv:latest

ENV TZ=Europe/Istanbul
ENV ETV_CONFIG_FOLDER=/config

# Logonuzu ve .strm medya dosyalarınızı konteynere alır
COPY ./logo.png /medya/logo.png
COPY ./medya /medya

# Yedek klasörü varsa geri yükler (ilk kurulumda boş klasör oluşturur)
RUN mkdir -p /config
COPY ./backup* /config/

# Hem ErsatzTV'yi hem de /yedek-indir (Port 8410 veya ters proxy) veya dosya kopyalayıcıyı başlatır
CMD sh -c 'while true; do cp -f /config/ersatztv.sqlite3 /app/wwwroot/yedek.db 2>/dev/null; sleep 30; done & exec /app/ErsatzTV'
