# Remote SO-101 Teleoperation Bridge

This guide explains how to stream commands from a leader SO-101 hand to a follower arm that is connected to a remote computer (e.g. a Raspberry Pi) using the new ZeroMQ-based bridge.

## 1. Prerequisites
- Both computers share the same Git revision (this fork) and have the LeRobot dependencies installed.
- The follower side can reach the SO-101 hardware over USB and any cameras you want to stream.
- Ports `6000` (commands) and `6001` (observations) are open between the two machines, or adjust them in the commands below.

> Replace `/dev/ttyUSB0` and camera configs with the actual serial device and camera layout you use.

## 2. Start the follower host (Raspberry Pi)
Run this where the physical SO-101 arm is connected:

```bash
python -m lerobot.robots.so101_client.so101_host \
  --robot.type=so101_follower \
  --robot.port=/dev/ttyUSB0 \
  --robot.cameras='{ front: {type: opencv, index_or_path: 0, width: 1920, height: 1080, fps: 30} }' \
  --host.port_zmq_cmd=6000 \
  --host.port_zmq_observations=6001 \
  --host.max_loop_freq_hz=60
```

- The host connects to the follower arm, listens for joint commands on `port_zmq_cmd`, and publishes joint states + JPEG-compressed camera frames on `port_zmq_observations`.
- The process runs until you terminate it (Ctrl+C). Use `--host.connection_time_s` if you want an automatic timeout.

## 3. Launch the leader teleoperation client (remote workstation)
On the machine with the leader hand:

```bash
lerobot-teleoperate \
  --robot.type=so101_client \
  --robot.remote_ip=<FOLLOWER_IP> \
  --robot.port_zmq_cmd=6000 \
  --robot.port_zmq_observations=6001 \
  --robot.cameras="{ front: {type: opencv, index_or_path: 0, width: 1920, height: 1080, fps: 30} }" \
  --robot.id=remote_follower \
  --teleop.type=so101_leader \
  --teleop.port=/dev/tty.usbmodemXXXX \
  --teleop.id=leader \
  --display_data=true
```

- `remote_ip` must be reachable (use the Raspberry Pi IP).
- The teleop loop streams leader commands to the host and displays the follower cameras when `--display_data=true`.
- You can adjust `--robot.cameras` to match the camera layout exported by the host.

## 4. Calibration & Safety
- Run the usual SO-101 calibration workflows on both leader and follower as needed before starting teleoperation.
- The host watchdog logs a warning if no command is received for 500 ms; the arm holds its last goal. Tune via `--host.watchdog_timeout_ms`.
- Cameras are JPEG-compressed at quality 90 by default. Lower quality or frame rate if bandwidth is limited (`--host.jpeg_quality`, `--host.max_loop_freq_hz`).

## 5. Troubleshooting
- If the teleop client times out on connect, confirm the host process is running and the ports/IP are reachable (e.g. `ping`, `nc -vz`).
- To inspect the raw stream, disable conflation by editing the client/host configs, but expect higher latency.
- Logs from both processes are verbose; use `LOG_LEVEL=DEBUG` to surface transport issues.

