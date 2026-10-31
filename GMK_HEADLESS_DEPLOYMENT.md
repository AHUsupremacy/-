# GMK N100 无界面实机部署与无线 RViz

目标机为 `rm@gmk`：Ubuntu 22.04.5 x86_64、N100 四核、7.5 GiB 内存、7.8 GiB swap，已安装 ROS 2 Humble。旧入口 `~/pb2025_ws` 指向 `~/gmk-navigation/releases/9fe99d1ea1b5`。源电脑已经完成实机 SLAM 与 RViz 目标导航；以下步骤在小电脑上部署同一次提交，随后验证运行效果。

## 1. 两机分工与现有无线套件

当前笔记本的 `GMK仿真.desktop` 调用桌面目录 `GMK无线套件-队友版/start.sh`。它通过 SSH 启动 GMK 上的 `/home/rm/start_all.sh`，然后在笔记本本地运行 RViz，通过 ROS 2/DDS 接收地图、模型与 TF；不是远程桌面或 X11 窗口转发。

实机使用同一条 Wi-Fi 链路，分工如下：

| 设备 | 运行内容 |
| --- | --- |
| GMK | MID360 驱动、Point-LIO、模型 TF、SLAM、Nav2、底盘串口桥；`use_rviz:=False` |
| 笔记本 | 本地轻量 RViz、模型资源路径转换、TF 转发；`use_sim_time:=False` |
| 通信 | 套件当前 `ROS_DOMAIN_ID=73`，两端一致；SSH 用于登录，ROS 数据通过 Wi-Fi 上的 DDS 传输 |

原“GMK 仿真”入口会启动仿真并使用仿真时间。实机用本仓库的 `scripts/view_reality.sh` 显示，不点击该仿真入口。Gazebo 窗口不属于实机运行内容。

新的显示脚本读取已有套件的通信域，复用它的轻量 RViz 配置与 TF 转发。模型描述来自 GMK，安装位置、关节、雷达外参均保持原值；只把其中 GMK 文件路径替换为笔记本本地网格资源路径，兼容新的 release 目录。笔记本不启动额外的机器人 TF、导航或底盘节点，也不修改已有 RViz 目标工具。

## 2. 在源电脑提交并推送

由使用者在源电脑执行。先确认分支和差异：

```bash
cd ~/beijixiong
git status -sb
git diff --stat
git add README.md HARDWARE_MIGRATION.md GMK_HEADLESS_DEPLOYMENT.md \
  scripts/build_all.sh scripts/view_reality.sh scripts/reality_description_relay.py \
  src/pb2025_sentry_nav/pb2025_nav_bringup/launch/rm_navigation_reality_launch.py
git commit -m "完善N100实机迁移与无线RViz支持"
git push origin gmk/integrate-fixes-20261027
git rev-parse HEAD
```

此处分支是当前的 `gmk/integrate-fixes-20261027`；如之后更换分支，推送和克隆参数也随之更换。记录最后输出的完整提交号，用于核对小电脑版本。

## 3. 小电脑获取新版本

使用已有无线套件登录，不需要在 GMK 安装桌面。在笔记本终端执行：

```bash
bash "$HOME/Desktop/GMK无线套件-队友版/gmk_connect.sh"
bash "$HOME/Desktop/GMK无线套件-队友版/login.sh"
```

在 GMK 中创建新的候选目录。首次迁移使用独立目录，保留旧 release 和 `~/pb2025_ws`：

```bash
mkdir -p ~/gmk-navigation/releases
git clone --branch gmk/integrate-fixes-20261027 --single-branch \
  https://github.com/AHUsupremacy/-.git \
  ~/gmk-navigation/releases/reality-n100-20261031
cd ~/gmk-navigation/releases/reality-n100-20261031
git rev-parse HEAD
```

输出应与源电脑刚提交的提交号一致。目录已存在时先检查其 `git status -sb` 和提交号，不重复克隆到其中。私有仓库可改用小电脑已有权限的 SSH 地址 `git@github.com:AHUsupremacy/-.git`。

## 4. 安装缺少的依赖并在 N100 编译

在 GMK 检查已有依赖：

```bash
source /opt/ros/humble/setup.bash
command -v git cmake colcon rosdep
for pkg in nav2_bringup slam_toolbox pcl_ros ros_gz_sim ros_gz_bridge robot_state_publisher joint_state_publisher; do
  ros2 pkg prefix "$pkg"
done
/usr/bin/python3 -c 'from xmacro.xmacro4sdf import XMLMacro4sdf; print("xmacro OK")'
pkg-config --modversion ignition-gazebo6 ignition-msgs8 ignition-transport11 apr-1
```

缺少的依赖按 README 第 2、3 节补齐。已有 Humble 无需重装 ROS，也不重复添加软件源。当前脚本构建全部 31 个 ROS 包，编译依赖仍包含 Gazebo 开发库，实机运行不会启动 Gazebo。底盘桥使用 Python 标准库，不需要 pyserial 或可选网页模块。

退出 Conda。在没有其他工作区环境的终端编译；下面命令仅清除本次子进程的旧 ROS 路径，并限制包内和包间并行：

```bash
cd ~/gmk-navigation/releases/reality-n100-20261031
env -u AMENT_PREFIX_PATH -u CMAKE_PREFIX_PATH -u COLCON_PREFIX_PATH \
  -u PYTHONPATH -u LD_LIBRARY_PATH -u BASH_ENV \
  PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  BUILD_JOBS=1 COLCON_JOBS=1 bash scripts/build_all.sh
```

脚本已处理 Humble setup 的未绑定变量、Livox ROS2/Humble 参数，以及包内 Make 并行度。无需单独运行 Livox 的 `build.sh`。应完成 31 个包且无 Failed/Aborted。新克隆目录无需 `--clean`；已有生成目录发生符号链接冲突时才加该选项。

脚本安装两个库到系统 `/usr/local`，需要 sudo；因此保留旧源码目录不等于备份了系统库。不要复制源电脑的 `build/`、`install/` 或二进制库替代本机构建。

编译后在同一 GMK 目录检查：

```bash
source scripts/env.sh
source install/local_setup.bash
ros2 pkg prefix pb2025_nav_bringup
ros2 pkg prefix pb_chassis_serial
python3 scripts/verify_livox_sdk_exports.py /usr/local/lib/liblivox_lidar_sdk_shared.so
ldd /usr/local/lib/liblivox_lidar_sdk_shared.so
ldd /usr/local/lib/libsmall_gicp.so
```

两个 ROS 包路径应属于新 release，`ldd` 不应有 `not found`。先加载 Humble 再加载当前 `install/local_setup.bash`，可以避免 `install/setup.bash` 自动串入构建时记录的其他工作区。

## 5. 接入硬件并确认端口

把 MID360 与调试器连接到 GMK，在 GMK 检查：

```bash
ip -br link
ip -br -4 addr
ls -l /dev/serial/by-id/ /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
id -nG
```

旧 GMK 配置使用 `enp3s0`，本次仍需按 `ip -br link` 确认；源电脑的 `enp5s0` 不能直接照搬。没有 IPv4 的接口不会出现在 `ip -br -4 addr` 中。Wi-Fi 地址 `192.168.31.157` 用于两机通信，有线雷达接收地址是 `192.168.1.50/24`，雷达为 `192.168.1.121`。

已有有线配置时沿用，先查看现有 Netplan/NetworkManager 设置，不重置当前 Wi-Fi。`lidar_interface` 只选择检查的网卡，不设置 IP；若改变接收地址，还要同步 JSON 中所有非空 host IP。JSON 路径为 `src/pb2025_sentry_nav/pb2025_nav_bringup/config/reality/mid360_user_config.json`。

串口波特率仍为 `1152000`，可用 `/dev/serial/by-id/` 的稳定路径替代 `/dev/ttyACM0`。若不在 dialout 组，执行 `sudo usermod -aG dialout "$USER"` 后重新登录。保留此前成功测试时的 UART 接线、遥控器连接与电控模式。

## 6. GMK 无 GUI 启动

先结束旧仿真、导航及可能的自启动进程，保证当前只有一套实机节点。不要在仿真仍运行的域 73 中叠加实机节点。

以下在 GMK 的 SSH/tmux 终端运行；`enp3s0` 必须替换为刚确认的网卡名：

```bash
cd ~/gmk-navigation/releases/reality-n100-20261031
source scripts/env.sh
source install/local_setup.bash
export ROS_DOMAIN_ID=73
export ROS_LOCALHOST_ONLY=0
ros2 launch pb2025_nav_bringup rm_navigation_reality_launch.py \
  namespace:=red_standard_robot1 \
  slam:=True use_sim_time:=False \
  use_robot_state_pub:=True use_composition:=False \
  use_rviz:=False lidar_interface:=enp3s0 \
  use_chassis_serial:=False \
  chassis_serial_port:=/dev/ttyACM0 chassis_serial_baudrate:=1152000
```

首次先关闭串口桥，确认雷达、定位、TF 和无线显示。另一个 GMK 终端加载相同环境与域 73，可分别检查点云、IMU 频率以及 `odometry`：

```bash
ros2 topic hz /red_standard_robot1/livox/lidar
ros2 topic hz /red_standard_robot1/livox/imu
ros2 topic echo /red_standard_robot1/odometry --once
ros2 run tf2_ros tf2_echo odom gimbal_yaw_fake --ros-args \
  -r /tf:=/red_standard_robot1/tf -r /tf_static:=/red_standard_robot1/tf_static
```

持续监听命令逐个运行，按 Ctrl+C 后再运行下一条。`slam:=True` 无需 PCD；地图、局部和全局代价地图均由 GMK 计算。重力、安装 TF 与速度处理沿用已验证源码，本次不额外调参。

显示和定位正常后，由使用者 Ctrl+C 退出该启动终端，再运行同一命令，将 `use_chassis_serial:=False` 改为 `True`。随后在笔记本 RViz 下发目标，验证方向、行驶与到点自旋。

已有自旋语义保留：速度超时会发送 `vx=vy=0, wz=3.14, mode=1`。关闭笔记本 RViz 或取消目标不会结束 GMK 串口桥；结束本轮导航应在 GMK 启动终端按 Ctrl+C。

## 7. 笔记本显示与目标输入

在有桌面的笔记本执行，不在 GMK 执行：

```bash
cd ~/beijixiong
bash scripts/view_reality.sh --check
bash scripts/view_reality.sh
```

套件不在默认位置时，用 `--kit-dir "/实际路径/GMK无线套件-队友版"`。`--check` 只验证本地依赖，不连接 GMK、不启动节点或窗口；正式入口只启动笔记本显示，不替你启动小电脑导航。轻量配置不订阅大点云，保留地图、机器人和目标工具，适合无线调试。

两机应能通过 DDS 发现与传输数据；SSH 可登录不代表 DDS 已互通。笔记本另开终端可检查：

```bash
source /opt/ros/humble/setup.bash
source "$HOME/Desktop/GMK无线套件-队友版/gmk_env.sh"
export ROS_LOCALHOST_ONLY=0
ros2 topic list --no-daemon
ros2 topic echo /red_standard_robot1/map --field info --once
```

如果 GMK 本地有话题而笔记本没有，核对同域、`ROS_LOCALHOST_ONLY=0`、已有 RMW/DDS 配置和 AP 的客户端隔离；只读查询失败不需要重启整套导航。真实时间运行时还需两机系统时间同步，可分别用 `timedatectl status` 检查。不要用仿真的 `/clock` 替代真实时间。

## 8. 验证后切换工作区入口

先完成点云/TF、地图显示、RViz 实车目标导航和持续运行验证，再停止相关进程，确认入口仍是符号链接：

```bash
ls -ld ~/pb2025_ws
readlink -f ~/pb2025_ws
```

确认后由使用者切换入口：

```bash
ln -sfnT ~/gmk-navigation/releases/reality-n100-20261031 ~/pb2025_ws
```

需要恢复旧源码入口时：

```bash
ln -sfnT ~/gmk-navigation/releases/9fe99d1ea1b5 ~/pb2025_ws
```

切换符号链接不会改变已运行进程、系统库、网络设置或旧 `/home/rm/start_all.sh` 的仿真启动逻辑。首次按本文手动启动验证，之后再按实际需求调整开机服务。原无线套件仍可用于原仿真流程。
