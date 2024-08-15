FROM registry.access.redhat.com/ubi9/ubi-minimal:latest
# USER root

WORKDIR /app
COPY . ./

RUN microdnf -y update && \
    microdnf --disableplugin subscription-manager -y install python3-devel && \
    microdnf clean all \
    pip install --no-cache-dir -r requirements.txt

ENV NIC eth0

CMD python droneinit.py