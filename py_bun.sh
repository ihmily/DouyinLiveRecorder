#!/bin/bash
python \
-m \
nuitka \
--output-dir=out \
--show-progress \
--show-memory \
--follow-imports  \
./main.py
