FROM jasongdove/ersatztv:latest

ENV TZ=Europe/Istanbul
ENV ETV_CONFIG_FOLDER=/config

# Logonuzu ve .strm medya dosyalarınızı konteynere alır
COPY ./logo.png /medya/logo.png
COPY ./medya /medya

# Yedek klasörü varsa geri yükler
RUN mkdir -p /config
COPY ./backup* /config/

# wwwroot klasörünü otomatik bulur ve veritabanını her 30 saniyede bir yedek.db olarak sunar
CMD sh -c 'WWW_DIR=$(find / -name "wwwroot" -type d 2>/dev/null | head -n 1); while true; do [ -n "$WWW_DIR" ] && cp -f /config/ersatztv.sqlite3 "$WWW_DIR/yedek.db" 2>/dev/null; sleep 30; done & exec $(find / -name "ErsatzTV" -type f -executable 2>/dev/null | head -n 1)'
