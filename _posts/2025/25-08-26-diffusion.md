---
title: Flow and Diffusion models Part 2 - Fokker-Planck
mathjax: true
toc: true
categories:
  - Study
tags:
  - VLM
---

[Lecture 2](https://www.youtube.com/watch?v=VDnM5D6wXio&t)
This is the most mathmatical chanllenging part of the lecture, but also covers all the missing knowledge I would like to learn, like Langevin and Fokker-Planck

## 1 Training goal
Review two models we learned so far
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/2models.png)
Learning goal is to find the formula for the target vector field such that corresponding ODE/SDE convert $p_{init}$ to $p_{data}$
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/traininggoal.png)

Two key concepts
- conditional: per single data point
- marginal: across distribution of all data points

## 2 Probability Path
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/probpath.png)
For conditional probability path
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/cpp.png)
We have a example of Gaussian prob path with noise schedule s.t
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/gpp.png)
For marginal probablity path, this is a bit hard to digest. The key idea is to understand probability path as **a trajectory in the space of distributions**. 
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/mpp.png)
The density $p_t(x)$ is unkonw because the integral is intractable.

## 3 Vector Field
If we simulate a ODE with a conditional vector field, then any state on the trajectory is following conditional probabilty path. 
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/cvf.png)
The Gaussian example is given by 
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/gvf.png)
The Marginalization Trick, which can be approved by Continuity equation, 
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/mvf.png)

Here is the comparison of these two under ODE samples
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/odesamples.png)

## 4 Continuity Equation
CE can be interpreated by the conservation of probability mass. 
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/ce.png)
From this equation, we can derive the marginalization trick

## 5 Score Function
Score function is defined as the grad of the log of the density.
and marginal score can be get from conditional score
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/score.png)
Now we do SDE extension trick. When there is diffusion terms added in the SDE, the vector field should be adjusted accordingly, so the same condition holds as in the marginalization trick.
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/sdeex.png)

## 6 Fokker-Planck Equation
SDE extension trick can be approved by Fokker-Planck equation, which is the SDE version of the continuity equation.
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/fpe.png)
And the physical interpretation is adding heat dispersion
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/heat.png)
The proof of SDE extension is a bit confusing to me. It actually starts from continuity equation, and then satisfied with Fokker-Planck equation... 

## 7 Summary
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/s1.png)
![Alt text](/code23/assets/images/2025/25-08-26-diffusion_files/s2.png)
