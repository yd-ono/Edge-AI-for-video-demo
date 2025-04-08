FROM registry.access.redhat.com/ubi9/python-311

# 日本語フォント追加（Noto Sans CJK JP）
# USER root
RUN microdnf --disableplugin subscription-manager -y install gcc python3-devel python3-pip libglvnd-glx google-noto-sans-cjk-ttc fontconfig \
    && microdnf clean all

# 必要なPythonパッケージ
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリ起動などはここに続く
COPY src .
WORKDIR /app/src
EXPOSE 8888
CMD ["python", "app.py"]