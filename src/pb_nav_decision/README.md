# 仿真目标点决策

这个包在 Nav2 上层实现一个按血量选择目标的二叉决策树。现有 Nav2、Gazebo 和 RViz 的 `nav2_rviz_plugins/GoalTool` 不会被修改。

## 两种模式

记录模式只保存目标，不向 Nav2 发送导航任务。它订阅 `decision/record_goal`（在机器人命名空间内），由 RViz 中额外添加的标准 `rviz_default_plugins/SetGoal` 工具发布 `geometry_msgs/msg/PoseStamped`。现有的 Nav2 Goal 工具继续保持原样。

目标保存到 `runtime/decision_goals.json`，默认坐标系必须是 `map`。前两个目标依次写入 `point_one` 和 `point_two`；第三个及之后的目标会丢弃最旧的点，只保留最近两个。

决策模式启动时读取这个文件。`remain_hp > hp_threshold` 选择 `point_one`，`remain_hp <= hp_threshold` 选择 `point_two`，再通过 Nav2 的 `NavigateToPose` action 执行导航。目标跨分支变化时取消旧目标后发送新目标，导航失败后定时重试；同一目标到达后不会重复发送。

## 编译

```bash
cd /home/frank/beijixiong
source scripts/env.sh
source install/setup.bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 colcon build --base-paths src/pb_nav_decision \
  --packages-select pb_nav_decision --symlink-install \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3
```

## 记录两个目标

先启动 Gazebo、Nav2 和 RViz，确认 RViz 的 Fixed Frame 是 `map`，并停止已经运行的决策节点。运行记录模式时建议清空旧点位：

```bash
cd /home/frank/beijixiong
bash scripts/start_sim_decision.sh mode:=record reset:=true
```

在 RViz 的工具栏中额外添加一次 `rviz_default_plugins/SetGoal`，将它的 Topic 设置为：

```text
/red_standard_robot1/decision/record_goal
```

这是独立的记录工具，不是现有的 Nav2 Goal 工具。用它依次点击两个目标并拖出朝向。记录终端会打印保存结果，文件内容可查看：

```bash
cat /home/frank/beijixiong/runtime/decision_goals.json
```

记录完成后退出记录节点。下次继续记录时不传 `reset:=true`，已有的点会被保留，新的点会按“最近两个”规则滚动更新。

## 启动决策

使用测试血量节点：

```bash
cd /home/frank/beijixiong
bash scripts/start_sim_decision.sh mode:=decision hp_source:=test
```

初始血量是 `100/100`，默认阈值是 50，因此选择点一。切换到点二和点一：

```bash
ros2 param set /red_standard_robot1/mock_robot_status remain_hp 20
ros2 param set /red_standard_robot1/mock_robot_status remain_hp 100
```

使用仿真裁判血量：

```bash
bash scripts/start_sim_decision.sh mode:=decision hp_source:=referee
```

决策节点会读取 `/referee_system/red_standard_robot1/robot_status`。查看状态：

```bash
ros2 topic echo /red_standard_robot1/decision/state
```

## 参数

可通过 launch 参数修改：

- `goal_file:=/path/to/decision_goals.json`
- `record_topic:=decision/record_goal`
- `hp_source:=test|referee`
- `use_sim_time:=true|false`

`decision.yaml` 中的 `target_one` 和 `target_two` 只作为旧测试接口的后备参数；通过 `mode:=decision` 启动时，目标文件优先且必须包含两个点。

## 验收

1. 记录模式生成包含两个点的 JSON 文件。
2. 高血量启动后只向点一发送一个 Nav2 目标。
3. 导航途中降到低血量，旧目标取消后切换到点二。
4. 保持低血量到达点二后不重复发送。
5. 恢复高血量后重新前往点一。
6. 删除或破坏目标文件时，决策模式拒绝启动并给出明确错误。

## 测试

```bash
cd /home/frank/beijixiong
source scripts/env.sh
source install/setup.bash
colcon test --packages-select pb_nav_decision --event-handlers console_direct+
colcon test-result --test-result-base build/pb_nav_decision --verbose

ROS_DOMAIN_ID=87 ROS_LOCALHOST_ONLY=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  /usr/bin/python3 -m pytest -q -p no:cacheprovider \
  src/pb_nav_decision/test/test_nav_decision_ros.py
```
