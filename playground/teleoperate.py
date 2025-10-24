from lerobot.teleoperators.so101_leader import SO101LeaderConfig, SO101Leader
from lerobot.robots.so101_follower import SO101FollowerConfig, SO101Follower

robot_config = SO101FollowerConfig(
    port="/dev/tty.usbmodem59700728871",
    # port="/dev/tty.usbmodem59700736791",
    id="k_arm_v5",
)

teleop_config = SO101LeaderConfig(
    port="/dev/tty.usbmodem59700721491",
    # port="/dev/tty.usbmodem59710814551",
    id="k_arm_v5_leader",
)

robot = SO101Follower(robot_config)
teleop_device = SO101Leader(teleop_config)
robot.connect()
teleop_device.connect()

while True:
    action = teleop_device.get_action()
    robot.send_action(action)
