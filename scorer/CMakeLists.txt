cmake_minimum_required(VERSION 3.16)
project(autolabeler_eval_scorer CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

add_compile_options(-Wall -Wextra)

option(ENABLE_ASAN "Build with AddressSanitizer + UndefinedBehaviorSanitizer" OFF)
option(BUILD_TESTS "Build the GoogleTest suite" ON)

if(ENABLE_ASAN)
  add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer -g -O1)
  add_link_options(-fsanitize=address,undefined)
endif()

add_library(scorer_core STATIC
  src/types.cpp
  src/matcher.cpp
)
target_include_directories(scorer_core PUBLIC include)

add_executable(scorer_cli src/main.cpp)
target_link_libraries(scorer_cli PRIVATE scorer_core)

if(BUILD_TESTS)
  enable_testing()
  include(FetchContent)
  FetchContent_Declare(
    googletest
    URL https://github.com/google/googletest/archive/refs/tags/v1.15.2.zip
  )
  set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
  set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(googletest)

  add_executable(scorer_tests
    tests/test_types.cpp
    tests/test_matcher.cpp
  )
  target_link_libraries(scorer_tests PRIVATE scorer_core gtest_main)
  include(GoogleTest)
  gtest_discover_tests(scorer_tests)
endif()
