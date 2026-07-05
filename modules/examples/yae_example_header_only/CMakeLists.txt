cmake_minimum_required(VERSION 3.20)
include(set_compiler_options)
set(module_source_files
    ${CMAKE_CURRENT_SOURCE_DIR}/code/public/yae_example_header_only/yae_example_header_only.hpp)
add_library(yae_example_header_only INTERFACE ${module_source_files})
set_generic_compiler_options(yae_example_header_only INTERFACE)
target_link_libraries(yae_example_header_only INTERFACE yae_example_library)
target_include_directories(yae_example_header_only INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/code/public)
target_include_directories(yae_example_header_only INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/code/private)
