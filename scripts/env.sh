# Source this file before building or running the workspace.
export PB_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$PB_ROOT/runtime"/{tmp,cache,config,data,ros,ros_logs,colcon}
export TMPDIR="$PB_ROOT/runtime/tmp"
export XDG_CACHE_HOME="$PB_ROOT/runtime/cache"
export XDG_CONFIG_HOME="$PB_ROOT/runtime/config"
export XDG_DATA_HOME="$PB_ROOT/runtime/data"
export ROS_HOME="$PB_ROOT/runtime/ros"
export ROS_LOG_DIR="$PB_ROOT/runtime/ros_logs"
export COLCON_HOME="$PB_ROOT/runtime/colcon"
export PYTHONDONTWRITEBYTECODE=1
export CMAKE_BUILD_PARALLEL_LEVEL=2
source /opt/ros/humble/setup.bash
