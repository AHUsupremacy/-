import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch_ros.actions import Node


def start_nodes(context):
    namespace = context.launch_configurations['namespace'].strip('/')
    mode = context.launch_configurations['mode']
    source = context.launch_configurations['hp_source']
    use_sim_time = context.launch_configurations['use_sim_time'].lower() == 'true'
    goal_file = context.launch_configurations['goal_file']
    if mode == 'record':
        return [Node(
            package='pb_nav_decision', executable='record_goals', namespace=namespace,
            name='record_decision_goals', output='screen', parameters=[{
                'input_topic': context.launch_configurations['record_topic'],
                'goal_file': goal_file,
                'reset': context.launch_configurations['reset'].lower() == 'true',
            }],
        )]
    status_topic = (
        f'/{namespace}/decision/test_robot_status' if source == 'test'
        else f'/referee_system/{namespace}/robot_status'
    )
    nodes = [Node(
        package='pb_nav_decision', executable='nav_decision', namespace=namespace,
        name='nav_decision', output='screen',
        parameters=[context.launch_configurations['params_file'], {
            'use_sim_time': use_sim_time, 'robot_status_topic': status_topic,
            'goal_file': goal_file,
        }],
    )]
    if source == 'test':
        nodes.append(Node(
            package='pb_nav_decision', executable='mock_robot_status', namespace=namespace,
            name='mock_robot_status', output='screen', parameters=[{
                'use_sim_time': use_sim_time, 'status_topic': status_topic,
                'remain_hp': 100, 'max_hp': 100,
            }],
        ))
    return nodes


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('namespace', default_value='red_standard_robot1'),
        DeclareLaunchArgument('mode', default_value='decision', choices=['record', 'decision']),
        DeclareLaunchArgument('hp_source', default_value='test', choices=['test', 'referee']),
        DeclareLaunchArgument('use_sim_time', default_value='true', choices=['true', 'false']),
        DeclareLaunchArgument('record_topic', default_value='decision/record_goal'),
        DeclareLaunchArgument('reset', default_value='false', choices=['true', 'false']),
        DeclareLaunchArgument('goal_file', default_value=os.path.join(
            os.getcwd(), 'runtime', 'decision_goals.json')),
        DeclareLaunchArgument('params_file', default_value=os.path.join(
            get_package_share_directory('pb_nav_decision'), 'config', 'decision.yaml'
        )),
        OpaqueFunction(function=start_nodes),
    ])
