# RunReady agent — container image.
#
# The agent needs Python 3.10+; we use 3.12-slim to match the Cloud Run Python
# runtime the sample app targets. The sample app's deps (fastapi/uvicorn) are
# installed so the in-container import check works on the bundled demo.
#
# SECURITY NOTE — container-relative confinement:
#   RunReady confines every file operation to ONE project root via realpath +
#   os.path.commonpath. Inside a container that boundary is evaluated against
#   the CONTAINER filesystem. Mount exactly one project root at /work and pass
#   /work as the project_root. Mount read-only (:ro) to exercise the
#   reject / no-write path. The agent performs NO cloud mutation and still
#   requires an explicit `approve` unless you pass --yes.
FROM python:3.12-slim

WORKDIR /app

# Install deps first for layer caching. Keep each requirements file at its
# original relative path so both installs resolve.
COPY requirements.txt ./requirements.txt
COPY sample_app/requirements.txt ./sample_app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r sample_app/requirements.txt

# Agent source.
COPY . .

# Default: run the deterministic safety path on a COPY of the bundled broken
# app, so the image's own fixture is never mutated and no API key is needed.
# Override by mounting your project:
#   docker run --rm -v /abs/path/to/project:/work rr-agent \
#       python main.py /work --log /work/startup.log --no-model --yes
CMD ["sh", "-c", "cp -r sample_app /tmp/app && python main.py /tmp/app --log /tmp/app/startup.log --no-model --yes"]
