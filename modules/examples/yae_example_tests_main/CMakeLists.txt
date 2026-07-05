cmake_minimum_required(VERSION 3.20)
include(set_compiler_options)
set(module_source_files
    ${CMAKE_CURRENT_SOURCE_DIR}/code/private/yae_example_tests_main.cpp)
add_executable(yae_example_tests_main ${module_source_files})
set_generic_compiler_options(yae_example_tests_main PRIVATE)
target_link_libraries(yae_example_tests_main PUBLIC yae_example_library
                                                    yae_example_header_only
                                                    gtest_main)
target_include_directories(yae_example_tests_main PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/code/public)
target_include_directories(yae_example_tests_main PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/code/private)
enable_testing()
include(GoogleTest)
gtest_discover_tests(yae_example_tests_main)
