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

# Point the runtime PYTHONPATH at the site-packages for the *linked* Python
# version, so the embedded interpreter and its deps can never mismatch.
target_compile_definitions(${EXECUTABLE_NAME} PRIVATE
    PY_VENV_SITE_PACKAGES=".venv/lib/python${Python3_VERSION_MAJOR}.${Python3_VERSION_MINOR}/site-packages"
)

if(ENABLE_WARNINGS)
    target_set_warnings(
        ${EXECUTABLE_NAME}
        ON
        OFF
    )
endif()
