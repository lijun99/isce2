#include "cudaUtil.h"

#include <cuda_runtime.h>
#include <stdio.h>
#include <stdlib.h>
#include "cudaError.h"

int gpuDeviceInit(int devID)
{
    int device_count;
    checkCudaErrors(cudaGetDeviceCount(&device_count));

    if (device_count == 0) {
        fprintf(stderr, "gpuDeviceInit() CUDA error: no devices supporting CUDA.\n");
        exit(EXIT_FAILURE);
    }

    if (devID < 0 || devID > device_count - 1) {
        fprintf(stderr, "gpuDeviceInit() Device %d is not a valid GPU device. \n", devID);
        exit(EXIT_FAILURE);
    }

    checkCudaErrors(cudaSetDevice(devID));
    printf("Using CUDA Device %d ...\n", devID);

    return devID;
}

int gpuDeviceList()
{
    int deviceCount = 0;
    checkCudaErrors(cudaGetDeviceCount(&deviceCount));

    if (deviceCount == 0) {
        fprintf(stderr, "CUDA error: no devices supporting CUDA.\n");
    }
    else {
        fprintf(stderr, "Detected %d CUDA capable device%s:\n",
                deviceCount, (deviceCount == 1 ? "" : "s"));
        fprintf(stderr, " GPU  Name                                    SM Ver  #SMs\n");

        for (int dev = 0; dev < deviceCount; ++dev) {
            cudaDeviceProp prop {};
            checkCudaErrors(cudaGetDeviceProperties(&prop, dev));

            fprintf(stderr, " %3d  %-36s  sm_%d%d  %4d\n",
                dev, prop.name, prop.major, prop.minor, prop.multiProcessorCount);
        }
    }
    return deviceCount;
}

int getSMCount(int devID)
{
    // Get the ID of the currently active CUDA device
    checkCudaErrors(cudaGetDevice(&devID));

    // Retrieve device properties
    cudaDeviceProp prop;
    checkCudaErrors(cudaGetDeviceProperties(&prop, devID));

    // Return the SM (Streaming Multiprocessor) count
    return prop.multiProcessorCount;
}