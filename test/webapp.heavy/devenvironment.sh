#!/bin/bash

sudo podman run --rm -it \
  --privileged \
  --device=/dev/video0 \
  --device=/dev/video1 \
  --group-add=39 \
  --security-opt seccomp=unconfined \
  --security-opt apparmor=unconfined \
  -p 5000:5000 \
  --security-opt label=disable quay.io/yono/yolov8-demo:2.0 /bin/bash