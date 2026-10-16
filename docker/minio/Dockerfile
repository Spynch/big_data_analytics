FROM golang:1.24.8-bookworm AS build
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
RUN go install github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z
RUN go install github.com/minio/mc@RELEASE.2025-08-13T08-35-41Z
FROM alpine:3.22.2
COPY --from=build /go/bin/minio /usr/local/bin/minio
COPY --from=build /go/bin/mc /usr/local/bin/mc
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
