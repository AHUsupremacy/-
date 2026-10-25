cmake_minimum_required(VERSION 3.8)
project(pb_chassis_serial)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

ament_python_install_package(${PROJECT_NAME})

install(
  PROGRAMS scripts/chassis_serial_bridge
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
