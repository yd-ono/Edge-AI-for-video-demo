#!/bin/bash

NODE_IP=$1

podman run --rm -u $(id -u) \
	-e AWS_ACCESS_KEY_ID=minio \
	-e AWS_SECRET_ACCESS_KEY=minio123 \
	-e AWS_REGION=dummy \
	-e S3_ENDPOINT=http://$NODE_IP:31306 \
	-p 9000:9000 \
	registry.connect.redhat.com/intel/openvino-model-server:latest \
	--model_name demo \
	--model_path s3://models/demo \
	--port 9000 \
	--shape auto
