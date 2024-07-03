#!/bin/bash

PROJECT_DIR="/Users/yono/Documents/work/Edge-AI-for-video-demo"

podman run --rm -u $(id -u) \
-v $HOME/Documents/work/Edge-AI-for-video-demo/models:/models \
-p 5555:5000 \
registry.connect.redhat.com/intel/openvino-model-server:latest \
--model_name demo \
--model_path /models/demo \
--port 9000 \
--target_device CPU \
--shape auto