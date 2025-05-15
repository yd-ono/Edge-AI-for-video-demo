# Node.js 18 を含む Red Hat UBI9 Micro ベースイメージ
FROM registry.access.redhat.com/ubi9/nodejs-22-minimal:latest

# 作業ディレクトリを設定
WORKDIR /opt/app-root/src

# package.jsonとpackage-lock.jsonを先にコピーして依存関係をインストール
COPY frontend/package*.json ./

USER root
RUN chown -R 1001:0 /opt/app-root/src

USER 1001
RUN npm install --omit=dev

# アプリケーションコードをコピー
COPY frontend .

# 必要に応じてポート公開（環境変数で変更可能）
EXPOSE 8000
EXPOSE 8081

# デフォルトの起動コマンド
CMD ["node", "server.js"]
