# 实机自主导航实施阶段

本文按当前 `beijixiong` 工作区状态规划后续实机工作。仿真和软件构建已经完成阶段性验证；NUC 上的雷达定位、底盘控制桥接和实机自主导航仍需验收。

## 当前基线

- 目标机为华硕 NUC 13、Ubuntu 22.04 x86_64、ROS 2 Humble；需在目标机重新安装依赖、构建 SDK/库和 ROS 工作区。
- 仿真已验证：Gazebo、Nav2 手动目标，以及读取两个 RViz 记录目标并按仿真血量切换目标。
- 实机配置使用单 MID360，配置文件当前写主机地址 `192.168.1.50`、雷达地址 `192.168.1.121`。目标机网卡地址仍需实测确认。
- 实机 launch 支持 `slam:=True`、`use_sim_time:=False` 和 `use_robot_state_pub:=True`。实际运行时要根据 TF 发布来源避免重复 TF。
- 工作区能把导航速度输出为 `geometry_msgs/msg/Twist` 的 `cmd_vel`。`rmoss_base` 有 UART 通用工具和云台示例节点，但没有已接入本项目导航 `cmd_vel` 的本车底盘协议桥接。
- 仿真决策已经连接仿真裁判状态；真实裁判血量输入尚未接入决策模块。

## 阶段 1：NUC 部署复现

按 [README.md](README.md) 在 NUC 上从源码安装依赖并构建。PCD 文件被 Git 忽略，需要单独复制；不能把当前电脑的 `build/`、`install/` 直接复制到 NUC。

验收条件：ROS 包可发现；仿真依赖和导航节点可正常启动；运行目录、PCD 路径和 NUC 的网络配置均明确。

## 阶段 2：雷达数据与时间基准

先不启动导航或底盘控制，按 [HARDWARE_MIGRATION.md](HARDWARE_MIGRATION.md) 单独启动 Livox 驱动。核对网卡地址与 `mid360_user_config.json` 的 host IP 一致，再检查 `/red_standard_robot1/livox/lidar` 和 `/red_standard_robot1/livox/imu` 的类型、频率、时间戳。

验收条件：MID360 连续发布 `CustomMsg` 点云和 IMU，持续观测时没有断流或时间戳倒退。ping 结果不作为 ROS 数据验收。

## 阶段 3：TF、里程计和地图

确认云台到 MID360 的固定 TF、IMU 外参和 Point-LIO 重力配置。逐条检查 `gimbal_yaw`、`front_mid360`、`base_footprint`、`odom`、`map` 的坐标关系和时间戳；判断 `robot_state_publisher` 是否应启动，确保每条 TF 只有一个权威发布者。

没有可用先验地图时，先以 `slam:=True` 建立场地二维地图并保存；该模式停用依赖先验 PCD 的 small_gicp。随后用与二维地图坐标一致的 PCD 验证定位模式。检查点云过滤时重点观察地面、斜坡和低矮障碍物；当前 `pointcloud_to_laserscan` 已支持 intensity 阈值，仿真值为 0.05–2.0、实机值为 0.1–2.0。

验收条件：机器人静止和低速移动时 Point-LIO 输出连续；地图与实时传感器数据不漂移、不重影到影响规划的程度；costmap 内机器人位置有效，障碍扫描能看到场地要求的低矮物体。

## 阶段 4：电控速度桥接

先从实际电控源码和已有 ROS1 部署中确认串口/网络协议、速度字段、坐标约定、单位、反馈信息和节点运行方式。确定 ROS1 与当前 ROS 2 节点之间的接口后，再决定复用现有节点、增加 ROS 2 桥接或重新实现。目标是让桥接节点订阅导航的 `cmd_vel`，并提供定位/控制所需反馈；不可把 `rmoss_base::SimpleRobotBaseNode` 当作现成底盘驱动，它只订阅 `cmd_gimbal` 示例接口。

先在机器人抬起或受控场地验证数据映射，再低速确认前后、横移（底盘支持时）、旋转和停止方向。确认电控板如何处理通信中断和底盘断电，恢复供电后再检查导航状态是否能继续。

验收条件：导航发布的速度能按约定转换并由电控执行；电控反馈的速度/里程计与实际方向一致；通信与断电情况的表现可重复解释。

## 阶段 5：导航和决策运行

先用 RViz 发送短距离目标，验证建图/定位、规划、避障、`cmd_vel` 和电控执行形成完整闭环。然后接入真实血量话题；血量高于阈值选择点一，低于或等于阈值选择点二。当前两个目标记录格式和仿真切换流程可复用，实机话题与坐标必须重新核对。

最终测试连续运行至少 7 分钟，观察雷达、IMU、TF、Point-LIO、Nav2、目标切换和底盘反馈。按实测场景覆盖临时底盘断电：记录掉电前后节点状态、是否残留速度命令、恢复后是否重新定位及继续导航。这个阶段验证现有系统行为，不预设未经验证的电控掉线处理能力。

验收条件：能按自身及周围状态选择记录目标，Nav2 将机器人送达目标；连续运行达标，且临时断电后的恢复行为符合预期。

## 实机启动基线

传感器、TF 和地图配置确认后，无先验地图的独立测试可从以下命令开始：

```bash
cd ~/beijixiong
source scripts/env.sh
source install/setup.bash
ros2 launch pb2025_nav_bringup rm_navigation_reality_launch.py \
  namespace:=red_standard_robot1 \
  slam:=True use_sim_time:=False \
  use_robot_state_pub:=True use_composition:=False
```

该命令启动导航栈和 Livox 驱动，但不会启动能控制本车底盘的协议桥接。真实 TF 已由其他节点提供时，将 `use_robot_state_pub:=False`。细节和雷达单独启动方式见 [HARDWARE_MIGRATION.md](HARDWARE_MIGRATION.md)。
