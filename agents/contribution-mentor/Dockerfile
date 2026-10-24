FROM golang:1.24-alpine AS build

WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /contribution-mentor ./cmd/contribution-mentor

FROM alpine:3.22

COPY --from=build /contribution-mentor /usr/local/bin/contribution-mentor
USER 65532:65532
ENTRYPOINT ["contribution-mentor"]
CMD ["-repo", "/workspace"]
