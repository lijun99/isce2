# Early exit if prereqs not available
if(NOT TARGET GDAL::GDAL
OR NOT TARGET CUDA::cufft
OR NOT pybind11_FOUND
   )
    message(STATUS "Skipping PyCuAmpcor build due to missing prerequisites (GDAL, CUDA, or pybind11)")
    return()
endif()

message(STATUS "Found CUDA version: ${CUDAToolkit_VERSION}")
# Set C++ standard based on CUDA version
if (CUDAToolkit_VERSION VERSION_GREATER_EQUAL 13.0)
    # CUDA 13 and later requires at least C++17
    set(CMAKE_CUDA_STANDARD 17)
    set(CMAKE_CUDA_STANDARD_REQUIRED ON)

    # Also set host compiler C++ standard
    set(CMAKE_CXX_STANDARD 17)
    set(CMAKE_CXX_STANDARD_REQUIRED ON)

    message(STATUS "Using C++17 because CUDA 13+ requires it")
else()
    # For older CUDA versions (and e.g. GCC 4.8)
    set(CMAKE_CUDA_STANDARD 11)
    set(CMAKE_CUDA_STANDARD_REQUIRED ON)

    set(CMAKE_CXX_STANDARD 11)
    set(CMAKE_CXX_STANDARD_REQUIRED ON)

    message(STATUS "Using C++11 for compatibility (CUDA < 13)")
endif()

pybind11_add_module(PyCuAmpcor
    src/PyCuAmpcor.cpp
    src/GDALImage.cpp
    src/SConscript
    src/cuAmpcorChunk.cpp
    src/cuAmpcorController.cpp
    src/cuAmpcorParameter.cpp
    src/cuArrays.cpp
    src/cuArraysCopy.cu
    src/cuArraysPadding.cu
    src/cuCorrFrequency.cu
    src/cuCorrNormalization.cu
    src/cuCorrNormalizationSAT.cu
    src/cuCorrNormalizer.cpp
    src/cuCorrTimeDomain.cu
    src/cuDeramp.cu
    src/cuEstimateStats.cu
    src/cuOffset.cu
    src/cuOverSampler.cpp
    src/cuSincOverSampler.cu
    src/cudaError.cpp
    src/cudaUtil.cpp
    )
target_include_directories(PyCuAmpcor PRIVATE
    src
    )
target_link_libraries(PyCuAmpcor PRIVATE
    CUDA::cufft
    GDAL::GDAL
    )

InstallSameDir(
    __init__.py
    PyCuAmpcor
    )
