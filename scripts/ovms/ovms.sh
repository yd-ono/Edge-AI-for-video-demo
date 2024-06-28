#!/bin/bash

podman run --rm -u $(id -u) \
-v ./models:/models \
-p 9000:9000 \
registry.connect.redhat.com/intel/openvino-model-server:latest \
--model_name yolov8n \
--model_path /models/yolov8n \
--port 9000 \
--target_device CPU \
--shape auto