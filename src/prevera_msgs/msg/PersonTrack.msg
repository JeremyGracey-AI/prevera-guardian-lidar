# A single tracked cluster from the 2D LIDAR perception stack.
# Emitted every scan for every active track.

std_msgs/Header header

uint32 track_id
geometry_msgs/Point    centroid
geometry_msgs/Vector3  velocity

float32 horizontal_extent_m
float32 elongation_ratio
float32 age_s
bool    is_still
