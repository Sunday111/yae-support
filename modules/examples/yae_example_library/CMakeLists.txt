cmake_minimum_required(VERSION 3.20)
include(set_compiler_options)
set(module_source_files
    ${CMAKE_CURRENT_SOURCE_DIR}/code/private/yae_example_library.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/code/public/yae_example_library/yae_example_library.hpp)
add_library(yae_example_library STATIC ${module_source_files})
set_generic_compiler_options(yae_example_library PRIVATE)
target_include_directories(yae_example_library PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/code/public)
target_include_directories(yae_example_library PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/code/private)
