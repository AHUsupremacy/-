# 依赖与构建

全新 Ubuntu 22.04 + ROS 2 Humble 环境的系统依赖安装、Livox-SDK2 和 small_gicp 构建安装、PCD 准备及 ROS 工作区构建步骤统一维护在 [README.md](README.md)。请按 README 第 1～5 节顺序执行。

安装命令会写入系统软件包目录或 `/usr/local`，由部署者在目标机器执行。项目源码、CMake 构建目录、ROS `build`、`install` 和 `log` 均位于工作区；PCD 不由 Git 分发。
