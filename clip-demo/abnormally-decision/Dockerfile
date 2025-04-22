FROM registry.access.redhat.com/ubi9/ubi-minimal:latest

# USER root
WORKDIR /app
RUN microdnf --disableplugin subscription-manager -y install gcc python3-devel python3-pip libglvnd-glx fontconfig \
    && microdnf clean all

# 必要なPythonパッケージ
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# アプリ起動などはここに続く
COPY src .
WORKDIR /app/src
EXPOSE 8888
CMD ["python", "app.py"]