#!/bin/bash
# Play a trained policy in the lerobot playground
# Usage: ./play_trained_policy.sh


lerobot-record \
  --robot.type=so101_follower \
  --robot.port=/dev/serial/by-id/usb-1a86_USB_Single_Serial_5970072149-if00 \
  --robot.id=my_follower_arm \
  --robot.cameras="{ camera2: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, camera1: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30}}" \
  --dataset.single_task="Grab purple marker and move it to the grey box." \
  --dataset.repo_id=Acterion/eval_purple_marker_to_grey_box_test-1 \
  --dataset.episode_time_s=50 \
  --dataset.num_episodes=10 \
  --policy.path=Acterion/policy_purple_marker_to_grey_box-1
  # <- Teleop optional if you want to teleoperate in between episodes \
  # --teleop.type=so100_leader \
  # --teleop.port=/dev/ttyACM0 \
  # --teleop.id=my_red_leader_arm \