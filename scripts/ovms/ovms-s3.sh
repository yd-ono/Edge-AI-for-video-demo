#!/bin/bash

podman run --rm -u $(id -u) \
	-e AWS_ACCESS_KEY_ID=minio \
	-e AWS_SECRET_ACCESS_KEY=minio123 \
	-e AWS_REGION=dummy \
	-e S3_ENDPOINT=http://192.168.3.101:31306 \
	-p 9000:9000 \
	registry.connect.redhat.com/intel/openvino-model-server:latest \
	--model_name yolov8n \
	--model_path s3://models/yolov8n \
	--port 9000 \
	--shape auto
