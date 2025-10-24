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
from functools import cached_property
from typing import Any

import cv2
import numpy as np

from lerobot.utils.constants import ACTION, OBS_STATE
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from ..robot import Robot
from .config_so101_client import SO101ClientConfig

logger = logging.getLogger(__name__)

JOINT_KEYS: tuple[str, ...] = (
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
    "gripper.pos",
)


class SO101Client(Robot):
    """Remote proxy robot for an SO-101 follower reachable over the network."""

    config_class = SO101ClientConfig
    name = "so101_client"

    def __init__(self, config: SO101ClientConfig):
        import zmq

        self._zmq = zmq
        super().__init__(config)
        self.config = config

        self.remote_ip = config.remote_ip
        self.port_zmq_cmd = config.port_zmq_cmd
        self.port_zmq_observations = config.port_zmq_observations

        self.polling_timeout_ms = config.polling_timeout_ms
        self.connect_timeout_s = config.connect_timeout_s

        self.zmq_context = None
        self.zmq_cmd_socket = None
        self.zmq_observation_socket = None

        self._is_connected = False
        self.last_frames: dict[str, np.ndarray] = {}
        self.last_remote_state: dict[str, Any] = {}

    @cached_property
    def _motors_ft(self) -> dict[str, type]:
        return {key: float for key in JOINT_KEYS}

    @cached_property
    def _cameras_ft(self) -> dict[str, tuple[int, int, int]]:
        return {
            name: (cfg.height, cfg.width, 3)
            for name, cfg in self.config.cameras.items()
            if cfg.height is not None and cfg.width is not None
        }

    @cached_property
    def observation_features(self) -> dict[str, type | tuple[int, int, int]]:
        return {**self._motors_ft, **self._cameras_ft}

    @cached_property
    def action_features(self) -> dict[str, type]:
        return self._motors_ft

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def is_calibrated(self) -> bool:
        return True

    def connect(self, calibrate: bool = True) -> None:  # noqa: ARG002
        if self._is_connected:
            raise DeviceAlreadyConnectedError(f"{self} already connected")

        zmq = self._zmq
        self.zmq_context = zmq.Context()

        self.zmq_cmd_socket = self.zmq_context.socket(zmq.PUSH)
        self.zmq_cmd_socket.setsockopt(zmq.CONFLATE, 1)
        self.zmq_cmd_socket.connect(f"tcp://{self.remote_ip}:{self.port_zmq_cmd}")

        self.zmq_observation_socket = self.zmq_context.socket(zmq.PULL)
        self.zmq_observation_socket.setsockopt(zmq.CONFLATE, 1)
        self.zmq_observation_socket.connect(f"tcp://{self.remote_ip}:{self.port_zmq_observations}")

        poller = zmq.Poller()
        poller.register(self.zmq_observation_socket, zmq.POLLIN)
        socks = dict(poller.poll(self.connect_timeout_s * 1000))
        if self.zmq_observation_socket not in socks or socks[self.zmq_observation_socket] != zmq.POLLIN:
            raise DeviceNotConnectedError("Timeout waiting for SO101 remote host to connect expired.")

        self._is_connected = True

    def calibrate(self) -> None:
        return None

    def configure(self) -> None:
        return None

    def _poll_and_get_latest_message(self) -> str | None:
        zmq = self._zmq
        poller = zmq.Poller()
        poller.register(self.zmq_observation_socket, zmq.POLLIN)

        try:
            socks = dict(poller.poll(self.polling_timeout_ms))
        except zmq.ZMQError as e:
            logger.error("ZMQ polling error: %s", e)
            return None

        if self.zmq_observation_socket not in socks:
            return None

        last_msg = None
        while True:
            try:
                msg = self.zmq_observation_socket.recv_string(zmq.NOBLOCK)
                last_msg = msg
            except zmq.Again:
                break

        return last_msg

    def _parse_observation_json(self, obs_string: str) -> dict[str, Any] | None:
        try:
            return json.loads(obs_string)
        except json.JSONDecodeError as e:
            logger.error("Error decoding JSON observation: %s", e)
            return None

    def _decode_image_from_b64(self, image_b64: str) -> np.ndarray | None:
        if not image_b64:
            return None
        try:
            jpg_data = base64.b64decode(image_b64)
            np_arr = np.frombuffer(jpg_data, dtype=np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            return frame
        except (TypeError, ValueError) as e:
            logger.error("Error decoding base64 image data: %s", e)
            return None

    def _remote_state_from_obs(self, observation: dict[str, Any]) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        flat_state = {key: float(observation.get(key, 0.0)) for key in JOINT_KEYS}
        state_vec = np.array([flat_state[key] for key in JOINT_KEYS], dtype=np.float32)
        obs_dict: dict[str, Any] = {**flat_state, OBS_STATE: state_vec}

        current_frames: dict[str, np.ndarray] = {}
        for cam_name in self._cameras_ft:
            image_b64 = observation.get(cam_name)
            if image_b64 is None:
                continue
            frame = self._decode_image_from_b64(image_b64)
            if frame is not None:
                current_frames[cam_name] = frame

        return current_frames, obs_dict

    def _get_data(self) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        latest_message_str = self._poll_and_get_latest_message()
        if latest_message_str is None:
            return self.last_frames, self.last_remote_state

        observation = self._parse_observation_json(latest_message_str)
        if observation is None:
            return self.last_frames, self.last_remote_state

        try:
            new_frames, new_state = self._remote_state_from_obs(observation)
        except Exception as e:
            logger.error("Error processing observation data, serving last observation: %s", e)
            return self.last_frames, self.last_remote_state

        self.last_frames = new_frames
        self.last_remote_state = new_state
        return new_frames, new_state

    def get_observation(self) -> dict[str, Any]:
        if not self._is_connected:
            raise DeviceNotConnectedError("SO101Client is not connected. Run `robot.connect()` first.")

        frames, obs_dict = self._get_data()
        for cam_name, frame in frames.items():
            obs_dict[cam_name] = frame
        return obs_dict

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        if not self._is_connected:
            raise DeviceNotConnectedError("SO101Client is not connected. Run `robot.connect()` first.")

        payload = {key: float(action.get(key, 0.0)) for key in JOINT_KEYS}
        self.zmq_cmd_socket.send_string(json.dumps(payload))

        actions = np.array([payload[key] for key in JOINT_KEYS], dtype=np.float32)
        action_sent = {key: actions[i] for i, key in enumerate(JOINT_KEYS)}
        action_sent[ACTION] = actions
        return action_sent

    def send_feedback(self, feedback: dict[str, Any]) -> None:  # noqa: ARG002
        raise NotImplementedError

    def disconnect(self) -> None:
        if not self._is_connected:
            raise DeviceNotConnectedError("SO101Client is not connected. Run `robot.connect()` first.")
        self.zmq_observation_socket.close()
        self.zmq_cmd_socket.close()
        self.zmq_context.term()
        self._is_connected = False

