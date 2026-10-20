"""Real DDS/action tests against a fake Nav2 server, in a separate namespace.

Run with ROS_DOMAIN_ID=87 and PYTEST_DISABLE_PLUGIN_AUTOLOAD=1.
No simulator or physical devices are used.
"""

import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from nav2_msgs.action import NavigateToPose
import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from rmoss_interfaces.msg import RobotStatus

from pb_nav_decision.mock_robot_status import MockRobotStatus
from pb_nav_decision.nav_decision import NavDecision
from pb_nav_decision.goal_store import StoredGoal, save_goals


class NavDecisionRosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def setUp(self):
        self.namespace = f'/decision_test_{os.getpid()}'
        workspace = Path(__file__).resolve().parents[3]
        temp_root = workspace / 'runtime' / 'tmp'
        temp_root.mkdir(parents=True, exist_ok=True)
        self.goal_dir = TemporaryDirectory(dir=temp_root)
        self.goal_file = str(Path(self.goal_dir.name) / 'decision_goals.json')
        save_goals(self.goal_file, [
            StoredGoal(2.0, 1.0, 1.2),
            StoredGoal(-1.0, 0.0, -0.5),
        ])
        self.helper = Node('fake_nav2', namespace=self.namespace)
        self.pub = self.helper.create_publisher(RobotStatus, 'status', 10)
        self.nav = NavDecision(namespace=self.namespace, parameter_overrides=[
            Parameter('use_sim_time', value=False),
            Parameter('robot_status_topic', value='status'),
            Parameter('hp_threshold', value=250),
            Parameter('tick_period', value=0.02),
            Parameter('retry_period', value=0.15),
            Parameter('goal_file', value=self.goal_file),
        ])
        self.executor = MultiThreadedExecutor(num_threads=4)
        self.executor.add_node(self.helper)
        self.executor.add_node(self.nav)
        self.server = None
        self.stopping = False
        self.mode = 'hold'
        self.reject_next = False
        self.requests = []
        self.events = []
        self.running = 0
        self.max_running = 0

    def tearDown(self):
        self.nav._timer.cancel()
        self.stopping = True
        # Drain goal results before destroying the server's native handles.
        self.spin_until(lambda: self.running == 0 and self.nav._active is None, timeout=3)
        self.executor.shutdown(timeout_sec=3)
        if self.server is not None:
            self.server.destroy()
        self.nav.destroy_node()
        self.helper.destroy_node()
        self.goal_dir.cleanup()

    def spin_until(self, predicate, timeout=5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end and not predicate():
            self.executor.spin_once(timeout_sec=0.02)
        self.assertTrue(predicate(), 'Timed out waiting for ROS condition')

    def spin_for(self, duration):
        end = time.monotonic() + duration
        while time.monotonic() < end:
            self.executor.spin_once(timeout_sec=0.02)

    def hp(self, value, maximum=500):
        self.spin_until(lambda: self.pub.get_subscription_count() > 0)
        self.pub.publish(RobotStatus(remain_hp=value, max_hp=maximum))
        if 0 <= value <= maximum and maximum > 0:
            self.spin_until(lambda: self.nav._health is not None and self.nav._health.remain_hp == value)

    def create_server(self):
        self.server = ActionServer(
            self.helper, NavigateToPose, 'navigate_to_pose',
            execute_callback=self.execute,
            goal_callback=self.goal,
            cancel_callback=self.cancel,
            callback_group=ReentrantCallbackGroup(),
        )

    def goal(self, request):
        self.requests.append(request)
        if self.reject_next:
            self.reject_next = False
            return GoalResponse.REJECT
        self.events.append(('accept', request.pose.pose.position.x))
        return GoalResponse.ACCEPT

    def cancel(self, handle):
        self.events.append(('cancel', handle.request.pose.pose.position.x))
        return CancelResponse.ACCEPT

    def execute(self, handle):
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        while not self.stopping:
            if handle.is_cancel_requested:
                handle.canceled()
                break
            if self.mode == 'succeed':
                handle.succeed()
                break
            if self.mode == 'abort_once':
                self.mode = 'hold'
                handle.abort()
                break
            time.sleep(0.01)
        else:
            handle.abort()
        self.events.append(('terminal', handle.request.pose.pose.position.x))
        self.running -= 1
        return NavigateToPose.Result()

    def test_wait_for_status_then_nav2_and_no_repeated_goals(self):
        self.create_server()
        self.spin_for(0.15)
        self.assertEqual(len(self.requests), 0)
        self.hp(500)
        self.spin_until(lambda: self.nav._state == 'NAVIGATING')
        pose = self.requests[0].pose
        self.assertEqual(pose.header.frame_id, 'map')
        self.assertAlmostEqual(pose.pose.orientation.z, math.sin(0.6))
        self.hp(450)
        self.spin_for(0.3)
        self.assertEqual(len(self.requests), 1)
        self.mode = 'succeed'
        self.spin_until(lambda: self.nav._state == 'ARRIVED')
        self.hp(400)
        self.spin_for(0.3)
        self.assertEqual(len(self.requests), 1)
        self.hp(100)
        self.spin_until(lambda: len(self.requests) == 2 and self.nav._state == 'ARRIVED')
        self.assertEqual(self.requests[1].pose.pose.position.x, -1.0)
        self.hp(500)
        self.spin_until(lambda: len(self.requests) == 3)

    def test_target_change_cancels_before_replacement(self):
        self.create_server()
        self.hp(500)
        self.spin_until(lambda: self.nav._state == 'NAVIGATING')
        self.hp(100)
        self.spin_until(lambda: len(self.requests) == 2 and self.nav._state == 'NAVIGATING')
        self.assertLess(self.events.index(('terminal', 2.0)), self.events.index(('accept', -1.0)))
        self.assertEqual(self.max_running, 1)
        self.assertEqual(self.requests[1].pose.pose.position.x, -1.0)

    def test_start_before_nav2_and_invalid_hp(self):
        self.hp(501)
        self.spin_for(0.1)
        self.assertIsNone(self.nav._desired)
        self.hp(500)
        self.spin_until(lambda: self.nav._state == 'WAITING_NAV2')
        self.create_server()
        self.spin_until(lambda: self.nav._state == 'NAVIGATING')

    def test_rejection_and_abort_retry(self):
        self.reject_next = True
        self.create_server()
        self.hp(500)
        self.spin_until(lambda: len(self.requests) == 2 and self.nav._state == 'NAVIGATING')
        self.mode = 'abort_once'
        self.spin_until(lambda: len(self.requests) == 3 and self.nav._state == 'NAVIGATING')
        self.assertEqual(self.max_running, 1)

    def test_mock_hp_parameter_validation(self):
        mock = MockRobotStatus(namespace=self.namespace)
        try:
            self.assertTrue(mock.set_parameters([Parameter('remain_hp', value=100)])[0].successful)
            self.assertFalse(mock.set_parameters([Parameter('remain_hp', value=501)])[0].successful)
            self.assertFalse(mock.set_parameters([Parameter('max_hp', value=0)])[0].successful)
            self.assertEqual(mock.get_parameter('remain_hp').value, 100)
        finally:
            mock.destroy_node()


if __name__ == '__main__':
    unittest.main()
