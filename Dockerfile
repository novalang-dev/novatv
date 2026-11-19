FROM vexorian/dizquetv:latest

RUN mkdir -p /config /medya
COPY ./logo.png /medya/logo.png
COPY ./backup/ /config/

ENV DIZQUETV_DATA_DIR=/config
ENV DIZQUETV_PORT=8000
EXPOSE 8000
