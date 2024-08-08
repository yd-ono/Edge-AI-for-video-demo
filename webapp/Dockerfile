FROM registry.access.redhat.com/ubi9/ubi-minimal:latest as builder
# USER root

WORKDIR /app
COPY ./requirements.txt ./

RUN microdnf -y update && \
    microdnf --disableplugin subscription-manager -y install gcc python3-devel python3-pip libglvnd-glx && \
    microdnf clean all

RUN pip install --no-cache-dir -r requirements.txt

# FROM registry.access.redhat.com/ubi9/ubi-minimal:latest as production
# WORKDIR /app
# COPY ./src /app

# RUN microdnf -y update && \
#     microdnf --disableplugin subscription-manager -y install gcc python3-devel python3-pip libglvnd-glx && \
#     microdnf clean all

# COPY --from=builder /usr/local/lib64/python3.9/site-packages /usr/local/lib64/python3.9/site-packages
# COPY --from=builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
# COPY --from=builder /usr/local/bin /usr/local/bin
# COPY --from=builder /usr/bin /usr/bin
# COPY --from=builder /usr/lib /usr/lib
# COPY --from=builder /usr/lib64 /usr/lib64

EXPOSE 5000

CMD python -m flask run --host 0.0.0.0