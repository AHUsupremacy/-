# 北极熊哨兵仿真与导航

本仓库收录已在 Ubuntu 22.04、ROS 2 Humble、Gazebo Fortress 环境中完成编译并由用户验证仿真导航可运行的源码。`src/` 是 15 个固定提交的 ROS 仓库（29 个 ROS 包），`third_party/` 是 Livox-SDK2 和 small_gicp 的源码。解压原始 ZIP 后完成的 ROS2 manifest、单 MID360 仿真、实机参数以及 small_gicp 构建适配已包含在这些源码中。

原始仓库的许可文件保留在各自目录。Livox-SDK2 固定在提交 `08f523c930b2f0ba1e98a6afaa8d7476bf479908`（该提交的 CHANGELOG 为 1.4.3，无同名正式 tag），livox_ros_driver2 固定在 `4a1def929e5b59c7a8122d19fce6efba581ce9f7`。其他源码的固定版本见各目录原始内容和部署记录。

## 地图数据

按上传要求，本仓库**不包含 PCD 文件**。运行 `rmuc_2025` 导航前，需单独将已验证的 `rmuc_2025.pcd` 放在：

```text
src/pb2025_sentry_nav/pb2025_nav_bringup/pcd/simulation/rmuc_2025.pcd
```

其他场地的 PCD 同样须单独提供，并与二维栅格地图匹配。缺少 PCD 时可构建源码，但不能直接运行依赖该 PCD 的重定位导航。

## 构建

在 Ubuntu 22.04 + ROS 2 Humble 上安装 ROS 导航、Gazebo Fortress、APR/OpenMP 和 Python xmacro 等依赖。详细包名见 [INSTALL_DEPENDENCIES.md](INSTALL_DEPENDENCIES.md)；该文件记录了原验证机的绝对路径，新机器应替换为自己的克隆路径。源码应放在同一工作目录下的 `src/` 和 `third_party/`，无需再次嵌套。

先在当前工作目录构建 Livox-SDK2 和 small_gicp，并由系统管理员安装到 `/usr/local`：

```bash
export PB_ROOT="$PWD"
cmake -S "$PB_ROOT/third_party/Livox-SDK2" -B "$PB_ROOT/build-deps/Livox-SDK2" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local
cmake --build "$PB_ROOT/build-deps/Livox-SDK2" --parallel 2
cmake -S "$PB_ROOT/third_party/small_gicp" -B "$PB_ROOT/build-deps/small_gicp" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_INSTALL_LIBDIR=lib -DBUILD_TESTS=OFF -DBUILD_EXAMPLES=OFF -DBUILD_BENCHMARKS=OFF -DBUILD_PYTHON_BINDINGS=OFF
cmake --build "$PB_ROOT/build-deps/small_gicp" --parallel 2
sudo cmake --install "$PB_ROOT/build-deps/Livox-SDK2"
sudo cmake --install "$PB_ROOT/build-deps/small_gicp"
sudo ldconfig
```

然后构建 ROS 工作区：

```bash
source "$PB_ROOT/scripts/env.sh"
colcon --log-base "$PB_ROOT/log" build --base-paths "$PB_ROOT/src" --build-base "$PB_ROOT/build" --install-base "$PB_ROOT/install" --symlink-install --parallel-workers 2 --cmake-args -DCMAKE_BUILD_TYPE=Release -DROS_EDITION=ROS2 -DDISTRO_ROS=humble -DPython3_EXECUTABLE=/usr/bin/python3 -DPYTHON_EXECUTABLE=/usr/bin/python3 -DBUILD_TESTING=OFF
source "$PB_ROOT/install/setup.bash"
```

`scripts/env.sh` 将构建与运行临时数据指向工作目录内的 `runtime/`。如该目录尚不存在，先执行 `mkdir -p runtime/{tmp,cache,config,data,ros,ros_logs,colcon}`。

## 已验证的仿真启动

分别在两个终端运行，终端都需要先 `source scripts/env.sh` 和 `source install/setup.bash`：

```bash
ros2 launch rmu_gazebo_simulator bringup_sim.launch.py
ros2 launch pb2025_nav_bringup rm_navigation_simulation_launch.py
```

第二条命令使用默认 `rmuc_2025` 地图，必须先放入相应 PCD。实机迁移仍处于规划阶段，参见 [HARDWARE_MIGRATION.md](HARDWARE_MIGRATION.md)；当前仿真验证不等于实机已经验证。
