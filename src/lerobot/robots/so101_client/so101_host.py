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

import base64
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import cv2
import draccus
import numpy as np
import zmq

from lerobot.utils.constants import ACTION

from ..so101_follower import SO101Follower, SO101FollowerConfig

logger = logging.getLogger(__name__)

JOINT_KEYS: tuple[str, ...] = (
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
    "gripper.pos",
)


@dataclass
class SO101HostNetworkConfig:
    """Networking parameters for the SO-101 remote host."""

    port_zmq_cmd: int = 6000
    port_zmq_observations: int = 6001
    connection_time_s: float | None = None
    watchdog_timeout_ms: int = 500
    max_loop_freq_hz: int = 60
    jpeg_quality: int = 90


@dataclass
class SO101RemoteHostConfig:
    """Bundle robot + network configuration for CLI use."""

    robot: SO101FollowerConfig
    host: SO101HostNetworkConfig = field(default_factory=SO101HostNetworkConfig)


class SO101Host:
    """Bridge between the physical follower arm and a remote client."""

    def __init__(self, config: SO101HostNetworkConfig):
        self.zmq_context = zmq.Context()

        self.zmq_cmd_socket = self.zmq_context.socket(zmq.PULL)
        self.zmq_cmd_socket.setsockopt(zmq.CONFLATE, 1)
        self.zmq_cmd_socket.bind(f"tcp://*:{config.port_zmq_cmd}")

        self.zmq_observation_socket = self.zmq_context.socket(zmq.PUSH)
        self.zmq_observation_socket.setsockopt(zmq.CONFLATE, 1)
        self.zmq_observation_socket.bind(f"tcp://*:{config.port_zmq_observations}")

        self.connection_time_s = config.connection_time_s
        self.watchdog_timeout_ms = config.watchdog_timeout_ms
        self.max_loop_freq_hz = config.max_loop_freq_hz
        self.jpeg_quality = config.jpeg_quality

        self.last_observation: dict[str, Any] = {}

    def disconnect(self) -> None:
        self.zmq_observation_socket.close()
        self.zmq_cmd_socket.close()
        self.zmq_context.term()


def _encode_frames(observation: dict[str, Any], jpeg_quality: int) -> dict[str, Any]:
    serializable: dict[str, Any] = {}
    for key, value in observation.items():
        if isinstance(value, np.ndarray):
            ret, buffer = cv2.imencode(".jpg", value, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
            if ret:
                serializable[key] = base64.b64encode(buffer).decode("utf-8")
            else:
                serializable[key] = ""
        elif isinstance(value, (np.floating, np.integer)):
            serializable[key] = float(value)
        elif key == ACTION:
            continue  # internal artifact, skip
        else:
            serializable[key] = value
    return serializable


@draccus.wrap()
def main(cfg: SO101RemoteHostConfig) -> None:
    logging.info("Configuring SO-101 follower")
    robot = SO101Follower(cfg.robot)

    logging.info("Connecting SO-101 follower")
    robot.connect()

    host = SO101Host(cfg.host)
    logging.info(
        "SO-101 remote host listening on cmd=%s obs=%s",
        cfg.host.port_zmq_cmd,
        cfg.host.port_zmq_observations,
    )

    last_cmd_time = time.time()
    watchdog_triggered = False
    start = time.perf_counter()

    try:
        while True:
            loop_start = time.time()
            if cfg.host.connection_time_s is not None and time.perf_counter() - start > cfg.host.connection_time_s:
                logging.info("Connection time reached, shutting down host loop.")
                break

            try:
                msg = host.zmq_cmd_socket.recv_string(zmq.NOBLOCK)
                command = json.loads(msg)
                robot.send_action(command)
                last_cmd_time = time.time()
                watchdog_triggered = False
            except zmq.Again:
                pass
            except Exception as e:
                logging.error("Failed to process incoming command: %s", e)

            now = time.time()
            if (
                cfg.host.watchdog_timeout_ms > 0
                and (now - last_cmd_time) * 1000 > cfg.host.watchdog_timeout_ms
                and not watchdog_triggered
            ):
                logging.warning(
                    "No command received for %.0f ms. Holding last commanded position.",
                    cfg.host.watchdog_timeout_ms,
                )
                watchdog_triggered = True

            observation = robot.get_observation()
            host.last_observation = observation
            serializable = _encode_frames(observation, cfg.host.jpeg_quality)

            try:
                host.zmq_observation_socket.send_string(json.dumps(serializable), flags=zmq.NOBLOCK)
            except zmq.Again:
                logging.debug("Dropping observation, no remote client ready.")

            elapsed = time.time() - loop_start
            time.sleep(max(1 / cfg.host.max_loop_freq_hz - elapsed, 0))

    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received, stopping host.")
    finally:
        logging.info("Disconnecting SO-101 follower.")
        robot.disconnect()
        host.disconnect()


if __name__ == "__main__":
    main()

