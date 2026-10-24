FROM golang:1.26.9-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY *.go ./
RUN CGO_ENABLED=0 go build -o /shop .

FROM alpine:3.24.2
COPY --from=build /shop /shop
ENTRYPOINT ["/shop"]
