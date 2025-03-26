#!/bin/bash

# Update package list
apt-get update

# Install required packages
apt-get install -y --no-install-recommends curl gnupg ffmpeg tzdata

# Install Node.js from the official source
curl -sL https://deb.nodesource.com/setup_20.x | bash -

# Install Node.js
apt-get install -y --no-install-recommends nodejs

# Set timezone to Vietnam
ln -fs /usr/share/zoneinfo/Asia/Ho_Chi_Minh /etc/localtime

# Reconfigure timezone
dpkg-reconfigure -f noninteractive tzdata

# Remove apt cache to reduce image size
rm -rf /var/lib/apt/lists/*
