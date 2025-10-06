---
title: Deterministic in LLM
mathjax: true
toc: true
categories:
  - Study
tags:
  - LLM
---

Deterministic in LLM is a much harder problem than I initially thought. I was working with a major customer SN for a couple of months for this issues and eventually escalated to VP level to get it sorted it out. Recenlty, thinkinglab published their first [blog](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/) about it and here are some notes I took.

## 1 What's Deterministic in LLM
Following statements can be all true at the same time
1. Some kernels on GPUs are **nondeterministic**.
2. However, all the kernels used in a language model’s forward pass are **deterministic**.
3. Moreover, the forward pass of an LLM inference server (like vLLM) can also be claimed to be **deterministic**.
4. Nevertheless, from the perspective of anybody using the inference server, the results are **nondeterministic**.

## 2 Cause of non-deterministic
1. The culprit is floating-point **non-associativity**. 
```python
(0.1 + 1e20) - 1e20
>>> 0
0.1 + (1e20 - 1e20)
>>> 0.1
```
2. “atomic add” (sometimes known as a “fetch-and-add”) is “nondeterministic”. 
For example the `torch.sum()` ensures every element will be  reflected in the final sum, but it makes no guarantee about what *order* the contributions will be added. 
Howevery, in the typical forward pass of an LLM, **there is usually not a single atomic add present**.
![Alt text](/code23/assets/images/2025/25-09-12-deterministic_files/model.png)
3. Batch invariance and “determinism”
The **primary reason** nearly all LLM inference endpoints are nondeterministic is that the load (and thus batch-size) nondeterministically varies. It also happens to CPU and TPU
```python
import torch
torch.set_default_device('cuda') 
B = 2048
D = 4096
a = torch.linspace(-1000, 1000, B*D).reshape(B, D)
b = torch.linspace(-1000, 1000, D*D).reshape(D, D)
# Doing a matrix vector multiplication by taking
# the first element of the batch
out1 = torch.mm(a[:1], b) # (1,D)*(D,D)=(1,D)
# Doing a matrix matrix multiplication and then taking
# the first element of the batch
out2 = torch.mm(a, b)[:1] # (B,D)*(D,D)=(B,D)->(1,D)
print((out1 - out2).abs().max()) # tensor(1669.2500, device='cuda:0') ## This is huge!
```
## 3 How to create batch-invariant kernels
