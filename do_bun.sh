#!/bin/bash
docker buildx build -t douyin-live-recorder:latest  . --load
docker run -d \
  --name app \
  --env TERM=xterm-256color \
  -v "$(pwd)/config:/app/config" \
  -v "$(pwd)/logs:/app/logs" \
  -v "$(pwd)/backup_config:/app/backup_config" \
  -v "$(pwd)/downloads:/app/downloads" \
  --restart always \
  -t -i \
  douyin-live-recorder:latest