cmake_minimum_required(VERSION 3.8)
project(pb_nav_decision)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
ament_python_install_package(${PROJECT_NAME})
install(PROGRAMS scripts/nav_decision scripts/mock_robot_status scripts/record_goals
  DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY launch config DESTINATION share/${PROJECT_NAME})
install(FILES README.md DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(decision_tree test/test_decision_tree.py
    APPEND_ENV PYTEST_DISABLE_PLUGIN_AUTOLOAD=1)
  # ROS action integration tests are run separately in an isolated ROS domain.
endif()
ament_package()
