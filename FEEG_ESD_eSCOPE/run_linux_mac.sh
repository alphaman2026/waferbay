#!/bin/sh
# FEEG_ESD_eSCOPE launcher for Linux / macOS
# Linux: serial port access may require:  sudo usermod -aG dialout $USER  (re-login)
cd "$(dirname "$0")"
python3 -m pip install -q -r requirements.txt
exec python3 FEEG_ESD_eSCOPE.py
