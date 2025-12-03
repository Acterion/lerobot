from pathlib import Path

import rerun as rr
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.robots.so101_follower import SO101Follower, SO101FollowerConfig
from lerobot.teleoperators.so101_leader import SO101Leader, SO101LeaderConfig
from lerobot.scripts.lerobot_record import DatasetRecordConfig, RecordConfig, record as record_dataset, record_loop
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.utils.control_utils import init_keyboard_listener, is_headless
from lerobot.utils.visualization_utils import init_rerun
from headless_keyboard import init_headless_keyboard_listener, wait_for_ready, wait_for_next_session, cleanup_signal_files, QUIT_FILE
from lerobot.utils.utils import log_say
from lerobot.datasets.utils import hw_to_dataset_features, load_episodes
from lerobot.processor import make_default_processors

NUM_EPISODES = 2  # Maximum episodes per session (set to 0 for unlimited)
FPS = 30
EPISODE_TIME_SEC = 30
RESET_TIME_SEC = 10
TASK_DESCRIPTION = "Grab purple marker and move it to the grey box."
DATASET_NAME = "purple_marker_to_grey_box-1"
# check if .cache/huggingface/lerobot/Acterion/my-test-dataset exists
# if yes, delete it to avoid issues with dataset creation
dataset_path = Path.home() / ".cache" / "huggingface" / "lerobot" / "Acterion" / DATASET_NAME
if dataset_path.exists():
    import shutil

    shutil.rmtree(dataset_path)


robot = SO101Follower(
    SO101FollowerConfig(
        port="/dev/serial/by-id/usb-1a86_USB_Single_Serial_5971081397-if00",
        id="my_follower_arm",
        cameras={
            "camera1": OpenCVCameraConfig(index_or_path=2, fps=30, width=640, height=480),  # wrist camera
            "camera2": OpenCVCameraConfig(index_or_path=0, fps=30, width=640, height=480),  # top camera
        },
    )
)

teleop = SO101Leader(
    SO101LeaderConfig(
        port="/dev/serial/by-id/usb-1a86_USB_Single_Serial_5970072149-if00",
        id="my_leader_arm",
    )
)

action_features = hw_to_dataset_features(robot.action_features, "action")
obs_features = hw_to_dataset_features(robot.observation_features, "observation")
dataset_features = {**action_features, **obs_features}

# Use batch_encoding_size > 1 to defer video encoding to the end of session
# This avoids 1.5 min post-processing per episode - all videos are encoded at once at the end
# Set to 0 or a large number to encode ALL at once when finalize() is called
# Or set to NUM_EPISODES to batch per session
BATCH_ENCODING_SIZE = 100  # Defer encoding - will encode on finalize()

dataset=LeRobotDataset.create(
            repo_id="Acterion/" + DATASET_NAME,
            features=dataset_features,
            fps=FPS,
            robot_type=robot.name,
            use_videos=True,
            image_writer_threads=4,
            batch_encoding_size=BATCH_ENCODING_SIZE,
        )

robot.connect()
teleop.connect()

teleop_action_processor, robot_action_processor, robot_observation_processor = make_default_processors()

# Clean up any old IPC files
cleanup_signal_files()

# Use headless keyboard listener if in headless mode, otherwise use pynput
if is_headless():
    # Wait for keyboard control session to connect
    if not wait_for_ready():
        print("Quit requested before recording started.")
        robot.disconnect()
        teleop.disconnect()
        import os
        os._exit(0)
    _, events = init_headless_keyboard_listener()
else:
    _, events = init_keyboard_listener()
    events["quit_program"] = False  # Add quit_program for non-headless mode
# init_rerun(session_name="recording")
# rr.init("recording", spawn=False)
# server_uri = rr.serve_grpc()
# rr.serve_web_viewer(connect_to=server_uri, open_browser=False)

# print("Go to http://172.22.2.1/?url=rerun%2Bhttp%3A%2F%2F172.22.1.2%3A9876%2Fproxy")
# print("Or run rerun --connect rerun+http://172.22.1.2:9876/proxy in another terminal")

# Main recording loop - supports multiple sessions
total_episodes = 0
session_num = 0

while not events.get("quit_program", False):
    session_num += 1
    episode_idx = 0
    events["stop_recording"] = False
    
    print(f"\n{'#'*60}")
    print(f"SESSION {session_num}")
    print(f"{'#'*60}")
    
    # Recording loop for this session
    while not events["stop_recording"] and not events.get("quit_program", False) and (NUM_EPISODES == 0 or episode_idx < NUM_EPISODES):
        print(f"\n{'='*60}")
        print(f"RECORDING EPISODE {episode_idx + 1} (Session {session_num})")
        print(f"{'='*60}\n")

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

        # Check if we should rerecord
        if events["rerecord_episode"]:
            print("\n>>> ← Discarding episode and rerecording...")
            events["rerecord_episode"] = False
            events["exit_early"] = False
            dataset.clear_episode_buffer()
            continue

        # Check if we should stop or quit
        if events["stop_recording"] or events.get("quit_program", False):
            print("\n>>> ■ Stopping recording session...")
            break

        # Save the episode
        print(f"\n>>> ✓ Saving episode {episode_idx + 1}...")
        dataset.save_episode()
        episode_idx += 1
        total_episodes += 1
        print(f">>> Episode saved! Session episodes: {episode_idx}, Total: {total_episodes}")

        # Check if we should skip reset (Right arrow was pressed)
        if events.get("skip_reset", False):
            print(">>> → Skipping reset, starting next episode immediately...")
            events["skip_reset"] = False
            events["exit_early"] = False
            continue

        # Reset phase (if not skipping)
        if not events["stop_recording"] and not events.get("quit_program", False):
            print(f"\n{'='*60}")
            print("RESET PHASE - Prepare for next episode")
            print("Press → to skip reset and start recording")
            print(f"{'='*60}\n")
            
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

    # End of session - upload and wait for next session or quit
    if not events.get("quit_program", False):
        print("\n" + "="*60)
        print(f"SESSION {session_num} COMPLETE")
        print(f"Episodes this session: {episode_idx}")
        print(f"Total episodes: {total_episodes}")
        print("="*60 + "\n")
        
        if total_episodes > 0:
            print("Encoding remaining videos and uploading dataset to HuggingFace...")
            # Flush remaining unencoded videos if using batched encoding
            if dataset.episodes_since_last_encoding > 0:
                start_ep = dataset.num_episodes - dataset.episodes_since_last_encoding
                print(f"Encoding {dataset.episodes_since_last_encoding} remaining episodes (episodes {start_ep} to {dataset.num_episodes - 1})...")
                # Flush metadata writer so episodes parquet files are written to disk
                dataset.meta._close_writer()
                # Reload episodes metadata from disk before batch encoding
                dataset.meta.episodes = load_episodes(dataset.root)
                dataset._batch_save_episode_video(start_ep, dataset.num_episodes)
                dataset.episodes_since_last_encoding = 0
            dataset.finalize()
            dataset.push_to_hub()
            print("✓ Upload complete!")
        else:
            print("No episodes recorded this session.")
        
        # Wait for next session or quit
        if is_headless():
            if not wait_for_next_session():
                events["quit_program"] = True
            else:
                # Reset events for new session
                events["stop_recording"] = False
                events["exit_early"] = False

# Clean up
print("\n" + "="*60)
print("RECORDING PROGRAM COMPLETE")
print(f"Total sessions: {session_num}")
print(f"Total episodes recorded: {total_episodes}")
print("="*60 + "\n")

robot.disconnect()
teleop.disconnect()

# Finalize dataset to properly close parquet writers
print("Finalizing dataset...")
# Flush remaining unencoded videos if using batched encoding
if dataset.episodes_since_last_encoding > 0:
    start_ep = dataset.num_episodes - dataset.episodes_since_last_encoding
    print(f"Encoding {dataset.episodes_since_last_encoding} remaining episodes (episodes {start_ep} to {dataset.num_episodes - 1})...")
    # Flush metadata writer so episodes parquet files are written to disk
    dataset.meta._close_writer()
    # Reload episodes metadata from disk before batch encoding
    dataset.meta.episodes = load_episodes(dataset.root)
    dataset._batch_save_episode_video(start_ep, dataset.num_episodes)
    dataset.episodes_since_last_encoding = 0
dataset.finalize()
print("✓ Dataset finalized!")

# Final upload if there are unsaved episodes
if total_episodes > 0 and not events.get("quit_program", False):
    print("Final upload to HuggingFace...")
    dataset.push_to_hub()
    print("\u2713 Upload complete!")
elif total_episodes == 0:
    print("No episodes recorded, skipping upload.")

# Clean up IPC files
cleanup_signal_files()

# Force clean exit to avoid PyArrow shutdown crash
import os
os._exit(0)