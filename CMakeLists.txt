cmake_minimum_required(VERSION 3.22)

project(Sample
    VERSION 1.0.0
    LANGUAGES C CXX
    DESCRIPTION "A sample project embedding Python in C++"
)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS ON)

# Use the project's virtualenv Python (if present) so the linked interpreter and
# the site-packages loaded at runtime are the SAME version — no ABI mismatch.
set(Python3_FIND_VIRTUALENV FIRST)
if(EXISTS "${CMAKE_SOURCE_DIR}/.venv/bin/python")
    set(Python3_EXECUTABLE "${CMAKE_SOURCE_DIR}/.venv/bin/python" CACHE FILEPATH "venv python" FORCE)
elseif(EXISTS "${CMAKE_SOURCE_DIR}/.venv/Scripts/python.exe")
    set(Python3_EXECUTABLE "${CMAKE_SOURCE_DIR}/.venv/Scripts/python.exe" CACHE FILEPATH "venv python" FORCE)
endif()

set(LIBRARY_NAME "Library" CACHE STRING "Name of the library target")
set(EXECUTABLE_NAME "main" CACHE STRING "Name of the executable target")

find_package(Python3 COMPONENTS Interpreter Development REQUIRED)

include_directories(${Python3_INCLUDE_DIRS})

add_subdirectory(src)

message(STATUS "Project: ${PROJECT_NAME} v${PROJECT_VERSION}")
message(STATUS "C++ Standard: ${CMAKE_CXX_STANDARD}")
message(STATUS "Python: ${Python3_EXECUTABLE} (version ${Python3_VERSION})")
