#!/usr/bin/env python

# Copyright 2025 The HuggingFace Inc. team. All rights reserved.
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

from dataclasses import dataclass, field

from lerobot.cameras import CameraConfig

from ..config import RobotConfig


@RobotConfig.register_subclass("so101_client")
@dataclass
class SO101ClientConfig(RobotConfig):
    """
    Configuration for the SO-101 remote client.

    Attributes:
        remote_ip: IP or hostname of the machine running the follower host daemon.
        port_zmq_cmd: TCP port used to send joint commands to the host.
        port_zmq_observations: TCP port used to receive observations (joint state + cameras).
        connect_timeout_s: How long to wait for the host to become reachable when connecting.
        polling_timeout_ms: Poll timeout for observation socket.
        cameras: Optional camera metadata mirroring the follower setup (width/height/fps).
    """

    remote_ip: str
    port_zmq_cmd: int = 6000
    port_zmq_observations: int = 6001
    connect_timeout_s: int = 5
    polling_timeout_ms: int = 15
    cameras: dict[str, CameraConfig] = field(default_factory=dict)

