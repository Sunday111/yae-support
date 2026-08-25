cmake_minimum_required(VERSION 3.20)

include(CheckLinkerFlag)

function(enable_debug_info_compression_for target_name)
    foreach(compression_format zstd zlib)
        set(support_variable "yae_linker_supports_${compression_format}_debug_info_compression")
        check_linker_flag(
            CXX
            "LINKER:--compress-debug-sections=${compression_format}"
            ${support_variable})
        if(${support_variable})
            target_link_options(
                ${target_name}
                PRIVATE "LINKER:--compress-debug-sections=${compression_format}")
            return()
        endif()
    endforeach()

    message(STATUS "Debug information compression is not supported for ${target_name}")
endfunction()
