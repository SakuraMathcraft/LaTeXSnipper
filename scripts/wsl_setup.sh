#!/bin/bash
echo 'Acquire::ForceIPv4 true;' | sudo tee /etc/apt/apt.conf.d/99force-ipv4 > /dev/null
sudo apt-get update -qq
sudo apt-get install -y libegl1 libgl1 libopengl0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0
echo "=== Done ==="
