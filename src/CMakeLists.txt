set(EXE_SOURCES
    "main.cpp"
)
set(EXE_INCLUDES
    "./"
)

add_executable(${EXECUTABLE_NAME} ${EXE_SOURCES})

target_include_directories(${EXECUTABLE_NAME} PUBLIC
    ${EXE_INCLUDES}
)

target_link_libraries(${EXECUTABLE_NAME}
    ${Python3_LIBRARIES}
)

# Bake in absolute paths so the embedded interpreter finds its stdlib (PY_HOME)
# and this project's deps (PY_VENV_SITE_PACKAGES) regardless of the working
# directory or CMake generator (Makefiles vs Xcode).
target_compile_definitions(${EXECUTABLE_NAME} PRIVATE
    PY_HOME="${PYTHON_BASE_PREFIX}"
    PY_VENV_SITE_PACKAGES="${CMAKE_SOURCE_DIR}/.venv/lib/python${Python3_VERSION_MAJOR}.${Python3_VERSION_MINOR}/site-packages"
)

if(ENABLE_WARNINGS)
    target_set_warnings(
        ${EXECUTABLE_NAME}
        ON
        OFF
    )
endif()
