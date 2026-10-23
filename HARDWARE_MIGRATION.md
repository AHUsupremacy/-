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

## 2. 单独验证雷达和 IMU

先关闭 Gazebo 和仿真导航，避免同一 ROS Domain 中出现仿真和实机同名话题。可单独启动 Livox 驱动：

```bash
ros2 run livox_ros_driver2 livox_ros_driver2_node --ros-args \
  -r __ns:=/red_standard_robot1 \
  -p xfer_format:=1 -p multi_topic:=0 -p data_src:=0 \
  -p publish_freq:=20.0 -p output_data_type:=0 \
  -p frame_id:=front_mid360 \
  -p user_config_path:="$(realpath src/pb2025_sentry_nav/pb2025_nav_bringup/config/reality/mid360_user_config.json)"
```

另开终端检查数据类型、频率和 IMU：

```bash
ros2 topic type /red_standard_robot1/livox/lidar
ros2 topic hz /red_standard_robot1/livox/lidar
ros2 topic hz /red_standard_robot1/livox/imu
ros2 topic echo /red_standard_robot1/livox/imu --once
```

预期点云类型为 `livox_ros_driver2/msg/CustomMsg`，IMU 类型为 `sensor_msgs/msg/Imu`，数据持续更新且时间戳递增。若没有数据，先检查网卡地址、JSON 中 host/lidar IP、线缆与雷达数据端口；不要以 ping 成功判定 ROS 驱动正常。

## 3. 验证 TF、Point-LIO 和扫描

确认每条 TF 只有一个节点发布。实机 YAML 将 `loam_interface.base_frame` 设为 `gimbal_yaw`、`lidar_frame` 设为 `front_mid360`；雷达相对云台的固定外参应由机器人模型 TF 表达。Point-LIO 的 `extrinsic_T/R` 是雷达与 IMU 的外参，不能用它代替雷达到云台的安装 TF。

实机 launch 的默认值是空 namespace、`slam=False`、`use_sim_time=False`、`use_robot_state_pub=False`。如果没有其他节点发布完整机器人 TF，可在独立模型测试时设 `use_robot_state_pub:=True`；若实际机器人已有 TF 发布者，避免重复发布相同 child frame。

没有可用先验地图时，可用 SLAM 模式开始实地建图。SLAM 模式使用 `slam_toolbox`，并停用依赖先验 PCD 的 small_gicp 重定位。地图稳定后另存地图，再验证定位模式。不要直接把 `rmuc_2025` 仿真地图当作实地地图。

当前 `pointcloud_to_laserscan` 节点已实现 `min_intensity` / `max_intensity` 过滤；实机 YAML 设为 `0.1` 到 `2.0`。高度和强度阈值会影响地面和低矮障碍物是否进入扫描，调整后需实际检查低矮障碍以及斜坡上的点云。

## 4. 实机导航启动

在 TF、雷达、Point-LIO 和地图路径已核实后，实机导航的独立测试命令为：

```bash
cd ~/beijixiong
source scripts/env.sh
source install/setup.bash
ros2 launch pb2025_nav_bringup rm_navigation_reality_launch.py \
  namespace:=red_standard_robot1 \
  slam:=True use_sim_time:=False \
  use_robot_state_pub:=True use_composition:=False
```

这组参数适用于没有先验地图且由此 launch 发布模型 TF 的独立测试。确认机器人 TF 已由其他来源发布后，将 `use_robot_state_pub` 设为 `False`。有先验地图时改用 `slam:=False`，并确保 `map:=...` 和 `prior_pcd_file:=...` 指向同一场地、坐标一致的地图与点云。

Nav2 的速度经平滑和 `fake_vel_transform` 转换后发布到 namespace 下的 `cmd_vel`，类型为 `geometry_msgs/msg/Twist`，具体话题为 `/red_standard_robot1/cmd_vel`。该话题只是 ROS 速度输出；它不会直接驱动串口电控板。

## 5. 底盘通信边界

工作区包含 `rmoss_base` 的 UART 通用传输代码和 `SimpleRobotBaseNode` 示例，但此示例订阅的是 `cmd_gimbal`，发送云台角度示例协议，并监听模式字节；它没有把导航的 `cmd_vel` 转为本车底盘协议。UART 示例还固定使用 `/dev/ttyUSB0`、115200 baud，与目前调试器枚举出的 `/dev/ttyACM0` 不是同一配置。

因此，实车运动前需要确认现有电控协议对应的 ROS 通信节点或实现匹配的桥接，再核验它订阅 `cmd_vel` 的名称、消息类型、坐标约定、速度单位以及掉线/底盘断电后的行为。不要把 `rmoss_base` 示例节点误当成已接入的导航底盘驱动。

## 验收顺序

1. NUC 能稳定接收 MID360 点云和 IMU。
2. TF 连通，点云与云台、底盘坐标关系正确；Point-LIO 静止和低速移动时输出连续。
3. 无先验地图时可持续 SLAM 建图；有先验地图时 small_gicp 与二维地图坐标一致。
4. 确认电控桥接后，先检查速度话题，再在受控场地验证低速方向、旋转和停驶行为。
5. RViz 目标导航通过后，再接入决策节点和真实血量输入；持续运行至少 7 分钟，并覆盖预期的底盘临时断电场景。

本仓库不包含已验证的实机底盘 `cmd_vel` 协议桥接，也未完成 NUC 上的实机导航验收。
