#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PB_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
export PB_ROOT

BUILD_JOBS="${BUILD_JOBS:-2}"
COLCON_JOBS="${COLCON_JOBS:-2}"
CLEAN=0

usage() {
  cat <<'EOF'
Usage: scripts/build_all.sh [--clean]

Builds and installs the bundled Livox-SDK2 and small_gicp, then builds all
ROS 2 packages in this workspace. Set BUILD_JOBS and COLCON_JOBS to adjust
parallelism. --clean removes only generated ROS build, install, and log dirs.
EOF
}

die() {
  printf 'build_all.sh: %s\n' "$*" >&2
  exit 1
}

for arg in "$@"; do
  case "$arg" in
    --clean) CLEAN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $arg" ;;
  esac
done

[[ -f /opt/ros/humble/setup.bash ]] || die "ROS 2 Humble is not installed at /opt/ros/humble"
[[ -d "$PB_ROOT/third_party/Livox-SDK2" ]] || die "missing third_party/Livox-SDK2"
[[ -d "$PB_ROOT/third_party/small_gicp" ]] || die "missing third_party/small_gicp"
command -v cmake >/dev/null || die "cmake is not installed"
command -v colcon >/dev/null || die "colcon is not installed"

mkdir -p "$PB_ROOT/runtime"/{tmp,cache,config,data,ros,ros_logs,colcon}
source "$PB_ROOT/scripts/env.sh"

if ! [[ "$BUILD_JOBS" =~ ^[1-9][0-9]*$ && "$COLCON_JOBS" =~ ^[1-9][0-9]*$ ]]; then
  die "BUILD_JOBS and COLCON_JOBS must be positive integers"
fi

if (( CLEAN )); then
  printf '%s\n' 'Removing generated ROS build, install, and log directories...'
  rm -rf -- "$PB_ROOT/build" "$PB_ROOT/install" "$PB_ROOT/log"
fi

if (( EUID == 0 )); then
  run_privileged() { "$@"; }
else
  command -v sudo >/dev/null || die "sudo is required to install libraries into /usr/local"
  sudo -v || die "sudo authorization failed"
  run_privileged() { sudo "$@"; }
fi

SDK_BUILD="$PB_ROOT/build-deps/Livox-SDK2"
GICP_BUILD="$PB_ROOT/build-deps/small_gicp"

printf '%s\n' 'Building and installing Livox-SDK2...'
cmake -S "$PB_ROOT/third_party/Livox-SDK2" \
  -B "$SDK_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/usr/local
cmake --build "$SDK_BUILD" --parallel "$BUILD_JOBS"
run_privileged cmake --install "$SDK_BUILD"

printf '%s\n' 'Building and installing small_gicp...'
cmake -S "$PB_ROOT/third_party/small_gicp" \
  -B "$GICP_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/usr/local \
  -DCMAKE_INSTALL_LIBDIR=lib \
  -DBUILD_TESTS=OFF \
  -DBUILD_EXAMPLES=OFF \
  -DBUILD_BENCHMARKS=OFF \
  -DBUILD_PYTHON_BINDINGS=OFF
cmake --build "$GICP_BUILD" --parallel "$BUILD_JOBS"
run_privileged cmake --install "$GICP_BUILD"
run_privileged ldconfig

printf '%s\n' 'Building the ROS 2 workspace...'
colcon --log-base "$PB_ROOT/log" build \
  --base-paths "$PB_ROOT/src" \
  --build-base "$PB_ROOT/build" \
  --install-base "$PB_ROOT/install" \
  --symlink-install \
  --parallel-workers "$COLCON_JOBS" \
  --cmake-args \
    -DCMAKE_BUILD_TYPE=Release \
    -DROS_EDITION=ROS2 \
    -DDISTRO_ROS=humble \
    -DPython3_EXECUTABLE=/usr/bin/python3 \
    -DPYTHON_EXECUTABLE=/usr/bin/python3 \
    -DBUILD_TESTING=OFF

[[ -f "$PB_ROOT/install/setup.bash" ]] || die "ROS workspace build completed without install/setup.bash"
printf '\nBuild complete. In each new terminal run:\n  source %q\n  source %q\n' \
  "$PB_ROOT/scripts/env.sh" "$PB_ROOT/install/setup.bash"
