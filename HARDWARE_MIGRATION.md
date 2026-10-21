# 单 MID360 实机迁移

本文对应当前工作区源码。仿真导航、RViz 手动目标和仿真血量决策已验证；NUC 上的雷达定位、底盘协议桥接和实机自主导航仍需分阶段验证。

## 目标设备与配置

- 目标主机：华硕 NUC 13，Ubuntu 22.04 x86_64，ROS 2 Humble。
- 单台 MID360：JSON 当前配置电脑接收地址 `192.168.1.50`、雷达地址 `192.168.1.121`。先确认 NUC 有线网卡实际地址；若不同，需同步修改雷达 JSON 中的所有 host IP 字段和网卡配置。
- 雷达在云台上，雷达相对 `gimbal_yaw` 固定。点云 frame 为 `front_mid360`，实机参数使用 Livox `CustomMsg`（`xfer_format=1`、`lidar_type=1`、`scan_line=4`）。
- 实机 Point-LIO 的 `gravity`、`gravity_init` 当前都设为 `[0, 0, +9.81]`。这只是当前配置值；实测时需按 IMU 方向确认，不能仅凭雷达倒装推断重力向量。

相关配置：

- `src/pb2025_sentry_nav/pb2025_nav_bringup/config/reality/mid360_user_config.json`
- `src/pb2025_sentry_nav/pb2025_nav_bringup/config/reality/nav2_params.yaml`
- `src/pb2025_sentry_nav/pb2025_nav_bringup/launch/rm_navigation_reality_launch.py`

## 1. 在 NUC 上准备工作区

按 [README.md](README.md) 从零安装依赖、构建两个独立 C++ 库和 ROS 工作区。不要把当前电脑的 `build/`、`install/` 复制给 NUC；这些目录包含本机路径和构建环境信息。PCD 被 Git 忽略，需另行传到匹配地图的配置路径。

每个终端加载环境：

```bash
cd ~/beijixiong
source scripts/env.sh
source install/setup.bash
```

实机雷达 JSON 中 host IP 应与 NUC 连接 MID360 的网卡地址一致。IP 可 ping 通只说明 IP 层连通；是否收到雷达数据要看 ROS 话题。

当前地址同时对应已有的 GMK 测试连接：电脑接收 IP `192.168.1.50`，雷达 IP `192.168.1.121`。换设备必须根据实际地址更新所有非空 host IP 和 lidar_configs.ip。电脑网卡静态 IP 配置属于系统设置，不能只修改 JSON。

实机 launch 会等待 enp3s0 链路及 JSON 中的接收 IP 就绪，最多 30 秒，再执行雷达驱动；SDK 保持仓库的 1.4.3，日志内部符号与 ROS 隔离。更换有线网卡时同步调整网口助手的 interface 设置。

## 2. 单独验证雷达和 IMU

先关闭 Gazebo 和仿真导航，避免同一 ROS Domain 中出现仿真和实机同名话题。可单独启动 Livox 驱动：

```bash
python3 "$PB_ROOT/src/pb2025_sentry_nav/pb2025_nav_bringup/launch/gmk_lidar_network_gate.py" -- \
ros2 run livox_ros_driver2 livox_ros_driver2_node --ros-args \
  -r __ns:=/red_standard_robot1 \
  -p xfer_format:=1 -p multi_topic:=0 -p data_src:=0 \
  -p publish_freq:=20.0 -p output_data_type:=0 \
  -p frame_id:=front_mid360 \
  -p user_config_path:="$PB_ROOT/src/pb2025_sentry_nav/pb2025_nav_bringup/config/reality/mid360_user_config.json"
```

另开终端检查数据类型、频率和 IMU：

```bash
ros2 topic type /red_standard_robot1/livox/lidar
ros2 topic hz /red_standard_robot1/livox/lidar
ros2 topic hz /red_standard_robot1/livox/imu
ros2 topic echo /red_standard_robot1/livox/imu --once
```

预期点云类型为 `livox_ros_driver2/msg/CustomMsg`，IMU 类型为 `sensor_msgs/msg/Imu`，数据持续更新且时间戳递增。若没有数据，先检查网卡地址、JSON 中 host/lidar IP、线缆与雷达数据端口；不要以 ping 成功判定 ROS 驱动正常。

也可先停止上面的独立驱动，再运行只启动雷达的接收/退出检查：

```bash
python3 scripts/verify_lidar_shutdown.py
```

该脚本使用独立 ROS 域 174，检查 CustomMsg/IMU 接收与四种停止情形，结束后停止驱动；不会启动导航或底盘控制。
报告和日志位于仓库 `runtime/lidar-verification/`，不提交 Git。短时接收成功不等于标定、频率或定位精度验收。

## 3. 验证 TF、Point-LIO 和扫描

确认每条 TF 只有一个节点发布。实机 YAML 将 `loam_interface.base_frame` 设为 `gimbal_yaw`、`lidar_frame` 设为 `front_mid360`；雷达相对云台的固定外参应由机器人模型 TF 表达。Point-LIO 的 `extrinsic_T/R` 是雷达与 IMU 的外参，不能用它代替雷达到云台的安装 TF。

实机 launch 的默认值是空 namespace、`slam=False`、`use_sim_time=False`、`use_robot_state_pub=False`。如果没有其他节点发布完整机器人 TF，可在独立模型测试时设 `use_robot_state_pub:=True`；若实际机器人已有 TF 发布者，避免重复发布相同 child frame。

没有可用先验地图时，可用 SLAM 模式开始实地建图。SLAM 模式使用 `slam_toolbox`，并停用依赖先验 PCD 的 small_gicp 重定位。地图稳定后另存地图，再验证定位模式。不要直接把 `rmuc_2025` 仿真地图当作实地地图。

当前 `pointcloud_to_laserscan` 节点已实现 `min_intensity` / `max_intensity` 过滤；实机 YAML 设为 `0.1` 到 `2.0`。高度和强度阈值会影响地面和低矮障碍物是否进入扫描，调整后需实际检查低矮障碍以及斜坡上的点云。

## 4. 实机导航启动

在 TF、雷达、Point-LIO 和地图路径已核实后，可先关闭底盘串口桥接，验证实机数据与导航栈：

```bash
cd ~/beijixiong
source scripts/env.sh
source install/setup.bash
ros2 launch pb2025_nav_bringup rm_navigation_reality_launch.py \
  namespace:=red_standard_robot1 \
  slam:=True use_sim_time:=False \
  use_robot_state_pub:=True use_composition:=False \
  use_chassis_serial:=False \
  chassis_serial_port:=/dev/ttyACM0 \
  chassis_serial_baudrate:=1152000
```

这组参数适用于没有先验地图且由此 launch 发布模型 TF 的独立测试。确认机器人 TF 已由其他来源发布后，将 `use_robot_state_pub` 设为 `False`。有先验地图时改用 `slam:=False`，并确保 `map:=...` 和 `prior_pcd_file:=...` 指向同一场地、坐标一致的地图与点云。

Nav2 的速度经平滑和 `fake_vel_transform` 转换后发布到 namespace 下的 `cmd_vel`，类型为 `geometry_msgs/msg/Twist`，具体话题为 `/red_standard_robot1/cmd_vel`。启用 `use_chassis_serial:=True` 后，`pb_chassis_serial` 订阅该话题并以 50 Hz 发送电控协议：`FA FB 21 0D`、三个小端 `float32` 速度和 `spin_mode` 字节。ROS 的 `linear.y` 左正会转换为电控协议的右正；收到新速度时使用 `spin_mode=1`，指令超过 0.25 秒未更新时发送 `vx=0, vy=0, wz=3.14, spin_mode=1`，节点退出时发送 `spin_mode=0` 零速。超时分支的日志仍写为保持零速度，但实际帧包含旋转速度，首次启用前必须与电控确认这是预期自转行为以及如何接管、停止。

电控回传的 `FA FB 42 0C` 速度帧会发布为 `/red_standard_robot1/chassis/actual_velocity`（`geometry_msgs/msg/TwistStamped`），用于诊断。该回传目前不替代 Point-LIO 的里程计输入，也不直接闭合 Nav2 的定位回路。

## 5. 底盘通信边界

工作区还包含 `rmoss_base` 的 UART 通用传输代码和 `SimpleRobotBaseNode` 示例；该示例订阅的是 `cmd_gimbal`，发送云台角度示例协议，固定使用 `/dev/ttyUSB0`、115200 baud，不要把它当作导航底盘驱动。导航底盘使用上面单独的 `pb_chassis_serial` 桥接，当前默认串口为 `/dev/ttyACM0`、1152000 baud。

首次接入实车时，先只启动桥接并检查打开串口和回传话题，再启动完整导航。确认电控处于允许自动控制的状态后，才在低速、可立即断电的场地发送目标；不要同时运行其他程序占用同一个串口。

## 验收顺序

1. NUC 能稳定接收 MID360 点云和 IMU。
2. TF 连通，点云与云台、底盘坐标关系正确；Point-LIO 静止和低速移动时输出连续。
3. 无先验地图时可持续 SLAM 建图；有先验地图时 small_gicp 与二维地图坐标一致。
4. 确认电控桥接后，先检查速度话题，再在受控场地验证低速方向、旋转和停驶行为。
5. RViz 目标导航通过后，再接入决策节点和真实血量输入；持续运行至少 7 分钟，并覆盖预期的底盘临时断电场景。

本仓库包含基于当前电控协议的实机底盘 `cmd_vel` 协议桥接；NUC 上的完整实机导航仍需按上述顺序验收。
