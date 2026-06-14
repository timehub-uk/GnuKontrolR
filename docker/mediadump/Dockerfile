FROM alpine:3.24
RUN apk add --no-cache python3 py3-pip ffmpeg
RUN pip3 install --break-system-packages flask gunicorn
WORKDIR /app
COPY app.py /app/app.py
COPY templates /app/templates
RUN adduser -D -u 1001 mediadump \
    && mkdir -p /data/uploads /data/outputs \
    && chown mediadump:mediadump /data /data/uploads /data/outputs \
    && chmod 770 /data /data/uploads /data/outputs
USER mediadump
EXPOSE 5001
CMD ["gunicorn", "-b", "0.0.0.0:5001", "-w", "2", "app:app"]
