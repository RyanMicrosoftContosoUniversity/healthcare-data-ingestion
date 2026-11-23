FROM apache/spark:4.1.0-scala2.13-java21-python3-ubuntu@sha256:370ada682945240b41cc2785aeb0b12c1b276b5bb46fc3930ba6732726ed6836
USER root
WORKDIR /workspace
RUN python3 -m pip install --no-cache-dir --index-url https://packagefeedproxy.microsoft.io/pypi/simple/ uv==0.13.8
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY tests ./tests
COPY database ./database
COPY metadata ./metadata
COPY scripts ./scripts
RUN uv sync --locked --extra spark --extra cloud --python 3.13
ENV PYSPARK_PYTHON=/workspace/.venv/bin/python
ENV PYSPARK_DRIVER_PYTHON=/workspace/.venv/bin/python
CMD ["uv", "run", "--locked", "--extra", "spark", "--extra", "cloud", "pytest"]
