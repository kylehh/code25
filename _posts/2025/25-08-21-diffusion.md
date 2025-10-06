---
title: Flow and Diffusion models Part 1 - Flow and Diffusion 
mathjax: true
toc: true
categories:
  - Study
tags:
  - VLM
---

Will start to review Diffusion series from 苏神 [blog](https://kexue.fm/archives/9119). But then I realized that SDE, Langevin and Flow models, are things taught in statiscal mechanics which Im not familiar with. So I decided to take MIT [course](https://diffusion.csail.mit.edu/) on Diffusion  

## 0 Engery based model
There was a series about energy model and GAN. [I](https://kexue.fm/archives/6316),[II](https://kexue.fm/archives/6331),[III](https://kexue.fm/archives/6612).
- Energy model == Generative model
- Energy is defined as below
![Alt text](/code23/assets/images/2025/25-08-21-diffusion_files/energy.png)

It needs some knowlege about Langevin equation, and I will leave it for the future

## 1 Flow model
Thare some key concepts in flow model which are similar to path/velocity 
- Trajectory: It's the path consistents of states from different t
- Vector Field: It's the velocity which is not consistent, depends on t and state
- ODE: Ordinary Differencial Equations, this is the physcal law behind this problem.
![Alt text](/code23/assets/images/2025/25-08-21-diffusion_files/ode.png)
- Flow: It is the collections of trajectories. So we can get any trajectory by giving the start state $x_o$ and time t
![Alt text](/code23/assets/images/2025/25-08-21-diffusion_files/flow.png)
Here is the relationship between these concept: **vector fields define ODEs whose solutions are flows.**
![Alt text](/code23/assets/images/2025/25-08-21-diffusion_files/relationship.png)

Then the course talked about the existence and uniqueness of the solution, which is for mathmatical rigorness. For ML, we just need to know there exist an solution, which is unique.
And through **Euler method**, we can simply simulate the ODE

Now let's define **flow model**, which is to let the final trajectory $x_t$ to be a sample in the designed data distribution
![Alt text](/code23/assets/images/2025/25-08-21-diffusion_files/flowmodel.png)
Similiar to how we simulate ODE, the sampling of the flow can be achieved by following algorithm, obviously.
![Alt text](/code23/assets/images/2025/25-08-21-diffusion_files/sampleflow.png)
## 2 Brownian motion
Learned Brownian motion for a long time but first time know it's description in math. 
-  It's a fundamental stochastic process that cameout of the study physical **diffusion** processes
- A Brownian motion $W = (W_t)_{0≤t≤1}$ always have $W_0=0$
- Normal increments: $W_t−W_s∼\mathcal{N}(0,(t−s)I_d)$ for all 0≤s<t
- Independent increments: For any 0 ≤ t0 < t1 < ...< tn =1, the increments $W_{t_1}−W_{t_0}$,...,$W_{t_n}−W_{t_{n−1}}$ are independent
random variables.

Brownian motion is also called a **Wiener process**, which is why we denote it with a "W".

## 3 Diffusion Model
Now we use SDE to replace ODE in the flow model so that we can get diffusion models, with a diffusion coefficient $\sigma_t$
![Alt text](/code23/assets/images/2025/25-08-21-diffusion_files/sde.png)
Since we can NOT use derivatives for a stachastic process. so let's rewrite both ODE and SDE without derivatives. 
![Alt text](/code23/assets/images/2025/25-08-21-diffusion_files/noderivatives.png)
Since $W_{t+h}−W_t∼\mathcal{N}(0,hI_d)$, so we get the following sampling for diffusion models 
![Alt text](/code23/assets/images/2025/25-08-21-diffusion_files/samplediffusion.png)

Now we can set initial trajectory $x_0$ is sampled from random noise, final trajectory $x_t$ to be data sample, we can get diffusion model, and flow model is a special case of it, which has zero diffusion coeff.
![Alt text](/code23/assets/images/2025/25-08-21-diffusion_files/summary.png)


