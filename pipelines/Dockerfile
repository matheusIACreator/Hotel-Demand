ARG HOTELML_IMAGE=hotelml:local
FROM ${HOTELML_IMAGE} AS spark
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-21-jre-headless \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-spark.lock ./
RUN pip install --no-cache-dir -r requirements-spark.lock
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    PYSPARK_PYTHON=/usr/local/bin/python \
    SPARK_LOCAL_IP=127.0.0.1
USER hotelml
HEALTHCHECK NONE
ENTRYPOINT ["hotelml"]
CMD ["features", "--help"]

FROM spark AS test
USER root
COPY requirements-dev.lock ./
RUN pip install --no-cache-dir -r requirements-dev.lock
USER hotelml
ENTRYPOINT ["python", "-m", "pytest"]
CMD ["/tests/test_spark_features.py", "-q", "-o", "cache_dir=/tmp/pytest-cache"]
