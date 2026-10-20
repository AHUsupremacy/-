"""Publish test HP on a separate topic, without changing simulator state."""

import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from rmoss_interfaces.msg import RobotStatus


class MockRobotStatus(Node):
    def __init__(self, **kwargs):
        super().__init__('mock_robot_status', **kwargs)
        self.declare_parameter('remain_hp', 100)
        self.declare_parameter('max_hp', 100)
        self.declare_parameter('status_topic', 'decision/test_robot_status')
        error = self._validate([])
        if not error.successful:
            raise ValueError(error.reason)
        self.add_on_set_parameters_callback(self._validate)
        self._pub = self.create_publisher(
            RobotStatus, self.get_parameter('status_topic').value, 10
        )
        self._timer = self.create_timer(0.2, self._publish)

    def _validate(self, parameters):
        values = {name: self.get_parameter(name).value for name in ('remain_hp', 'max_hp')}
        for param in parameters:
            if param.name in values:
                if type(param.value) is not int:
                    return SetParametersResult(successful=False, reason='HP values must be integers')
                values[param.name] = param.value
            elif param.name == 'status_topic':
                return SetParametersResult(successful=False, reason='Restart to change status_topic')
        valid = (0 < values['max_hp'] <= 2147483647
                 and 0 <= values['remain_hp'] <= values['max_hp'])
        return SetParametersResult(
            successful=valid, reason='' if valid else 'Require 0 <= remain_hp <= max_hp <= int32 max; max_hp > 0'
        )

    def _publish(self):
        msg = RobotStatus()
        msg.remain_hp = self.get_parameter('remain_hp').value
        msg.max_hp = self.get_parameter('max_hp').value
        self._pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = MockRobotStatus()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
