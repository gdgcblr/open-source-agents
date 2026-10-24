# Build context must be agents/securevantara, never the repository root.
FROM python:3.12.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    XALGORIX_NO_AUTO_UPDATE=1 XALGORIX_ALLOW_AUTO_INSTALL=false \
    XALGORIX_AUTO_INSTALL_SUDO=false HOME=/tmp/securevantara
WORKDIR /app
COPY securevantara/ ./securevantara/

FROM base AS tests
COPY tests/ ./tests/
CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]

FROM base AS download
ARG TARGETARCH
RUN python -c 'import hashlib, os, pathlib, urllib.request; arch=os.environ["TARGETARCH"]; digests={"amd64":"8a0005f5e76dafa91c4f7ea1a039a7c4dfa2348e9c981c85400832aa81181a32","arm64":"bf789421e2ccd936f34efc265badf144ec19753033d0b69c56a1ce55bfc28c8f"}; data=urllib.request.urlopen("https://github.com/xalgorix/xalgorix/releases/download/v4.6.159/xalgorix-linux-"+arch, timeout=120).read(); assert hashlib.sha256(data).hexdigest()==digests[arch], "checksum mismatch"; pathlib.Path("/tmp/xalgorix").write_bytes(data)'

FROM base AS xalgorix
COPY --from=download --chmod=0555 /tmp/xalgorix /usr/local/bin/xalgorix
USER 65532:65532
ENTRYPOINT ["python", "-m", "securevantara"]

# Default build is local-only and does not download Xalgorix.
FROM base AS local
USER 65532:65532
ENTRYPOINT ["python", "-m", "securevantara"]
