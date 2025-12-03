import time
import rerun as rr
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.robots.so101_follower import SO101Follower, SO101FollowerConfig
from lerobot.utils.visualization_utils import log_rerun_data
from lerobot.processor import make_default_processors

# Initialize Robot
robot = SO101Follower(
    SO101FollowerConfig(
        port="/dev/serial/by-id/usb-1a86_USB_Single_Serial_5971081397-if00",
        id="my_follower_arm",
        cameras={
            "wrist": OpenCVCameraConfig(index_or_path=2, fps=30, width=640, height=480),
            "top": OpenCVCameraConfig(index_or_path=0, fps=30, width=640, height=480),
        },
    )
)

print("Connecting to robot...")
robot.connect()
print("Connected!")

# Initialize Processors
_, _, robot_observation_processor = make_default_processors()

# Initialize Rerun
print("Initializing Rerun...")
rr.init("test_visualization")
# serve_web starts the web server and the websocket server
# open_browser=False is important for headless
rr.serve_web(open_browser=False, server_memory_limit="1GB")

print("Rerun visualization started.")
print("Please check the logs above for the correct URL.")
print("Typically it is http://<ip>:9090")

try:
    while True:
        obs = robot.get_observation()
        obs_processed = robot_observation_processor(obs)
        log_rerun_data(observation=obs_processed)
        time.sleep(0.03) # ~30 FPS
except KeyboardInterrupt:
    print("Stopping...")
    robot.disconnect()
