FROM postgis/postgis:15-3.4

# UUID extension 및 TimescaleDB 설치
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg postgresql-contrib \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /etc/apt/keyrings/timescaledb.gpg \
    && . /etc/os-release \
    && echo "deb [signed-by=/etc/apt/keyrings/timescaledb.gpg] https://packagecloud.io/timescale/timescaledb/debian/ ${VERSION_CODENAME} main" > /etc/apt/sources.list.d/timescaledb.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends timescaledb-2-postgresql-15 \
    && rm -rf /var/lib/apt/lists/*

# Create necessary directories for initialization
RUN mkdir -p /docker-entrypoint-initdb.d
