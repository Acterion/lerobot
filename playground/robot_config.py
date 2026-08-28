"""
Robot and dataset configuration for SO101 recording and training.

This file contains all setup-dependent configuration that should be shared
between recording, training, and inference scripts.
"""

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig


# =============================================================================
# DATASET CONFIGURATION
# =============================================================================

# Dataset identification
DATASET_NAME = "purple_marker_to_grey_box-1"
POLICY_NAME = "policy_purple_marker_to_grey_box-1"
HUGGINGFACE_USER = "Acterion"

# Task description (used for training and inference)
TASK_DESCRIPTION = "Grab purple marker and move it to the grey box."

# Recording framerate (must match between recording and training)
FPS = 30


# =============================================================================
# HARDWARE CONFIGURATION
# =============================================================================

# Robot serial ports
FOLLOWER_PORT = "/dev/ttyACM1"
LEADER_PORT = "/dev/ttyACM0"

# Robot type identifier
ROBOT_TYPE = "so101"


# =============================================================================
# CAMERA CONFIGURATION
# =============================================================================

# Camera resolution and framerate
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = FPS

# Camera device indices
CAMERA_INDICES = {
    "camera1": 2,  # wrist camera
    "camera2": 0,  # top camera
}

# Camera configurations (used for recording)
CAMERAS = {
    "camera1": OpenCVCameraConfig(
        index_or_path=CAMERA_INDICES["camera1"],
        fps=CAMERA_FPS,
        width=CAMERA_WIDTH,
        height=CAMERA_HEIGHT,
        exposure=-6
    ),
    "camera2": OpenCVCameraConfig(
        index_or_path=CAMERA_INDICES["camera2"],
        fps=CAMERA_FPS,
        width=CAMERA_WIDTH,
        height=CAMERA_HEIGHT,
        exposure=0.33
    ),
}


# =============================================================================
# RECORDING CONFIGURATION
# =============================================================================

# Episode settings
NUM_EPISODES = 10          # Max episodes per session (0 = unlimited)
EPISODE_TIME_SEC = 30      # Duration of each episode in seconds
RESET_TIME_SEC = 10        # Duration of reset phase between episodes in seconds

# Batch encoding: defer video encoding to end of session for faster recording
# Set to 1 for immediate encoding, or higher to batch (100 = effectively all at once)
BATCH_ENCODING_SIZE = 100

# Image writer threads (for async image saving during recording)
IMAGE_WRITER_THREADS = 4


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_repo_id() -> str:
    """Get the full HuggingFace dataset repository ID."""
    return f"{HUGGINGFACE_USER}/{DATASET_NAME}"


def get_camera_keys() -> list[str]:
    """Get list of camera keys."""
    return list(CAMERAS.keys())


def get_image_features() -> dict[str, tuple[int, int]]:
    """Get image feature dimensions for each camera."""
    return {key: (CAMERA_HEIGHT, CAMERA_WIDTH) for key in CAMERAS.keys()}
