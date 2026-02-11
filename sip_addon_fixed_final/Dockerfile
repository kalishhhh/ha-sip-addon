FROM alpine:3.19

# Install dependencies
RUN apk add --no-cache \
    bash \
    jq \
    python3 \
    py3-pip \
    pjproject \
    pjproject-dev \
    pjsua \
    alsa-lib \
    alsa-utils

# Install Python packages
RUN pip3 install --no-cache-dir --break-system-packages \
    flask \
    requests

# Copy application
COPY app_simple.py /app/app.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

WORKDIR /app

ENTRYPOINT ["/run.sh"]
