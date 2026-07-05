cmake_minimum_required(VERSION 3.20)
include(set_compiler_options)
set(module_source_files
    ${CMAKE_CURRENT_SOURCE_DIR}/code/private/yae_example_benchmark.cpp)
add_executable(yae_example_benchmark ${module_source_files})
set_generic_compiler_options(yae_example_benchmark PRIVATE)
target_link_libraries(yae_example_benchmark PUBLIC benchmark::benchmark)
target_include_directories(yae_example_benchmark PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/code/public)
target_include_directories(yae_example_benchmark PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/code/private)
