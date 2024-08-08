#!/bin/bash

PROJECT_DIR="/Users/yono/Documents/work/Edge-AI-for-video-demo"

podman run --rm -u $(id -u) \
-v $PROJECT_DIR/models:/models \
-p 9000:9000 \
docker.io/openvino/model_server:latest-gpu \
--model_name test \
--model_path /models/test \
--port 9000 \
--rest_port 9090 \
--target_device CPU \
--shape auto