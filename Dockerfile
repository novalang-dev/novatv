FROM jasongdove/ersatztv:latest

ENV TZ=Europe/Istanbul
ENV ETV_CONFIG_FOLDER=/config

# Klasörleri hazırlar
RUN mkdir -p /medya /config

# Logonu ve .strm dosyalarını içeri kopyalar
COPY ./logo.png /medya/logo.png
COPY ./medya/ /medya/

# GitHub'daki backup klasöründe ersatztv.sqlite3 varsa geri yükler
COPY ./backup/ /config/

# Hem ErsatzTV'yi başlatır hem de tarayıcıdan /yedek.txt olarak indirilebilmesi için
# ErsatzTV'nin kendi web dizinine (wwwroot) .txt uzantısıyla kopyalar
CMD sh -c ' \
  WWW_DIR=$(find / -name "wwwroot" -type d 2>/dev/null | head -n 1); \
  ETV_BIN=$(find / -name "ErsatzTV" -type f -executable 2>/dev/null | head -n 1); \
  (while true; do \
    if [ -f /config/ersatztv.sqlite3 ] && [ -n "$WWW_DIR" ]; then \
      cp -f /config/ersatztv.sqlite3 "$WWW_DIR/yedek.txt"; \
    fi; \
    sleep 20; \
  done) & \
  exec "$ETV_BIN" \
'
