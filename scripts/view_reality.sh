#!/usr/bin/env bash
# Laptop-only RViz for the existing GMK wireless kit. Starts no remote processes.
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PB_VIEW_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
KIT_DIR="${GMK_KIT_DIR:-$HOME/Desktop/GMK无线套件-队友版}"
CHECK_ONLY=0

usage() {
  cat <<'EOF'
Usage: bash scripts/view_reality.sh [--kit-dir DIRECTORY] [--check]

Runs real-time RViz on the laptop, using the existing kit's ROS domain,
lightweight view and TF relay. Does not start GMK navigation or simulation.
--check validates local dependencies without opening RViz or ROS nodes.
EOF
}

while (( $# )); do
  case "$1" in
    --kit-dir)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      KIT_DIR="$2"; shift 2 ;;
    --check) CHECK_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

for FILE in gmk_env.sh gmk_side/local_tf_relay.py rviz/gmk_nav_light.rviz; do
  [[ -f "$KIT_DIR/$FILE" ]] || { echo "Missing kit file: $KIT_DIR/$FILE" >&2; exit 1; }
done
[[ -f /opt/ros/humble/setup.bash ]] || { echo 'ROS 2 Humble is required on the laptop.' >&2; exit 1; }
source /opt/ros/humble/setup.bash
source "$KIT_DIR/gmk_env.sh"
export ROS_LOCALHOST_ONLY=0
command -v rviz2 >/dev/null
/usr/bin/python3 -c 'import rclpy; import yaml; from std_msgs.msg import String; from tf2_msgs.msg import TFMessage'
[[ -d "$KIT_DIR/resources/pb2025_ws/install" ]] || { echo 'Missing kit model resources.' >&2; exit 1; }

# Ensure the supplied light view still targets the topics used by these relays.
/usr/bin/python3 - "$KIT_DIR/rviz/gmk_nav_light.rviz" <<'PY'
import sys
import yaml
with open(sys.argv[1], encoding="utf-8") as stream:
    view = yaml.safe_load(stream)["Visualization Manager"]
assert any(d.get("Description Topic", {}).get("Value") == "/gmk_kit/robot_description"
           for d in view["Displays"]), "Unexpected kit RobotModel topic"
assert any(t.get("Topic", {}).get("Value") == "/red_standard_robot1/goal_pose"
           for t in view["Tools"]), "Unexpected kit goal topic"
PY

echo "Laptop real-robot view: ROS_DOMAIN_ID=$ROS_DOMAIN_ID, use_sim_time=false"
if (( CHECK_ONLY )); then
  echo 'Local checks passed; no ROS nodes, GUI or remote commands were started.'
  exit 0
fi
[[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] || { echo 'Run this viewer in the laptop desktop session.' >&2; exit 1; }
if pgrep -x rviz2 >/dev/null; then
  echo 'Close the existing RViz before starting the real-robot viewer.' >&2
  exit 1
fi

VIEW_PIDS=()
cleanup() {
  local VIEW_PID
  for VIEW_PID in "${VIEW_PIDS[@]}"; do kill "$VIEW_PID" 2>/dev/null || true; done
  for VIEW_PID in "${VIEW_PIDS[@]}"; do wait "$VIEW_PID" 2>/dev/null || true; done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Prefer the matching local build's assets, falling back to the kit's mesh files.
/usr/bin/python3 "$SCRIPT_DIR/reality_description_relay.py" \
  --resources "$PB_VIEW_ROOT/install" \
  --resources "$KIT_DIR/resources/pb2025_ws/install" &
VIEW_PIDS+=("$!")
/usr/bin/python3 "$KIT_DIR/gmk_side/local_tf_relay.py" &
VIEW_PIDS+=("$!")
export QT_QPA_PLATFORM=xcb
rviz2 -d "$KIT_DIR/rviz/gmk_nav_light.rviz" --ros-args \
  -p use_sim_time:=false -r __ns:=/red_standard_robot1 \
  -r /tf:=/gmk_kit/tf -r /tf_static:=/gmk_kit/tf_static &
VIEW_PIDS+=("$!")
echo 'Closing this RViz stops only the laptop display; GMK navigation continues.'
wait "${VIEW_PIDS[2]}"
