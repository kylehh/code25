---
title: Flow and Diffusion models Part 3 - Langevin and Matching
mathjax: true
toc: true
categories:
  - Study
tags:
  - LLM
---

[Lecture 3](https://www.maartengrootendorst.com/blog/quantization/). 
Finished Lab 1, implemented flow and diffusion models and implemented Langevin Dynamics

## 0 Langevin Dynamics
Setting $p_t=p$ constant, and let $u^{target}=0$, we can have a special case of Langevin Dynamics
![Alt text](/code23/assets/images/2025/25-08-30-diffusion_files/langevin.png)

We can approve that it's a special case of OU process when setting zero mean and $\frac{\sigma^2}{2\theta}$ var
![Alt text](/code23/assets/images/2025/25-08-30-diffusion_files/ou.png)

## 1 Flow Matching
Flow matching is actually **vector field** matching used on flow model training
![Alt text](/code23/assets/images/2025/25-08-30-diffusion_files/fm.png)
Unfortunately, the marginal vector field is intractable, we have to turn to **Conditional Flow Matching**
![Alt text](/code23/assets/images/2025/25-08-30-diffusion_files/cfm.png)
And we can approve these two loss are only differ by a constant,
![Alt text](/code23/assets/images/2025/25-08-30-diffusion_files/equal.png)

Here is an example of applying to Guassion case
![Alt text](/code23/assets/images/2025/25-08-30-diffusion_files/gfm.png)
With chosen noise schedular, we can get the **CondOT**, Optimal Transport (OT)
![Alt text](/code23/assets/images/2025/25-08-30-diffusion_files/condot.png)
The final formula is actually so simple, using a network to matching a straightline
![Alt text](/code23/assets/images/2025/25-08-30-diffusion_files/simple.png)

## 2 Score Matching
Very similiarly, we can use conditional score matching, which is called **denoising score matching** to replace intractable marginal score matching. 
![Alt text](/code23/assets/images/2025/25-08-30-diffusion_files/sm.png)
and the loss functions are only diff by a constant
![Alt text](/code23/assets/images/2025/25-08-30-diffusion_files/constant.png)

In the Gaussian example, you can also get a simply expression
![Alt text](/code23/assets/images/2025/25-08-30-diffusion_files/sdesimple.png)
In the DDPM paper, it actually is the same with the formula above. This is more straighforward as prediction for the noise. 
![Alt text](/code23/assets/images/2025/25-08-30-diffusion_files/ddpm.png)
Now we can get the algrithm for training. Still not sure how the plus sign in the loss function works for score matching. predicting the nagative noise?
![Alt text](/code23/assets/images/2025/25-08-30-diffusion_files/sdetrain.png)

After getting both vector field by flow matching, and score function by score matching, we can get the final formula for SDE. 
![Alt text](/code23/assets/images/2025/25-08-30-diffusion_files/2models.png)
But in pratice, you only need to train one model, score function, instead of two
![Alt text](/code23/assets/images/2025/25-08-30-diffusion_files/1model.png)
Because simple algebra can get the conversion of these two
![Alt text](/code23/assets/images/2025/25-08-30-diffusion_files/conversion.png)
