cmake_minimum_required(VERSION 3.20)
include(set_compiler_options)
set(module_source_files
    ${CMAKE_CURRENT_SOURCE_DIR}/code/private/ecs_benchmark_main.cpp)
add_executable(ecs_benchmark ${module_source_files})
set_generic_compiler_options(ecs_benchmark PRIVATE)
target_link_libraries(ecs_benchmark PUBLIC benchmark::benchmark_main
                                           CppReflection
                                           unordered_dense
                                           ecs)
target_link_libraries(ecs_benchmark PRIVATE fmt)
target_include_directories(ecs_benchmark PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/code/public)
target_include_directories(ecs_benchmark PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/code/private)
