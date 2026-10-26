"""Bridge ROS Twist commands to the RM27 UART navigation protocol.

The firmware protocol is fixed at 17 bytes:
FA FB 21 0D | float32 vx | float32 vy | float32 wz | uint8 spin_mode

ROS uses +Y to the left, while the firmware protocol uses +Y to the right,
so the lateral velocity is negated before transmission.
"""

from __future__ import annotations

import math
import os
import struct
import termios
import time
from typing import Optional, Tuple

import rclpy
from geometry_msgs.msg import Twist, TwistStamped
from rclpy.node import Node


COMMAND_HEADER = b"\xfa\xfb\x21\x0d"
FEEDBACK_HEADER = b"\xfa\xfb\x42\x0c"
COMMAND_LENGTH = 17
FEEDBACK_LENGTH = 16



def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


class ChassisSerialBridge(Node):
    """Send fresh navigation commands and expose actual chassis velocity."""

    def __init__(self) -> None:
        super().__init__("chassis_serial_bridge")

        self.declare_parameter("port", "/dev/ttyACM0")
        self.declare_parameter("baudrate", 1152000)
        self.declare_parameter("command_topic", "cmd_vel")
        self.declare_parameter("feedback_topic", "chassis/actual_velocity")
        self.declare_parameter("feedback_frame_id", "base_footprint")
        self.declare_parameter("publish_feedback", True)
        self.declare_parameter("publish_rate", 50.0)
        self.declare_parameter("command_timeout", 0.25)
        self.declare_parameter("max_vx", 2.5)
        self.declare_parameter("max_vy", 2.5)
        self.declare_parameter("max_wz", 3.0)

        self._port = str(self.get_parameter("port").value)
        self._baudrate = int(self.get_parameter("baudrate").value)
        self._publish_feedback = bool(self.get_parameter("publish_feedback").value)
        self._feedback_frame_id = str(self.get_parameter("feedback_frame_id").value)
        self._command_timeout = float(self.get_parameter("command_timeout").value)
        self._max_vx = abs(float(self.get_parameter("max_vx").value))
        self._max_vy = abs(float(self.get_parameter("max_vy").value))
        self._max_wz = abs(float(self.get_parameter("max_wz").value))
        publish_rate = float(self.get_parameter("publish_rate").value)

        if not math.isfinite(publish_rate) or publish_rate <= 0.0:
            raise ValueError("publish_rate must be finite and positive")
        if not math.isfinite(self._command_timeout) or self._command_timeout <= 0.0:
            raise ValueError("command_timeout must be finite and positive")
        if min(self._max_vx, self._max_vy, self._max_wz) <= 0.0:
            raise ValueError("velocity limits must be finite and positive")

        self._fd: Optional[int] = None
        self._last_open_attempt = 0.0
        self._last_cmd: Optional[Tuple[float, float, float]] = None
        self._last_cmd_time = 0.0
        self._last_mode: Optional[int] = None
        self._rx_buffer = bytearray()
        self._last_invalid_command_log = 0.0
        self._last_stale_log = 0.0

        command_topic = str(self.get_parameter("command_topic").value)
        self._command_sub = self.create_subscription(
            Twist, command_topic, self._command_callback, 10
        )
        self._feedback_pub = None
        if self._publish_feedback:
            feedback_topic = str(self.get_parameter("feedback_topic").value)
            self._feedback_pub = self.create_publisher(TwistStamped, feedback_topic, 10)

        self._timer = self.create_timer(
            1.0 / publish_rate, self._periodic_io
        )
        self.get_logger().info(
            f"UART bridge: {self._port} at {self._baudrate} baud, "
            f"command topic '{command_topic}', {publish_rate:g} Hz"
        )
        self._try_open()

    @staticmethod
    def _configure_fd(fd: int, baudrate: int) -> None:
        config = termios.tcgetattr(fd)
        config[0] &= ~(
            termios.IGNBRK
            | termios.BRKINT
            | termios.PARMRK
            | termios.ISTRIP
            | termios.INLCR
            | termios.IGNCR
            | termios.ICRNL
            | termios.IXON
            | termios.IXOFF
            | termios.IXANY
        )
        config[1] &= ~termios.OPOST
        config[2] &= ~(
            termios.CSIZE
            | termios.PARENB
            | termios.CSTOPB
            | getattr(termios, "CRTSCTS", 0)
        )
        config[2] |= termios.CS8 | termios.CLOCAL | termios.CREAD
        config[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG)
        config[4] = getattr(termios, f"B{baudrate}")
        config[5] = getattr(termios, f"B{baudrate}")
        config[6][termios.VMIN] = 0
        config[6][termios.VTIME] = 1
        termios.tcsetattr(fd, termios.TCSANOW, config)
        termios.tcflush(fd, termios.TCIOFLUSH)

    def _try_open(self) -> None:
        now = time.monotonic()
        if self._fd is not None or now - self._last_open_attempt < 1.0:
            return
        self._last_open_attempt = now
        try:
            fd = os.open(self._port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            if hasattr(termios, "TIOCEXCL"):
                try:
                    import fcntl

                    fcntl.ioctl(fd, termios.TIOCEXCL)
                except OSError:
                    os.close(fd)
                    raise
            self._configure_fd(fd, self._baudrate)
            self._fd = fd
            self._rx_buffer.clear()
            self.get_logger().info(f"Opened {self._port} at {self._baudrate} baud")
        except (OSError, AttributeError) as exc:
            self.get_logger().error(f"Cannot open {self._port}: {exc}")

    def _close_fd(self) -> None:
        if self._fd is None:
            return
        try:
            os.close(self._fd)
        except OSError:
            pass
        self._fd = None

    def _command_callback(self, msg: Twist) -> None:
        values = (msg.linear.x, msg.linear.y, msg.angular.z)
        if not all(math.isfinite(float(value)) for value in values):
            now = time.monotonic()
            if now - self._last_invalid_command_log > 2.0:
                self.get_logger().warning("Ignoring non-finite cmd_vel")
                self._last_invalid_command_log = now
            return

        # ROS +Y is left; the firmware protocol defines +Y as right.
        command = (
            _clamp(float(msg.linear.x), -self._max_vx, self._max_vx),
            _clamp(-float(msg.linear.y), -self._max_vy, self._max_vy),
            _clamp(float(msg.angular.z), -self._max_wz, self._max_wz),
        )
        self._last_cmd = command
        self._last_cmd_time = time.monotonic()

    @staticmethod
    def _make_frame(vx: float, vy: float, wz: float, spin_mode: int) -> bytes:
        return COMMAND_HEADER + struct.pack("<fffB", vx, vy, wz, spin_mode)

    def _write_frame(self, frame: bytes) -> bool:
        if self._fd is None:
            return False
        try:
            offset = 0
            while offset < len(frame):
                offset += os.write(self._fd, frame[offset:])
            return True
        except OSError as exc:
            self.get_logger().error(f"UART write failed: {exc}")
            self._close_fd()
            return False

    def _periodic_io(self) -> None:
        if self._fd is None:
            self._try_open()
            return

        now = time.monotonic()
        if self._last_cmd is None:
            frame = self._make_frame(0.0, 0.0, 0.0, 0)
            mode = 0
        elif now - self._last_cmd_time <= self._command_timeout:
            frame = self._make_frame(*self._last_cmd, 1)
            mode = 1
        else:
            frame = self._make_frame(0.0, 0.0, 3.14, 1)
            mode = 1
            if now - self._last_stale_log > 2.0:
                self.get_logger().warning(
                    "cmd_vel timed out; holding automatic zero velocity"
                )
                self._last_stale_log = now

        if mode != self._last_mode:
            self.get_logger().info(
                "UART control mode: " + ("AUTO" if mode == 1 else "REMOTE")
            )
            self._last_mode = mode
        self._write_frame(frame)
        self._read_feedback()

    def _read_feedback(self) -> None:
        if self._fd is None:
            return
        try:
            while True:
                chunk = os.read(self._fd, 4096)
                if not chunk:
                    break
                self._rx_buffer.extend(chunk)
        except BlockingIOError:
            pass
        except OSError as exc:
            self.get_logger().error(f"UART read failed: {exc}")
            self._close_fd()
            return

        while True:
            start = self._rx_buffer.find(FEEDBACK_HEADER)
            if start < 0:
                del self._rx_buffer[:-3]
                return
            if start:
                del self._rx_buffer[:start]
            if len(self._rx_buffer) < FEEDBACK_LENGTH:
                return
            frame = bytes(self._rx_buffer[:FEEDBACK_LENGTH])
            del self._rx_buffer[:FEEDBACK_LENGTH]
            vx, vy, wz = struct.unpack_from("<fff", frame, 4)
            if not all(math.isfinite(value) for value in (vx, vy, wz)):
                continue
            if self._feedback_pub is not None:
                msg = TwistStamped()
                msg.header.stamp = self.get_clock().now().to_msg()
                msg.header.frame_id = self._feedback_frame_id
                msg.twist.linear.x = vx
                msg.twist.linear.y = vy
                msg.twist.angular.z = wz
                self._feedback_pub.publish(msg)

    def close(self) -> None:
        """Stop automatic mode before releasing the UART."""
        if self._fd is None:
            return
        exit_frame = self._make_frame(0.0, 0.0, 0.0, 0)
        for _ in range(5):
            if not self._write_frame(exit_frame):
                break
            time.sleep(0.01)
        self._close_fd()

    def destroy_node(self) -> bool:
        self.close()
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ChassisSerialBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
