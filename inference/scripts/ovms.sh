#!/bin/bash

podman run --rm -u $(id -u) -v $(pwd)/models:/models -p 9000:9000 registry.connect.redhat.com/intel/openvino-model-server:latest --model_name yolov8n --model_path /models/yolov8n --port 9000 --shape auto