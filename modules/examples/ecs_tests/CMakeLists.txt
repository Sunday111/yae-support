cmake_minimum_required(VERSION 3.20)
include(set_compiler_options)
set(module_source_files
    ${CMAKE_CURRENT_SOURCE_DIR}/code/private/app_tests.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/code/private/test_app.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/code/private/test_app.hpp
    ${CMAKE_CURRENT_SOURCE_DIR}/code/private/test_components.hpp)
add_executable(ecs_tests ${module_source_files})
set_generic_compiler_options(ecs_tests PRIVATE)
target_link_libraries(ecs_tests PUBLIC ecs
                                       gtest_main)
target_link_libraries(ecs_tests PRIVATE fmt)
target_include_directories(ecs_tests PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/code/public)
target_include_directories(ecs_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/code/private)
enable_testing()
include(GoogleTest)
gtest_discover_tests(ecs_tests)
