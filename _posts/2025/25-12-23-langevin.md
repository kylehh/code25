---
title: Langevin Sampling in Diffuion models
mathjax: true
toc: true
categories:
  - Study
tags:
  - VLM
---

This youtuber only uploaded 3 videos and one of them explained [score matching](https://www.youtube.com/watch?v=Fk2I6pa6UeA) better than any others and finally I am ready to read Dr Yang Song's [paper](https://arxiv.org/pdf/1907.05600) and [blog](https://yang-song.net/blog/2021/score/)

## 0 Model Classifications
- Likelihood-based models, which directly learn the distribution’s PDF via (approximate) maximum likelihood., like AR, VAEs, EBMs and normalizing flow models 
- Implicit generative models, where the probability distribution is implicitly represented by a model of its sampling process, like GAN
![Alt text](/code25/assets/images/2025/25-12-23-langevin_files/models.png)

## 1 Langevin Sampling
To sample from a distribution w known pdf, we can use following algorithm:
![Alt text](/code25/assets/images/2025/25-12-23-langevin_files/langevin.png)
where $F(x)=\nabla_x\log(p(x))$, is just the **score function**
Here is the sample code of running Langevin Sampling on a uniform distribution over dice rolling
![Alt text](/code25/assets/images/2025/25-12-23-langevin_files/langevin.png)
Here are 2 things to notice
1. Why we need the log? It can make sure converge fast, especially when p(x) is small
![Alt text](/code25/assets/images/2025/25-12-23-langevin_files/log.png)
$$F(x)= \frac{d}{dx}\log(p(x)) \\  
      =\frac{p(x)}{p(x)} \\
      =\frac{\nabla_xp(x)}{p(x)}  
$$
2. The noise term is to make sure we are getting a distribution, rather than focused on highest percentage points.
![Alt text](/code25/assets/images/2025/25-12-23-langevin_files/nonoise.png)
What if the PDF is unknown? That's where DL comes to the rescue
![Alt text](/code25/assets/images/2025/25-12-23-langevin_files/unknown.png)
## 2 Image Generation
Recap this youtubers' first [video](https://www.youtube.com/watch?v=1pgiu--4W3I) on diffusion, the idea is very straightforward. 
- Diffusion process is highly similar to ML training process
![Alt text](/code25/assets/images/2025/25-12-23-langevin_files/ml.png)
- Predicting noise, is actually finding the direction to the valid image cluster in the image space 
![Alt text](/code25/assets/images/2025/25-12-23-langevin_files/recap.png)
The noise is playing a critical role in the diffusion models in following ways
1. As we shown above, ensure diversity. and also avoid local optima, anohter ML similarity
![Alt text](/code25/assets/images/2025/25-12-23-langevin_files/localoptima.png)
2. If we remove the noise, you will see the blurr image. which is explained in previous blog 
![Alt text](/code25/assets/images/2025/25-12-23-langevin_files/blurr.png)
3. The diffusion is for "logical" part, and noise is for creativity
![Alt text](/code25/assets/images/2025/25-12-23-langevin_files/creativity.png)
So now you will see diffusion is essencially same as finding the weight in DL training
![Alt text](/code25/assets/images/2025/25-12-23-langevin_files/dl.png)