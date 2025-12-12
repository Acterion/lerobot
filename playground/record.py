"""
Recording script for SO101 robot with headless SSH keyboard control.

Controls:
    SPACE  - Start/stop recording (with confirmation)
    ←      - Discard current episode and rerecord
    →      - Skip reset phase, start next episode immediately
    Q      - Quit program

Usage:
    1. Run this script on the robot (left tmux pane)
    2. Run headless_keyboard.py in another SSH session (right tmux pane)
    3. Or use start_recording.sh to launch both in tmux
"""

import os
import shutil
from pathlib import Path

from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.datasets.utils import hw_to_dataset_features, load_episodes
from lerobot.processor import make_default_processors
from lerobot.robots.so101_follower import SO101Follower, SO101FollowerConfig
from lerobot.scripts.lerobot_record import record_loop
from lerobot.teleoperators.so101_leader import SO101Leader, SO101LeaderConfig
from lerobot.utils.control_utils import init_keyboard_listener, is_headless

from headless_keyboard import (
    cleanup_signal_files,
    init_headless_keyboard_listener,
    wait_for_next_session,
    wait_for_ready,
)

# Import configuration from shared config file
from robot_config import (
    BATCH_ENCODING_SIZE,
    CAMERAS,
    DATASET_NAME,
    EPISODE_TIME_SEC,
    FOLLOWER_PORT,
    FPS,
    HUGGINGFACE_USER,
    IMAGE_WRITER_THREADS,
    LEADER_PORT,
    NUM_EPISODES,
    RESET_TIME_SEC,
    ROBOT_TYPE,
    TASK_DESCRIPTION,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def print_header(text: str, char: str = "=", width: int = 60):
    """Print a formatted header."""
    print(f"\n{char * width}")
    print(text)
    print(f"{char * width}\n")


def print_session_header(session_num: int):
    """Print session start header."""
    print(f"\n{'#' * 60}")
    print(f"SESSION {session_num}")
    print(f"{'#' * 60}")


def encode_and_upload(dataset, total_episodes: int):
    """Encode remaining videos and upload dataset to HuggingFace."""
    if total_episodes == 0:
        print("No episodes recorded, skipping upload.")
        return

    print("Encoding remaining videos and uploading dataset to HuggingFace...")

    # Flush remaining unencoded videos if using batched encoding
    if dataset.episodes_since_last_encoding > 0:
        start_ep = dataset.num_episodes - dataset.episodes_since_last_encoding
        end_ep = dataset.num_episodes
        print(f"Encoding {dataset.episodes_since_last_encoding} remaining episodes "
              f"(episodes {start_ep} to {end_ep - 1})...")

        # Flush metadata writer so episodes parquet files are written to disk
        dataset.meta._close_writer()

        # Reload episodes metadata from disk before batch encoding
        dataset.meta.episodes = load_episodes(dataset.root)
        dataset._batch_save_episode_video(start_ep, end_ep)
        dataset.episodes_since_last_encoding = 0

    dataset.finalize()
    dataset.push_to_hub()
    print("✓ Upload complete!")


def cleanup_and_exit(robot, teleop, total_sessions: int, total_episodes: int):
    """Clean up resources and exit."""
    print_header(f"RECORDING PROGRAM COMPLETE\n"
                 f"Total sessions: {total_sessions}\n"
                 f"Total episodes recorded: {total_episodes}")

    robot.disconnect()
    teleop.disconnect()
    cleanup_signal_files()

    # Force clean exit to avoid PyArrow shutdown crash
    os._exit(0)


# =============================================================================
# INITIALIZATION
# =============================================================================

# Clear existing dataset cache
dataset_path = Path.home() / ".cache" / "huggingface" / "lerobot" / HUGGINGFACE_USER / DATASET_NAME
if dataset_path.exists():
    shutil.rmtree(dataset_path)

# Initialize robot
robot = SO101Follower(
    SO101FollowerConfig(
        port=FOLLOWER_PORT,
        id="my_follower_arm",
        cameras=CAMERAS,
    )
)

# Initialize teleoperator (leader arm)
teleop = SO101Leader(
    SO101LeaderConfig(
        port=LEADER_PORT,
        id="my_leader_arm",
    )
)

# Create dataset with features from robot
action_features = hw_to_dataset_features(robot.action_features, "action")
obs_features = hw_to_dataset_features(robot.observation_features, "observation")

dataset = LeRobotDataset.create(
    repo_id=f"{HUGGINGFACE_USER}/{DATASET_NAME}",
    features={**action_features, **obs_features},
    fps=FPS,
    robot_type=robot.name,
    use_videos=True,
    image_writer_threads=4,
    batch_encoding_size=BATCH_ENCODING_SIZE,
)

# Connect hardware
robot.connect()
teleop.connect()

# Initialize processors
teleop_action_processor, robot_action_processor, robot_observation_processor = make_default_processors()

# Clean up any old IPC files
cleanup_signal_files()

# Initialize keyboard listener
if is_headless():
    if not wait_for_ready():
        print("Quit requested before recording started.")
        robot.disconnect()
        teleop.disconnect()
        os._exit(0)
    _, events = init_headless_keyboard_listener()
else:
    _, events = init_keyboard_listener()
    events["quit_program"] = False


# =============================================================================
# MAIN RECORDING LOOP
# =============================================================================

total_episodes = 0
session_num = 0

while not events.get("quit_program", False):
    session_num += 1
    episode_idx = 0
    events["stop_recording"] = False

    print_session_header(session_num)

    # --- Episode recording loop ---
    while (not events["stop_recording"]
           and not events.get("quit_program", False)
           and (NUM_EPISODES == 0 or episode_idx < NUM_EPISODES)):

        print_header(f"RECORDING EPISODE {episode_idx + 1} (Session {session_num})")

        # Record episode
        record_loop(
            robot=robot,
            events=events,
            fps=FPS,
            teleop_action_processor=teleop_action_processor,
            robot_action_processor=robot_action_processor,
            robot_observation_processor=robot_observation_processor,
            teleop=teleop,
            dataset=dataset,
            control_time_s=EPISODE_TIME_SEC,
            single_task=TASK_DESCRIPTION,
            display_data=True,
        )

        # Handle rerecord request
        if events["rerecord_episode"]:
            print("\n>>> ← Discarding episode and rerecording...")
            events["rerecord_episode"] = False
            events["exit_early"] = False
            dataset.clear_episode_buffer()
            continue

        # Handle stop/quit request
        if events["stop_recording"] or events.get("quit_program", False):
            print("\n>>> ■ Stopping recording session...")
            break

        # Save episode
        print(f"\n>>> ✓ Saving episode {episode_idx + 1}...")
        dataset.save_episode()
        episode_idx += 1
        total_episodes += 1
        print(f">>> Episode saved! Session episodes: {episode_idx}, Total: {total_episodes}")

        # Handle skip reset request
        if events.get("skip_reset", False):
            print(">>> → Skipping reset, starting next episode immediately...")
            events["skip_reset"] = False
            events["exit_early"] = False
            continue

        # --- Reset phase ---
        if not events["stop_recording"] and not events.get("quit_program", False):
            print_header("RESET PHASE - Prepare for next episode\n"
                        "Press → to skip reset and start recording")

            events["exit_early"] = False
            record_loop(
                robot=robot,
                events=events,
                fps=FPS,
                teleop_action_processor=teleop_action_processor,
                robot_action_processor=robot_action_processor,
                robot_observation_processor=robot_observation_processor,
                teleop=teleop,
                control_time_s=RESET_TIME_SEC,
                single_task=TASK_DESCRIPTION,
                display_data=True,
            )
            events["exit_early"] = False

    # --- End of session ---
    if not events.get("quit_program", False):
        print_header(f"SESSION {session_num} COMPLETE\n"
                    f"Episodes this session: {episode_idx}\n"
                    f"Total episodes: {total_episodes}")

        encode_and_upload(dataset, total_episodes)

        # Wait for next session or quit
        if is_headless():
            if not wait_for_next_session():
                events["quit_program"] = True
            else:
                events["stop_recording"] = False
                events["exit_early"] = False


# =============================================================================
# CLEANUP
# =============================================================================

cleanup_and_exit(robot, teleop, session_num, total_episodes)