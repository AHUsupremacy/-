"""Select goals using HP, then manage a single Nav2 action at a time."""

from dataclasses import dataclass
import json
import math
import time

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
import rclpy
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from rmoss_interfaces.msg import RobotStatus
from std_msgs.msg import String

from .decision_tree import HealthDecisionTree, RobotHealth
from .goal_store import load_goals


@dataclass
class Attempt:
    target: str
    handle: object = None
    cancel_future: object = None
    cancel_retry_at: float = 0.0


class NavDecision(Node):
    def __init__(self, **kwargs):
        super().__init__('nav_decision', **kwargs)
        robot_namespace = self.get_namespace().strip('/')
        if not robot_namespace:
            robot_namespace = 'red_standard_robot1'
        defaults = {
            'robot_status_topic': f'/referee_system/{robot_namespace}/robot_status',
            'navigate_action': 'navigate_to_pose',
            'global_frame': 'map',
            'goal_file': '',
            'hp_threshold': 50,
            'target_one': [2.0, 0.0, 0.0],
            'target_two': [0.5, 0.0, 0.0],
            'tick_period': 0.2,
            'retry_period': 3.0,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value, ParameterDescriptor(read_only=True))
        self._tree = HealthDecisionTree(self.get_parameter('hp_threshold').value)
        self._frame = self.get_parameter('global_frame').value
        self._targets = {}
        goal_file = self.get_parameter('goal_file').value
        if goal_file:
            point_one, point_two = load_goals(goal_file)
            self._targets = {
                'target_one': (point_one.x, point_one.y, point_one.yaw),
                'target_two': (point_two.x, point_two.y, point_two.yaw),
            }
            self.get_logger().info(f'Loaded target points from {goal_file}')
        else:
            for name in ('target_one', 'target_two'):
                pose = self.get_parameter(name).value
                if len(pose) != 3 or not all(math.isfinite(v) for v in pose):
                    raise ValueError(f'{name} must contain finite [x, y, yaw_radians]')
                self._targets[name] = tuple(pose)
        tick_period = self.get_parameter('tick_period').value
        self._retry_period = self.get_parameter('retry_period').value
        if not self._frame or not all(
            math.isfinite(v) and v > 0 for v in (tick_period, self._retry_period)
        ):
            raise ValueError('global_frame must be set; periods must be finite and positive')

        self._health = None
        self._desired = None
        self._completed = None
        self._active = None
        self._retry_at = 0.0
        self._state = ''
        self._invalid_reported = False
        self._client = ActionClient(
            self, NavigateToPose, self.get_parameter('navigate_action').value
        )
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self._state_pub = self.create_publisher(String, 'decision/state', latched)
        self._goal_pub = self.create_publisher(PoseStamped, 'decision/selected_goal', latched)
        self._status_sub = self.create_subscription(
            RobotStatus, self.get_parameter('robot_status_topic').value, self._on_status, 10
        )
        self._timer = self.create_timer(tick_period, self._tick)
        self._set_state('WAITING_STATUS')
        self.get_logger().info(
            f"HP input: {self.get_parameter('robot_status_topic').value}; "
            f"HP > {self.get_parameter('hp_threshold').value}: target_one; otherwise: target_two"
        )

    def _set_state(self, state):
        changed = state != self._state
        self._state = state
        payload = {
            'state': state,
            'target': self._desired,
            'active_target': self._active.target if self._active else None,
            'remain_hp': self._health.remain_hp if self._health else None,
            'max_hp': self._health.max_hp if self._health else None,
        }
        self._state_pub.publish(String(data=json.dumps(payload)))
        if changed:
            self.get_logger().info(json.dumps(payload))

    def _on_status(self, msg):
        health = RobotHealth(msg.remain_hp, msg.max_hp)
        if not health.valid:
            if not self._invalid_reported:
                self.get_logger().warning('Ignoring invalid HP: require 0 <= remain_hp <= max_hp, max_hp > 0')
                self._invalid_reported = True
            return
        self._invalid_reported = False
        self._health = health
        selected = self._tree.evaluate(health)
        if selected != self._desired:
            self._desired = selected
            self._completed = None
            self._retry_at = 0.0
            self._goal_pub.publish(self._pose(selected))
            self._set_state('TARGET_SELECTED')
        else:
            self._set_state(self._state)

    def _pose(self, target):
        x, y, yaw = self._targets[target]
        msg = PoseStamped()
        msg.header.frame_id = self._frame
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.pose.position.x = x
        msg.pose.position.y = y
        msg.pose.orientation.z = math.sin(yaw / 2.0)
        msg.pose.orientation.w = math.cos(yaw / 2.0)
        return msg

    def _tick(self):
        if self._desired is None:
            return
        attempt = self._active
        if attempt is not None:
            if (attempt.target != self._desired and attempt.handle is not None
                    and attempt.cancel_future is None
                    and time.monotonic() >= attempt.cancel_retry_at):
                self._set_state('SWITCHING_TARGET')
                attempt.cancel_future = attempt.handle.cancel_goal_async()
                attempt.cancel_future.add_done_callback(
                    lambda future: self._on_cancel(attempt, future)
                )
            return
        if self._completed == self._desired:
            return
        if self.get_parameter('use_sim_time').value and self.get_clock().now().nanoseconds == 0:
            if self._state != 'WAITING_CLOCK':
                self._set_state('WAITING_CLOCK')
            return
        if time.monotonic() < self._retry_at:
            return
        if not self._client.server_is_ready():
            if self._state != 'WAITING_NAV2':
                self._set_state('WAITING_NAV2')
            return
        attempt = Attempt(self._desired)
        self._active = attempt
        goal = NavigateToPose.Goal()
        goal.pose = self._pose(attempt.target)
        self._goal_pub.publish(goal.pose)
        self._set_state('SENDING_GOAL')
        future = self._client.send_goal_async(goal)
        future.add_done_callback(lambda response: self._on_goal(attempt, response))

    def _on_goal(self, attempt, future):
        if self._active is not attempt:
            return
        try:
            handle = future.result()
        except Exception as exc:
            self._failed(attempt, f'Goal request failed: {exc}')
            return
        if not handle.accepted:
            self._failed(attempt, 'Nav2 rejected goal (it may still be starting)')
            return
        attempt.handle = handle
        result = handle.get_result_async()
        result.add_done_callback(lambda response: self._on_result(attempt, response))
        self._set_state('NAVIGATING')

    def _on_cancel(self, attempt, future):
        if self._active is not attempt:
            return
        try:
            if future.result().goals_canceling:
                return  # Wait for this goal's terminal result before sending another.
        except Exception as exc:
            self.get_logger().warning(f'Cancel request failed: {exc}')
        attempt.cancel_future = None
        attempt.cancel_retry_at = time.monotonic() + self._retry_period

    def _failed(self, attempt, message):
        if self._active is not attempt:
            return
        self.get_logger().warning(message)
        self._active = None
        self._retry_at = time.monotonic() + self._retry_period
        self._set_state('RETRY_WAIT')

    def _on_result(self, attempt, future):
        if self._active is not attempt:
            return
        try:
            status = future.result().status
        except Exception as exc:
            self._failed(attempt, f'Result request failed: {exc}')
            return
        self._active = None
        if status == GoalStatus.STATUS_SUCCEEDED:
            self._completed = attempt.target
            self._set_state('ARRIVED')
        elif status == GoalStatus.STATUS_CANCELED:
            self._retry_at = time.monotonic() + (
                self._retry_period if attempt.target == self._desired else 0.0
            )
            self._set_state('GOAL_CANCELED')
        else:
            self._retry_at = time.monotonic() + self._retry_period
            self._set_state('RETRY_WAIT')
            self.get_logger().warning(f'Navigation ended with status={status}; will retry')


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = NavDecision()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
