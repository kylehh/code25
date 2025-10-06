---
title: Flow and Diffusion models Part 4 - Classifer-Free Guidence
mathjax: true
toc: true
categories:
  - Study
tags:
  - LLM
---

[Lecture 4](https://www.maartengrootendorst.com/blog/quantization/). 

## 1 Guided Modeling
Going to unconditional to conditional is to add condition on lable y for all the formulas. To avoid confusion, we change the wording to **guided** and now is to find the loss function of it
![Alt text](/code23/assets/images/2025/25-09-06-diffusion_files/unguided.png)

By fixing y first to reuse the unguided formula, and varying y to get the guided version by using conditional probabilities.
![Alt text](/code23/assets/images/2025/25-09-06-diffusion_files/guided.png)

## 2 Classifier Guidance
The method above was soon empirically realized that images samples with this procedure did NOT fit well enough to the desired label y. The perceptual quality is increased when the effect of the guidance variable y is artificially reinforced. Here is how we can enhance the effective of y.

First recall the relationship between vector field and score function for Gaussian conditional probability path.
![Alt text](/code23/assets/images/2025/25-09-06-diffusion_files/relationship.png)

Simply pluging Bayes' rule, and notice gradient is respect to x only, so we can get $\nabla{\log{p_t(y)}} = 0$, thus
![Alt text](/code23/assets/images/2025/25-09-06-diffusion_files/bayes.png)
Here $\nabla{\log{p_t(y|x)}}$ is sort of a **classifer**.  
Early works actually trained a classifer, and this leads to classifier guidience method.
![Alt text](/code23/assets/images/2025/25-09-06-diffusion_files/cg.png)

## 2 Classifier-Free Guidance
The key conversion to get classifier-free formula is just applying this Bayes conversion.
![Alt text](/code23/assets/images/2025/25-09-06-diffusion_files/bayes1.png)
and some algebra can totally remove the classifier term
![Alt text](/code23/assets/images/2025/25-09-06-diffusion_files/cfg.png)
In practice, instead of training two models, we can converge into a single model by introducing a nothing class
![Alt text](/code23/assets/images/2025/25-09-06-diffusion_files/nothing.png)

Here is the summary of the training process, which is referred to CFM training we derived before
![Alt text](/code23/assets/images/2025/25-09-06-diffusion_files/algorithm.png)

## 3 CFG for Diffusion process
The derive for score matching and diffusion process is actually more easiy, directly play with the Bayes formula
![Alt text](/code23/assets/images/2025/25-09-06-diffusion_files/bayes2.png)
So the CFG for diffusion score matching is 
![Alt text](/code23/assets/images/2025/25-09-06-diffusion_files/dsm.png)

