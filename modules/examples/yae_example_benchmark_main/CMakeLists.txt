cmake_minimum_required(VERSION 3.20)
include(set_compiler_options)
set(module_source_files
    ${CMAKE_CURRENT_SOURCE_DIR}/code/private/yae_example_benchmark_main.cpp)
add_executable(yae_example_benchmark_main ${module_source_files})
set_generic_compiler_options(yae_example_benchmark_main PRIVATE)
target_link_libraries(yae_example_benchmark_main PUBLIC benchmark::benchmark_main)
target_include_directories(yae_example_benchmark_main PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/code/public)
target_include_directories(yae_example_benchmark_main PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/code/private)
