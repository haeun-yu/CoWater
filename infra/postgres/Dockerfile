FROM postgis/postgis:15-3.4-alpine

# UUID extension 설치
RUN apk add --no-cache postgresql-contrib

# Create necessary directories for initialization
RUN mkdir -p /docker-entrypoint-initdb.d
