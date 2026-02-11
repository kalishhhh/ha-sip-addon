ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    pjproject \
    alsa-lib \
    alsa-utils \
    jq

# Install Python packages
RUN pip3 install --no-cache-dir --break-system-packages \
    flask==3.0.0 \
    requests==2.31.0

# Copy application
COPY app_simple.py /app/app.py

# Copy rootfs (includes service script)
COPY rootfs /
