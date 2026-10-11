# 依赖与部署

完整、适用于全新 Ubuntu 22.04 机器的安装和构建步骤已统一到 [README.md](README.md)。请按 README 第 1～6 节顺序执行。

本仓库不包含预编译产物或 PCD。Livox-SDK2 和 small_gicp 必须先从 third_party 构建，再安装到 /usr/local；ROS 源码在 src 下，构建和安装产物在工作目录内。README 中的 PB_ROOT 根据实际克隆位置计算，不依赖原验证机的用户名。
