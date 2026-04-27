FROM python:3.12-slim

WORKDIR /app

RUN pip install flask requests apprise

COPY freeloadarr_detector.py /app/
COPY freeloadarr_webui.py /app/
COPY static /app/static
COPY start_freeloadarr.sh /usr/local/bin/start_freeloadarr.sh

RUN chmod +x /usr/local/bin/start_freeloadarr.sh

ENV DB_PATH=/config/freeloadarr.db
ENV WEBUI_HOST=0.0.0.0
ENV WEBUI_PORT=11012

CMD ["/usr/local/bin/start_freeloadarr.sh"]
