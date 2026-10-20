#!/usr/bin/env bash
set -e
decision_workspace="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$decision_workspace"
source "$decision_workspace/scripts/env.sh"
source "$decision_workspace/install/setup.bash"
exec ros2 launch pb_nav_decision decision_sim.launch.py "$@"
