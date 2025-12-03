"""
Headless keyboard listener for controlling recording via keyboard over SSH.

Usage:
    Run start_recording.sh to launch both panels in tmux.

Controls:
    SPACE        → Start recording / Stop recording (with confirmation)
    Right Arrow  → Save episode and immediately start next (skip reset)
    Left Arrow   → Discard and rerecord current episode
"""

import sys
import tty
import termios
import threading
import time
import select
from pathlib import Path

# IPC files for inter-process communication
CONTROL_FILE = Path("/tmp/lerobot_control")
READY_FILE = Path("/tmp/lerobot_ready")
WAITING_FILE = Path("/tmp/lerobot_waiting")
RECORD_READY_FILE = Path("/tmp/lerobot_record_ready")
SESSION_DONE_FILE = Path("/tmp/lerobot_session_done")
QUIT_FILE = Path("/tmp/lerobot_quit")

ALL_IPC_FILES = [CONTROL_FILE, READY_FILE, WAITING_FILE, RECORD_READY_FILE, SESSION_DONE_FILE, QUIT_FILE]


def cleanup_signal_files():
    """Remove all signal files."""
    for f in ALL_IPC_FILES:
        if f.exists():
            f.unlink()


def send_command(command: str):
    """Send a command to the record.py process via file."""
    CONTROL_FILE.write_text(command)
    print(f"    ✓ Signal sent to recording process")


def read_key():
    """Read a single keypress, handling arrow keys and special keys."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        # Check if input is available (non-blocking)
        if select.select([sys.stdin], [], [], 0.1)[0]:
            ch = sys.stdin.read(1)
            if ch == '\x1b':  # Escape sequence
                # Check for arrow key sequence
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    ch2 = sys.stdin.read(1)
                    if ch2 == '[':
                        if select.select([sys.stdin], [], [], 0.1)[0]:
                            ch3 = sys.stdin.read(1)
                            if ch3 == 'C':  # Right arrow
                                return 'RIGHT'
                            elif ch3 == 'D':  # Left arrow
                                return 'LEFT'
                            elif ch3 == 'A':  # Up arrow
                                return 'UP'
                            elif ch3 == 'B':  # Down arrow
                                return 'DOWN'
                return 'ESC'
            elif ch == ' ':
                return 'SPACE'
            elif ch in ('y', 'Y'):
                return 'Y'
            elif ch in ('n', 'N'):
                return 'N'
            elif ch in ('q', 'Q'):
                return 'Q'
            return ch
    except Exception:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return None


def read_key_blocking():
    """Read a single keypress, blocking until a key is pressed."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == '\x1b':  # Escape sequence
            if select.select([sys.stdin], [], [], 0.1)[0]:
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        ch3 = sys.stdin.read(1)
                        if ch3 == 'C':
                            return 'RIGHT'
                        elif ch3 == 'D':
                            return 'LEFT'
            return 'ESC'
        elif ch == ' ':
            return 'SPACE'
        elif ch in ('y', 'Y'):
            return 'Y'
        elif ch in ('n', 'N'):
            return 'N'
        elif ch in ('q', 'Q'):
            return 'Q'
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def init_headless_keyboard_listener(control_file: Path = CONTROL_FILE):
    """
    Initializes a keyboard listener that watches the control file for commands.
    This runs in record.py and reads commands from the keyboard controller process.
    
    Returns:
        A tuple containing:
        - The listener thread
        - A dictionary of event flags
    """
    events = {
        "exit_early": False,
        "rerecord_episode": False,
        "stop_recording": False,
        "skip_reset": False,
        "quit_program": False,
    }
    
    # Clean up any existing control file
    if control_file.exists():
        control_file.unlink()
    
    def watch_control_file():
        """Watch the control file for commands from the keyboard controller."""
        # Only exit when quit_program is True - keep running across sessions
        while not events["quit_program"]:
            try:
                # Check for quit signal
                if QUIT_FILE.exists():
                    print("\n" + "="*60)
                    print(">>> QUIT SIGNAL RECEIVED - Shutting down...")
                    print("="*60)
                    events["quit_program"] = True
                    events["stop_recording"] = True
                    events["exit_early"] = True
                    QUIT_FILE.unlink()
                    continue
                
                if control_file.exists():
                    command = control_file.read_text().strip().lower()
                    control_file.unlink()
                    
                    if command == "exit":
                        print("\n>>> Command received: exit_early")
                        events["exit_early"] = True
                    elif command == "rerecord":
                        print("\n>>> ← RERECORD: Discarding current episode...")
                        events["rerecord_episode"] = True
                        events["exit_early"] = True
                    elif command == "stop":
                        print("\n>>> ■ STOP: Ending recording session...")
                        events["stop_recording"] = True
                        events["exit_early"] = True
                    elif command == "skip":
                        print("\n>>> → SKIP: Saving and starting next episode...")
                        events["skip_reset"] = True
                        events["exit_early"] = True
            except Exception as e:
                pass
            
            time.sleep(0.05)
    
    listener_thread = threading.Thread(target=watch_control_file, daemon=True)
    listener_thread.start()
    
    return listener_thread, events


def wait_for_ready():
    """
    Wait for the keyboard control session to signal it's ready.
    Called by record.py before starting the recording loop.
    Returns True if ready to record, False if quit was requested.
    """
    # Signal that record.py is ready and waiting
    RECORD_READY_FILE.touch()
    
    print(f"\n{'='*60}")
    print("WAITING FOR KEYBOARD CONTROL SESSION")
    print(f"{'='*60}")
    print("\nWaiting for keyboard controller to connect...")
    
    while not READY_FILE.exists():
        if QUIT_FILE.exists():
            return False
        time.sleep(0.1)
    
    READY_FILE.unlink()
    print("Keyboard controller connected!\n")
    
    # Now wait for SPACE to start recording
    print("Waiting for SPACE to start recording...")
    while not WAITING_FILE.exists():
        if QUIT_FILE.exists():
            return False
        time.sleep(0.1)
    
    WAITING_FILE.unlink()
    if RECORD_READY_FILE.exists():
        RECORD_READY_FILE.unlink()
    print("\n" + "="*60)
    print("▶ RECORDING STARTED")
    print("="*60 + "\n")
    return True


def wait_for_next_session():
    """
    Wait for keyboard controller to signal start of next recording session.
    Returns True if ready to record, False if quit was requested.
    """
    # Signal that we're ready for next session
    SESSION_DONE_FILE.touch()
    
    print(f"\n{'='*60}")
    print("WAITING FOR NEXT RECORDING SESSION")
    print("(Keyboard controller will signal when ready)")
    print(f"{'='*60}\n")
    
    while not WAITING_FILE.exists():
        if QUIT_FILE.exists():
            return False
        time.sleep(0.1)
    
    WAITING_FILE.unlink()
    if SESSION_DONE_FILE.exists():
        SESSION_DONE_FILE.unlink()
    
    print("\n" + "="*60)
    print("▶ RECORDING STARTED")
    print("="*60 + "\n")
    return True


def signal_ready():
    """Signal that the keyboard control session is ready."""
    READY_FILE.touch()


def signal_start():
    """Signal to start recording."""
    WAITING_FILE.touch()


def print_controls():
    """Print the control instructions."""
    print(f"\n{'='*60}")
    print("CONTROLS:")
    print("  SPACE       : Start recording / Stop (with confirmation)")
    print("  → (Right)   : Save episode, skip reset, start next")
    print("  ← (Left)    : Discard and rerecord current episode")
    print("  Q           : Quit entire program")
    print(f"{'='*60}")


if __name__ == "__main__":
    # Standalone keyboard controller mode
    # This process reads keyboard input and sends commands to record.py via files
    
    cleanup_signal_files()
    
    print(f"\n{'='*60}")
    print("KEYBOARD CONTROLLER FOR LEROBOT RECORDING")
    print(f"{'='*60}")
    
    # Wait for record script to be ready
    print("\nWaiting for record.py to initialize...")
    while not RECORD_READY_FILE.exists():
        time.sleep(0.1)
    
    print("✓ Record script is ready!")
    
    # Signal that we're connected
    signal_ready()
    
    print_controls()
    
    # Main session loop - can restart recording multiple times
    session_running = True
    while session_running:
        print("\n" + "-"*60)
        print("Press SPACE to start recording, or Q to quit...")
        print("-"*60)
        
        # Wait for SPACE or Q
        while True:
            key = read_key_blocking()
            if key == 'SPACE':
                break
            elif key == 'Q':
                print("\n>>> Quitting...")
                QUIT_FILE.touch()
                session_running = False
                break
        
        if not session_running:
            break
        
        # Signal to start recording
        signal_start()
        print("\n" + "="*60)
        print("▶ RECORDING IN PROGRESS")
        print("="*60)
        print("\n  → (Right) : Save & next episode")
        print("  ← (Left)  : Rerecord episode")
        print("  SPACE     : Stop recording")
        print("  Q         : Quit program\n")
        
        # Recording control loop
        recording = True
        while recording:
            key = read_key()
            if key:
                if key == 'RIGHT':
                    print("\n>>> → SKIP: Saving episode, starting next...")
                    send_command("skip")
                elif key == 'LEFT':
                    print("\n>>> ← RERECORD: Discarding episode...")
                    send_command("rerecord")
                elif key == 'Q':
                    print("\n>>> Q: Quit requested")
                    print("    Are you sure you want to quit? (y/n): ", end='', flush=True)
                    while True:
                        confirm = read_key_blocking()
                        if confirm == 'Y':
                            print("y")
                            print("    Quitting...")
                            QUIT_FILE.touch()
                            recording = False
                            session_running = False
                            break
                        elif confirm == 'N':
                            print("n")
                            print("    Continuing...")
                            break
                elif key == 'SPACE':
                    print("\n>>> ■ STOP: Stop recording requested")
                    print("    Do you want to stop this session? (y/n): ", end='', flush=True)
                    while True:
                        confirm = read_key_blocking()
                        if confirm == 'Y':
                            print("y")
                            print("    Stopping session...")
                            send_command("stop")
                            recording = False
                            break
                        elif confirm == 'N':
                            print("n")
                            print("    Continuing recording...")
                            break
            
            time.sleep(0.05)
        
        if not session_running:
            break
        
        # Wait for session to complete (upload, etc.)
        print("\n" + "="*60)
        print("SESSION ENDED - Waiting for upload to complete...")
        print("="*60)
        
        # Wait for record.py to signal it's ready for next session
        while not SESSION_DONE_FILE.exists() and not QUIT_FILE.exists():
            time.sleep(0.1)
        
        if QUIT_FILE.exists():
            break
        
        if SESSION_DONE_FILE.exists():
            SESSION_DONE_FILE.unlink()
            print("\n✓ Session complete! Ready for next recording.")
    
    print("\n" + "="*60)
    print("KEYBOARD CONTROLLER EXITING")
    print("="*60)
    print("\nGoodbye!")
    time.sleep(0.5)
