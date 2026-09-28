# PREVERA GUARDIAN+AI fall event emitted by perception stack.
# Patent pending. See NOTICE at the repository root.

# Alert level constants
uint8 NONE     = 0
uint8 OBSERVE  = 1   # unusual posture, monitor
uint8 WARN     = 2   # probable fall, escalate visual analysis
uint8 ALERT    = 3   # confirmed fall, notify staff
uint8 CRITICAL = 4   # confirmed fall + prolonged stillness

std_msgs/Header header

uint32 track_id
uint8  alert_level
float32 confidence              # 0.0 - 1.0

geometry_msgs/Point location    # in `map` frame if SLAM active, else `laser`
float32 horizontal_extent_m     # major-axis length of cluster
float32 elongation_ratio        # major / minor axis
float32 stillness_duration_s    # time since cluster last moved
float32 preceding_velocity_mps  # peak velocity in the last second before stillness

# Set by the V-JEPA verification stage (proprietary, not in this repository);
# the LIDAR detector publishes NaN.
float32 vjepa_confidence
