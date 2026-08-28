from lerobot.robots.so101_follower import SO101Follower, SO101FollowerConfig
from robot_config import FOLLOWER_PORT, LEADER_PORT 
from lerobot.teleoperators.so101_leader import SO101Leader, SO101LeaderConfig

# config = SO101FollowerConfig(
#     port=FOLLOWER_PORT,
#     id="my_follower_arm",
# )

# follower = SO101Follower(config)
# follower.connect(calibrate=False)
# follower.calibrate()
# follower.disconnect()

config = SO101LeaderConfig(
    port=LEADER_PORT,
    id="my_leader_arm",
)

leader = SO101Leader(config)
leader.connect(calibrate=False)
leader.calibrate()
leader.disconnect()