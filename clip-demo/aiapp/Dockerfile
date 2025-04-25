FROM registry.access.redhat.com/ubi9/ubi-minimal:latest

# USER root
RUN microdnf --disableplugin subscription-manager -y install gcc python3-devel python3-pip libglvnd-glx fontconfig \
    && microdnf clean all

# 必要なPythonパッケージ
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt


COPY fonts/ipaexg.ttf /usr/share/fonts/ipaexg.ttf

# アプリ起動などはここに続く
WORKDIR /app/src
COPY src .
EXPOSE 9000
CMD ["python", "app.py"]