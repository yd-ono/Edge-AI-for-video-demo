FROM registry.access.redhat.com/ubi9/ubi-minimal:latest

# USER root
RUN microdnf --disableplugin subscription-manager -y install gcc python3-devel python3-pip libglvnd-glx fontconfig \
    && microdnf clean all

# 必要なPythonパッケージ
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# アプリ起動などはここに続く
WORKDIR /app/src
COPY src .
EXPOSE 8888
CMD ["python", "app.py"]