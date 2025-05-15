FROM registry.access.redhat.com/ubi9/ubi-minimal:latest

WORKDIR /app
COPY . ./

RUN microdnf -y update && \
    microdnf --disableplugin subscription-manager -y install python3-devel python3-pip && \
    microdnf clean all

RUN pip install --no-cache-dir -r requirements.txt

CMD python producer.py