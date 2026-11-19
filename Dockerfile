FROM jrottenberg/ffmpeg:4.4-alpine
WORKDIR /app
RUN apk add --no-cache python3
COPY ./logo.png /app/logo.png
COPY ./app.py /app/app.py
ENV PORT=8000
EXPOSE 8000
CMD ["python3", "/app/app.py"]
