#!/bin/bash

PROJECT_DIR="/Users/yono/Documents/work/Edge-AI-for-video-demo"

podman run --rm -u $(id -u) \
-v $PROJECT_DIR/models:/models \
-p 9000:9000 \
registry.connect.redhat.com/intel/openvino-model-server:latest \
--model_name demo \
--model_path /models/demo \
--port 9000 \
--rest_port 9090 \
--metrics_enabled \
--target_device CPU \
--shape auto