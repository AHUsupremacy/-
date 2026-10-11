# 当前安装步骤

> 此文件记录原验证机 `/home/frank/beijixiong` 的操作。新机器克隆后应使用仓库根目录代替该绝对路径，并重新构建两个库及 ROS 包；不要假设克隆仓库包含原机器的 `build-deps`。PCD 文件未上传。

更新：2026-10-08。所有系统目录安装由用户执行；本次没有执行 sudo、apt 或 pip 安装。

## 已准备的项目内容

- 15 个固定提交的 ROS 仓库已放到 `/home/frank/beijixiong/src`，没有重复包；两份 PCD 已复制到导航包的 `pcd/simulation`。
- Livox-SDK2：`third_party/Livox-SDK2`，提交 `08f523c930b2f0ba1e98a6afaa8d7476bf479908`，CHANGELOG 为 1.4.3（不是正式 tag）。
- small_gicp：`third_party/small_gicp`，提交 `2c6c7831bc1f5ada2ee5300027fe7d7aee66827d`。
- 两个库的构建目录为 `build-deps/Livox-SDK2` 和 `build-deps/small_gicp`，安装目标为 `/usr/local`。
- 两个库均已编译成功（退出码 0），尚未执行系统安装；新 SDK 对原始驱动 `pub_handler.cpp` 的 C++14 接口检查通过。
- 已准备 Livox ROS2 manifest；不应用旧 SDK 兼容补丁。
- 重定位改用 C++17 和系统安装的 `small_gicp::small_gicp`，不再在线拉取 master。
- 仿真移除了 RPLIDAR 实例和桥接，保留单 MID360；实车 `xfer_format` 改为 1。模型移除了零值 `offset_timestamp`，使用官方 Humble joint_state_publisher。

旧 ZIP 保留，但不参与本次构建。仿真/实机尚未启动验证。

## 1. 安装缺少的系统依赖

在当前机器终端执行：

```bash
sudo apt update
sudo apt install \
  ros-humble-navigation2 \
  ros-humble-nav2-bringup \
  ros-humble-slam-toolbox \
  ros-humble-pcl-ros \
  ros-humble-ros-gz-sim \
  ros-humble-ros-gz-bridge \
  ignition-fortress \
  libignition-gazebo6-dev \
  libignition-msgs8-dev \
  libignition-transport11-dev \
  libomp-dev \
  libapr1-dev
```

这些包在当前机器尚未安装；此前 apt 模拟检查已通过，无需额外添加软件源。Eigen3、PCL、OpenCV、glog、libunwind、编译器、CMake、colcon 和 ROS Humble 基础环境已经存在。

## 2. 安装 xmacro

```bash
Y
```

使用系统 Python，避免裸 `python3` 指向另一套解释器。该安装写入用户目录，由用户执行。

## 3. 安装已构建的 SDK 和 small_gicp

无需重新下载或解压，也无需迁移其他机器的 SDK。以下命令将项目内构建产物安装到 `/usr/local`：

```bash
export PB_ROOT=/home/frank/beijixiong
sudo cmake --install "$PB_ROOT/build-deps/Livox-SDK2"
sudo cmake --install "$PB_ROOT/build-deps/small_gicp"
sudo ldconfig
```

如需要重新构建，先执行以下项目内命令，再执行上面的安装命令：

```bash
source /home/frank/beijixiong/scripts/env.sh
cmake -S "$PB_ROOT/third_party/Livox-SDK2" \
  -B "$PB_ROOT/build-deps/Livox-SDK2" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local
cmake --build "$PB_ROOT/build-deps/Livox-SDK2" --parallel 2
cmake -S "$PB_ROOT/third_party/small_gicp" \
  -B "$PB_ROOT/build-deps/small_gicp" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local \
  -DCMAKE_INSTALL_LIBDIR=lib \
  -DBUILD_TESTS=OFF -DBUILD_EXAMPLES=OFF \
  -DBUILD_BENCHMARKS=OFF -DBUILD_PYTHON_BINDINGS=OFF
cmake --build "$PB_ROOT/build-deps/small_gicp" --parallel 2
```

## 4. 检查系统安装

```bash
source /home/frank/beijixiong/scripts/env.sh
ros2 pkg prefix nav2_bringup
ros2 pkg prefix slam_toolbox
ros2 pkg prefix pcl_ros
ros2 pkg prefix ros_gz_sim
ros2 pkg prefix ros_gz_bridge
/usr/bin/python3 -c 'from xmacro.xmacro4sdf import XMLMacro4sdf'
pkg-config --modversion ignition-gazebo6 ignition-msgs8 ignition-transport11 apr-1
ls /usr/local/include/livox_lidar_api.h \
   /usr/local/include/livox_lidar_def.h \
   /usr/local/lib/liblivox_lidar_sdk_shared.so \
   /usr/local/lib/cmake/small_gicp/small_gicp-config.cmake
ldd /usr/local/lib/liblivox_lidar_sdk_shared.so
ldd /usr/local/lib/libsmall_gicp.so
```

输出不应出现缺包或 `not found`。安装完成后告知我，我会继续 ROS 构建和修复实际编译问题。

## 5. 后续项目内 ROS 构建

系统安装完成后的构建命令如下，构建、安装和日志目录都在 beijixiong 内：

```bash
source /home/frank/beijixiong/scripts/env.sh
cd "$PB_ROOT"
colcon list --base-paths src
colcon --log-base "$PB_ROOT/log" build \
  --base-paths "$PB_ROOT/src" \
  --build-base "$PB_ROOT/build" \
  --install-base "$PB_ROOT/install" \
  --symlink-install --parallel-workers 2 \
  --cmake-args -DCMAKE_BUILD_TYPE=Release \
  -DROS_EDITION=ROS2 -DDISTRO_ROS=humble \
  -DPython3_EXECUTABLE=/usr/bin/python3 \
  -DPYTHON_EXECUTABLE=/usr/bin/python3 \
  -DBUILD_TESTING=OFF
source "$PB_ROOT/install/setup.bash"
```

首次 ROS 构建前还要核实其他 manifest 依赖。导航配置含 intensity 过滤参数，当前 pointcloud_to_laserscan 固定提交未实现此过滤；SLAM 运行前需要处理该项。完整构建通过不等于导航或硬件运行通过。

仅需要网页控制时，再安装可选依赖：

```bash
/usr/bin/python3 -m pip install --user Flask Flask-SocketIO Flask-Cors python-engineio
```
