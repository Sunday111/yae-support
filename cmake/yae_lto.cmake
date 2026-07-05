cmake_minimum_required(VERSION 3.16)

include(CheckIPOSupported)

# Check for lto support only once and save the value in cache
if (NOT DEFINED yae_lto_supported)
    check_ipo_supported(RESULT ipo_supported OUTPUT lto_supported_output)
    SET(yae_lto_supported ${ipo_supported} CACHE INTERNAL "yae_lto_supported")
    SET(yae_lto_supported_output "${lto_supported_output}" CACHE INTERNAL STRING "yae_lto_supported_output")
    if (yae_lto_supported)
        message(STATUS "LTO is supported")
    else()
        message(WARNING "Could not enable LTO. Debug info here: ${yae_lto_supported_output}")
    endif()
endif()

function(enable_lto_globally)
    if (NOT yae_lto_supported)
        return()
    endif()

    if(POLICY CMP0069)
        cmake_policy(SET CMP0069 NEW)
        set(CMAKE_POLICY_DEFAULT_CMP0069 NEW)
    endif(POLICY CMP0069)

    set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE CACHE BOOL "Enable LTO globally")
endfunction(enable_lto_globally)

function(disable_lto_globally)
    if(POLICY CMP0069)
        cmake_policy(SET CMP0069 NEW)
        set(CMAKE_POLICY_DEFAULT_CMP0069 NEW)
    endif(POLICY CMP0069)

    set(CMAKE_INTERPROCEDURAL_OPTIMIZATION FALSE CACHE BOOL "Enable LTO globally")
endfunction()

function(enable_lto_for target_name)
    if (yae_lto_supported)
        set_property(TARGET ${target_name} PROPERTY INTERPROCEDURAL_OPTIMIZATION TRUE)
    endif()
endfunction()
