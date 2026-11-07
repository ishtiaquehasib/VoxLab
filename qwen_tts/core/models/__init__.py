# coding=utf-8
# Copyright 2026 The Alibaba Qwen team.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# VOXLAB: this file is qwen_tts/core/models/__init__.py — CONFIG / MODEL /
# PROCESSOR exports. Do NOT swap it with qwen_tts/core/__init__.py
# (tokenizer exports): the v1.1.11 browser upload swapped the two files
# (same name, similar size) and v1.1.11 + v1.1.12 CI both failed on
# "No module named 'qwen_tts.core.configuration_qwen3_tts'".
from .configuration_qwen3_tts import Qwen3TTSConfig
from .modeling_qwen3_tts import Qwen3TTSForConditionalGeneration
from .processing_qwen3_tts import Qwen3TTSProcessor