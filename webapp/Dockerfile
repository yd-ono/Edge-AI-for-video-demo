FROM registry.access.redhat.com/ubi9/ubi-minimal:latest as builder
# USER root

WORKDIR /app
COPY . ./

RUN microdnf -y update && \
    microdnf --disableplugin subscription-manager -y install gcc python3-devel python3-pip libglvnd-glx && \
    microdnf clean all

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

WORKDIR /app/src
CMD python -m flask run --host 0.0.0.0