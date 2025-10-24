from lerobot.robots.so101_follower import SO101FollowerConfig, SO101Follower
from lerobot.teleoperators.so101_leader import SO101LeaderConfig, SO101Leader

config = SO101FollowerConfig(
    port="/dev/tty.usbmodem59700728871",
    id="my_arm_v5",
)

follower = SO101Follower(config)
follower.connect(calibrate=False)
follower.calibrate()

follower.disconnect()


# config = SO101LeaderConfig(
#     port="/dev/tty.usbmodem59700721491",
#     id="my_arm_v5_leader",
# )

leader = SO101Leader(config)
leader.connect(calibrate=False)
leader.calibrate()
leader.disconnect()
