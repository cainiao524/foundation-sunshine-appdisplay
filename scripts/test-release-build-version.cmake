# Exercise release branch and detached-checkout versions without a full build.
set(ENV{BRANCH} "release/app-display")
set(ENV{BUILD_VERSION} "v4.9.杂鱼")
set(ENV{COMMIT} "abcdef1234567890abcdef1234567890abcdef12")
set(PROJECT_VERSION "old-version")
include("${CMAKE_CURRENT_LIST_DIR}/../cmake/prep/build_version.cmake")
if(NOT "${PROJECT_VERSION}" STREQUAL "v4.9.杂鱼" OR
   NOT "${CMAKE_PROJECT_VERSION}" STREQUAL "v4.9.杂鱼")
    message(FATAL_ERROR "The explicit release branch version was discarded")
endif()

unset(ENV{BRANCH})
unset(ENV{COMMIT})
set(ENV{BUILD_VERSION} "v5.0.杂鱼")
include("${CMAKE_CURRENT_LIST_DIR}/../cmake/prep/build_version.cmake")
if(NOT "${PROJECT_VERSION}" STREQUAL "v5.0.杂鱼" OR
   NOT "${CMAKE_PROJECT_VERSION}" STREQUAL "v5.0.杂鱼")
    message(FATAL_ERROR "An explicit version must also work without branch metadata")
endif()

set(ENV{BRANCH} "pull-request")
set(ENV{COMMIT} "abc1234")
set(ENV{BUILD_VERSION} "")
set(PROJECT_VERSION "2027.0101")
include("${CMAKE_CURRENT_LIST_DIR}/../cmake/prep/build_version.cmake")
if(NOT "${PROJECT_VERSION}" STREQUAL "2027.0101.abc1234")
    message(FATAL_ERROR "The version fallback lost its source commit")
endif()
message(STATUS "Release build version tests passed")
