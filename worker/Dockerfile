# FieldKey export worker: GDAL (official OSGeo image) + psycopg2, standard library otherwise.
#   docker build -t fieldkey-export worker/
#   docker run --rm --env-file worker/.env -p 8080:8080 fieldkey-export            # serve (default)
#   docker run --rm --env-file worker/.env fieldkey-export loop --interval 30       # always-on host
# Secrets come from the environment (--env-file, or the host's secret store). Never bake them in.
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.10.3

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3-psycopg2 ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 worker

WORKDIR /app
COPY fieldkey_export/ ./fieldkey_export/
COPY tests/ ./tests/

USER worker
ENV PYTHONUNBUFFERED=1 PORT=8080
EXPOSE 8080
# Checks the image itself on build: tile maths, GeoPackage writing, caps (no network, no database)
RUN python3 -m unittest discover -s tests -t . -q

ENTRYPOINT ["python3", "-m", "fieldkey_export"]
CMD ["serve"]
