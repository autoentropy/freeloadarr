FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /config

RUN pip install flask requests

COPY start_freeloadarr.sh /usr/local/bin/start_freeloadarr.sh
RUN chmod +x /usr/local/bin/start_freeloadarr.sh

CMD ["/usr/local/bin/start_freeloadarr.sh"]
