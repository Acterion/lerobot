#!/usr/bin/env python3
"""
Play a trained policy on the robot.

This script runs a trained policy on the robot, recording episodes to evaluate
the policy's performance. It uses the same robot and camera configuration as
the recording script.

Usage:
    python play_trained_policy.py --policy-path <path_or_repo_id>
    
Example:
    python play_trained_policy.py --policy-path Acterion/my-trained-policy
    python play_trained_policy.py --policy-path ./outputs/train/my-policy
"""

import argparse
import os
from pathlib import Path

from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.datasets.utils import hw_to_dataset_features
from lerobot.policies.factory import make_pre_post_processors
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
from lerobot.processor import make_default_processors
from lerobot.robots.so101_follower import SO101Follower, SO101FollowerConfig
from lerobot.scripts.lerobot_record import record_loop
from lerobot.utils.control_utils import init_keyboard_listener, is_headless

# Import configuration
from robot_config import (
    CAMERAS,
    EPISODE_TIME_SEC,
    FOLLOWER_PORT,
    FPS,
    HUGGINGFACE_USER,
    RESET_TIME_SEC,
    TASK_DESCRIPTION,
    NUM_EPISODES,
    POLICY_NAME,
    HUGGINGFACE_USER,
)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Play a trained policy on the robot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Play a policy from HuggingFace Hub
  %(prog)s --policy-path Acterion/my-trained-policy
  
  # Play a local policy checkpoint
  %(prog)s --policy-path ./outputs/train/my-policy
  
  # Record to a custom evaluation dataset
  %(prog)s --policy-path Acterion/my-policy --eval-dataset-name my-eval-test
  
  # Run more episodes
  %(prog)s --policy-path Acterion/my-policy --num-episodes 20
        """
    )
    
    parser.add_argument(
        "--policy-path",
        type=str,
        default=f"{HUGGINGFACE_USER}/{POLICY_NAME}",
        help="Path to trained policy (HuggingFace repo ID or local directory)"
    )
    
    parser.add_argument(
        "--eval-dataset-name",
        type=str,
        default=None,
        help="Name for evaluation dataset (default: eval_<model_name>_test)"
    )
    
    parser.add_argument(
        "--num-episodes",
        type=int,
        default=NUM_EPISODES,
        help=f"Number of episodes to record (default: {NUM_EPISODES})"
    )
    
    parser.add_argument(
        "--episode-time",
        type=int,
        default=EPISODE_TIME_SEC,
        help=f"Duration of each episode in seconds (default: {EPISODE_TIME_SEC})"
    )
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    # Determine evaluation dataset name
    if args.eval_dataset_name:
        eval_dataset_name = args.eval_dataset_name
    else:
        # Extract model name from policy path
        model_name = Path(args.policy_path).name
        eval_dataset_name = f"eval_{model_name}_test"
    
    print("=" * 60)
    print("POLICY EVALUATION")
    print("=" * 60)
    print(f"Policy path:      {args.policy_path}")
    print(f"Eval dataset:     {HUGGINGFACE_USER}/{eval_dataset_name}")
    print(f"Task:             {TASK_DESCRIPTION}")
    print(f"Episodes:         {args.num_episodes}")
    print(f"Episode duration: {args.episode_time}s")
    print("=" * 60 + "\n")
    
    # Initialize robot
    print("Initializing robot...")
    robot = SO101Follower(
        SO101FollowerConfig(
            port=FOLLOWER_PORT,
            id="my_follower_arm",
            cameras=CAMERAS,
        )
    )
    
    # Connect robot
    print("Connecting to robot...")
    robot.connect()
    
    if not robot.is_connected:
        raise ValueError("Robot is not connected!")
    
    # Create evaluation dataset
    print("Creating evaluation dataset...")
    action_features = hw_to_dataset_features(robot.action_features, "action")
    obs_features = hw_to_dataset_features(robot.observation_features, "observation")
    
    dataset = LeRobotDataset.create(
        repo_id=f"{HUGGINGFACE_USER}/{eval_dataset_name}",
        features={**action_features, **obs_features},
        fps=FPS,
        robot_type=robot.name,
        use_videos=True,
        image_writer_threads=4,
    )
    
    # Load policy
    print(f"Loading policy from {args.policy_path}...")
    policy = SmolVLAPolicy.from_pretrained(args.policy_path)
    
    # Build preprocessor and postprocessor
    print("Creating policy processors...")
    preprocessor, postprocessor = make_pre_post_processors(
        policy_cfg=policy.config,
        pretrained_path=args.policy_path,
        dataset_stats=dataset.meta.stats,
        # Ensure device compatibility with detected hardware
        preprocessor_overrides={"device_processor": {"device": str(policy.config.device)}},
    )
    
    # Initialize processors
    teleop_action_processor, robot_action_processor, robot_observation_processor = make_default_processors()
    
    # Initialize keyboard listener
    if is_headless():
        print("Warning: Running in headless mode - limited keyboard control")
        events = {"stop_recording": False, "exit_early": False, "rerecord_episode": False}
    else:
        listener, events = init_keyboard_listener()
    
    print("Starting evaluation loop...")
    
    # Main evaluation loop
    try:
        episode_idx = 0
        while episode_idx < args.num_episodes:
            print(f"Running inference, recording eval episode {episode_idx + 1} of {args.num_episodes}")
            
            # Record episode with policy
            record_loop(
                robot=robot,
                events=events,
                fps=FPS,
                policy=policy,
                preprocessor=preprocessor,
                postprocessor=postprocessor,
                teleop_action_processor=teleop_action_processor,
                robot_action_processor=robot_action_processor,
                robot_observation_processor=robot_observation_processor,
                teleop=None,  # No teleop, using policy
                dataset=dataset,
                control_time_s=args.episode_time,
                single_task=TASK_DESCRIPTION,
                display_data=True,
            )
            
            # Handle rerecord request
            if events.get("rerecord_episode", False):
                print("Re-recording episode")
                events["rerecord_episode"] = False
                events["exit_early"] = False
                dataset.clear_episode_buffer()
                continue
            
            # Handle stop request
            if events.get("stop_recording", False) or events.get("exit_early", False):
                print("Stopping evaluation early...")
                break
            
            # Save episode
            print(f"Saving episode {episode_idx + 1}...")
            dataset.save_episode()
            episode_idx += 1
            
            # Reset phase between episodes (if not last episode)
            if episode_idx < args.num_episodes and not events.get("stop_recording", False):
                print("Reset the environment")
                record_loop(
                    robot=robot,
                    events=events,
                    fps=FPS,
                    teleop_action_processor=teleop_action_processor,
                    robot_action_processor=robot_action_processor,
                    robot_observation_processor=robot_observation_processor,
                    control_time_s=RESET_TIME_SEC,
                    single_task=TASK_DESCRIPTION,
                    display_data=True,
                )
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    
    finally:
        # Cleanup
        print("Stopping recording...")
        robot.disconnect()
        
        if not is_headless():
            listener.stop()
        
        print("Finalizing dataset...")
        dataset.finalize()
        
        print("Uploading to HuggingFace...")
        dataset.push_to_hub()
        
        print("\n" + "=" * 60)
        print("EVALUATION COMPLETE")
        print(f"Recorded {episode_idx} episodes")
        print(f"Dataset: {HUGGINGFACE_USER}/{eval_dataset_name}")
        print("=" * 60)


if __name__ == "__main__":
    main()
