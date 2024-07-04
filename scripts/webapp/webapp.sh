#!/bin/bash

NODE_IP=$1

podman run --rm -u $(id -u) \
	-e OVMS_ENDPOINT=$NODE_IP:32290 \
	-e MODEL_NAME=demo \
	-e DEVICE="0" \
	-e CONF="0.7" \
	-e FPS="0.03" \
	-e OVMS_TIMEOUT="0.03" \
	-p 5555:5000 \
	-v /dev:/dev \
	quay.io/yono/yolov8-demo:1.0
