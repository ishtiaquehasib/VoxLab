# coding=utf-8
# Copyright 2026 The Alibaba Qwen team.
# SPDX-License-Identifier: Apache-2.0
#
# VOXLAB: package marker for qwen_tts.cli (the gradio demo lives at
# qwen_tts/cli/demo.py). The upstream package ships this directory as a
# package; without this file the demo can only be reached as a namespace
# package and PyInstaller's --collect-all may skip it. The demo itself
# is NOT imported by the clone engines.
