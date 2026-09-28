cmake_minimum_required(VERSION 3.8)
project(prevera_bringup)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY launch config rviz udev
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
