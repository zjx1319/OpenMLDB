#! /bin/bash

# Copyright 2021 4Paradigm
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

COMPONENT=$1

ulimit -c unlimited
ulimit -n 655360
LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:$(pwd)/lib"
export LD_LIBRARY_PATH
./bin/openmldb --flagfile=./conf/"$COMPONENT".flags --enable_status_service=true
