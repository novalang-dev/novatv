FROM vexorian/dizquetv:latest

# Klasörleri hazırla
RUN mkdir -p /config /medya

# GitHub'daki logo.png ve backup klasöründeki yedekleri içeri al
COPY ./logo.png /medya/logo.png
COPY ./backup/ /config/

# Render'ın dışarıdan bağlandığı portu ayarla
ENV PORT=8000
EXPOSE 8000

# DizqueTV'yi /config klasörü ve 8000 portu ile başlat
ENTRYPOINT []
CMD ["node", "index.js", "-p", "8000", "-d", "/config"]
