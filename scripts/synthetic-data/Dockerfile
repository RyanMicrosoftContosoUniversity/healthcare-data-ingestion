FROM ghcr.io/astral-sh/uv:0.9.17 AS uv
FROM python:3.12.12-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 UV_CACHE_DIR=/app/.uv-cache TMPDIR=/app/.build
WORKDIR /app
RUN mkdir -p .build generator && apt-get update -qq \
    && apt-get install -y --no-install-recommends ca-certificates curl openjdk-17-jre-headless \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
       -o .build/packages-microsoft-prod.deb \
    && dpkg -i .build/packages-microsoft-prod.deb \
    && apt-get update -qq \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -f .build/packages-microsoft-prod.deb
COPY scripts/synthetic-data/synthea-pin.json scripts/synthetic-data/synthea-pin.json
RUN python -c "import json,urllib.request,hashlib,pathlib; p=json.load(open('scripts/synthetic-data/synthea-pin.json')); f=pathlib.Path(p['jar_path']); urllib.request.urlretrieve(p['url'],f); actual=hashlib.sha256(f.read_bytes()).hexdigest(); assert actual==p['sha256'], 'Synthea digest mismatch'"
COPY pyproject.toml uv.lock README.md ./
COPY src src
COPY database/schema-contracts database/schema-contracts
COPY metadata/source-mappings metadata/source-mappings
RUN uv sync --locked --no-dev --extra cloud \
    && useradd --uid 10001 --create-home generator \
    && mkdir -p generator-host-state \
    && chown -R 10001:10001 /app
ENV PATH=/app/.venv/bin:$PATH GENERATOR_TIMEOUT_SECONDS=2700
USER 10001
ENTRYPOINT ["python", "-m", "healthcare_ingestion.generator_host"]
