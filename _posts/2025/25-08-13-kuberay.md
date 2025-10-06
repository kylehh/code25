---
title: KubeRay Setup and Trouble shooting
mathjax: true
toc: true
categories:
  - Study
tags:
  - Ray/Anyscale
---

Trying to get a 2 node 8 GPU (4 GPU from each node) Ray cluster running with KubeRay

## 1 KubeRay configuration
We can customize the `value.yaml` and deploy Ray cluster with KubyRay Operator
```sh
helm install my-ray-cluster kuberay/ray-cluster -f my-value.yaml
```
and this is the sample values
```yaml
image:
  repository: vllm/vllm-openai
  tag: latest
# Head group configuration
head:
  nodeSelector:
    kubernetes.io/hostname: dgx-001
  useHostNetwork: true
  resources:
    requests:
      cpu: "16"
      memory: "64Gi"
      nvidia.com/gpu: "4"
    limits:
      cpu: "16"
      memory: "64Gi"
      nvidia.com/gpu: "4"
  containerEnv:
  - name: "CUDA_VISIBLE_DEVICES"
    value: "0,1,2,3"
worker:
  nodeSelector:
    kubernetes.io/hostname: dgx-002
  useHostNetwork: true
  resources:
    requests:
      cpu: "16"
      memory: "64Gi"
      nvidia.com/gpu: "4"
    limits:
      cpu: "16"
      memory: "64Gi"
      nvidia.com/gpu: "4"
  containerEnv:
  - name: "CUDA_VISIBLE_DEVICES"
    value: "4,5,6,7"
```

## 2 Troubleshooting
1. The deployment was failed on worker group does not have node assigned. 
After `describe` the node, you will see following `Allocated resources` section at the end
and there is NO `nvidia.com/gpu` for this node
```sh
│ Allocated resources: 
│   Resource           Requests Limits
│   cpu                355m (0%)   100m
│   memory             576Mi (0%)  1Gi 
│   ephemeral-storage  0 (0%)      0
│   hugepages-1Gi      0 (0%)      0
│   hugepages-2Mi      0 (0%)      0
│   nvidia.com/gpu     0           0   # was not here
```
This is due to not install [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) properly. So fix it by `sudo apt-get install -y nvidia-container-toolkit` (see more details at the link).  

Then I was checking with following cmds to see if the toolkit is properly installed.
```sh
systemctl status nvidia-container-runtime
# This command always shows NOT Found
#Unit nvidia-container-runtime.service could not be found.
systemctl list-units --type=service | grep nvidia
# This command list nvidia services
#nvidia-dcgm.service          NVIDIA DCGM service
#nvidia-fabricmanager.service NVIDIA fabric manager service
#nvidia-persistenced.service  NVIDIA Persistence Daemon
```
2. To install `fabric manager`
```sh
# To list all the available fabric manager version under 570
apt-cache madison cuda-drivers-fabricmanager-570
sudo apt-get install cuda-drivers-fabricmanager-570
#570.158.01 to be installed by default but 570.172.08 is GPU driver version
cat /proc/driver/nvidia/version
```
Here is how re-install GPU driver 
```sh
# remove current driver
sudo apt-get purge nvidia*
# install drive with specific versoin
apt-cache madison nvidia-driver-570
sudo apt install nvidia-driver-570=570.124.06-0ubuntu1
```

## 3 Container Runtime update
The service file `nvidia-container-runtime.service` likely doesn't exist. In modern versions (like 1.17+), a persistent, standalone service is **no longer required**. The toolkit now integrates directly with your container runtime (Docker, containerd) through configuration.

The goal is not to start a service, but to configure your container engine to use the NVIDIA runtime.
```sh
# 1 Reload
sudo systemctl daemon-reload
# 2 Update
# Use this command if you are using Docker
sudo nvidia-ctk runtime configure --runtime=docker
# Or use this command if you are using containerd
# sudo nvidia-ctk runtime configure --runtime=containerd
# 3 Restart
# For Docker
sudo systemctl restart docker
# For containerd
# sudo systemctl restart containerd
```
You can check following files see the nvidia runtime being used
```sh
cat /etc/docker/daemon.json
cat /etc/containerd/config.toml
```

## 4 Key update
```sh
sudo apt-key list
distro=ubuntu2204
arch=x86_64
wget https://developer.download.nvidia.com/compute/cuda/repos/$distro/$arch/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
```