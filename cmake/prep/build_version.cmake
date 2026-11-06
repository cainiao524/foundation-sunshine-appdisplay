# Explicit CI versions also apply to release branches and detached source commits.
if((DEFINED ENV{BUILD_VERSION}) AND (NOT "$ENV{BUILD_VERSION}" STREQUAL ""))
    MESSAGE("Got explicit CI version $ENV{BUILD_VERSION}")
    set(PROJECT_VERSION "$ENV{BUILD_VERSION}")
    set(CMAKE_PROJECT_VERSION "${PROJECT_VERSION}")  # cpack will use this to set the binary versions
elseif((DEFINED ENV{BRANCH}) AND (DEFINED ENV{COMMIT}))
    MESSAGE("Got from CI $ENV{BRANCH} branch and commit $ENV{COMMIT}")
    set(PROJECT_VERSION "${PROJECT_VERSION}.$ENV{COMMIT}")
else()
    # Generate Sunshine Version based of the git tag.
    # https://github.com/nocnokneo/cmake-git-versioning-example/blob/master/LICENSE
    find_package(Git)
    string(TIMESTAMP COMPILE_TIME "%Y.%m%d.%H%M%S")
    set(PROJECT_VERSION ${COMPILE_TIME})
    if(GIT_EXECUTABLE)
        MESSAGE("${CMAKE_SOURCE_DIR}")
        get_filename_component(SRC_DIR "${CMAKE_SOURCE_DIR}" DIRECTORY)
        #Get current Branch
        execute_process(
                COMMAND ${GIT_EXECUTABLE} rev-parse --abbrev-ref HEAD
                OUTPUT_VARIABLE GIT_DESCRIBE_BRANCH
                RESULT_VARIABLE GIT_DESCRIBE_ERROR_CODE
                OUTPUT_STRIP_TRAILING_WHITESPACE
        )
        # Gather current commit
        execute_process(
                COMMAND ${GIT_EXECUTABLE} rev-parse --short HEAD
                OUTPUT_VARIABLE GIT_DESCRIBE_VERSION
                RESULT_VARIABLE GIT_DESCRIBE_ERROR_CODE
                OUTPUT_STRIP_TRAILING_WHITESPACE
        )
        # Check if Dirty
        execute_process(
                COMMAND ${GIT_EXECUTABLE} diff --quiet --exit-code
                RESULT_VARIABLE GIT_IS_DIRTY
                OUTPUT_STRIP_TRAILING_WHITESPACE
        )
        if(NOT GIT_DESCRIBE_ERROR_CODE)
            MESSAGE("Sunshine Branch: ${GIT_DESCRIBE_BRANCH}")
            if(NOT GIT_DESCRIBE_BRANCH STREQUAL "master")
                set(PROJECT_VERSION ${PROJECT_VERSION}.${GIT_DESCRIBE_VERSION})
                MESSAGE("Sunshine Version: ${GIT_DESCRIBE_VERSION}")
            endif()
            if(GIT_IS_DIRTY)
                set(PROJECT_VERSION ${PROJECT_VERSION}.杂鱼)
                MESSAGE("Git tree is dirty!")
            endif()
        else()
            MESSAGE(ERROR ": Got git error while fetching tags: ${GIT_DESCRIBE_ERROR_CODE}")
        endif()
    else()
        MESSAGE(WARNING ": Git not found, cannot find git version")
    endif()
endif()
