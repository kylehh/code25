---
title: ComfyUI
mathjax: true
toc: true
categories:
  - Application
tags:
  - VLM
---

It's time for a bit of fun after learning and coding with VLM for a while. ComfyUI and SB WebUI both has been very matured and quite some new models in the GenAI field.

## 0 Basic tips
- Model download  
 `huggingface-cli download --local-dir /raid/models/comfyui/models/ <repo> <path>`
- Model location  
  defined under `extra_model_paths.yaml`
- Custom Node  
  Clone Kijia's wrapper into `custom_nodes` fodler
- Add node manager  
  Clone Node manager into `custom_nodes` by `git clone https://github.com/ltdrdata/ComfyUI-Manager comfyui-manager`
## 1 Wan-2.1
Start with Wan-2.1 from Alibaba.
The ComfyUI [example](https://comfyanonymous.github.io/ComfyUI_examples/wan/) gives all you need to start a t2v or i2v
- Workflow `Comfy-Org/Wan_2.1_ComfyUI_repackaged example workflows_Wan2.1/image_to_video_wan_480p_example.json`
- Diffusion model `Comfy-Org/Wan_2.1_ComfyUI_repackaged split_files/diffusion_models/wan2.1_t2v_14B_fp16.safetensors`
- Clip vision `Comfy-Org/Wan_2.1_ComfyUI_repackaged split_files/clip_vision/clip_vision_h.safetensors`
- Text encoder `Comfy-Org/Wan_2.1_ComfyUI_repackaged split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors`
- VAE `Comfy-Org/Wan_2.1_ComfyUI_repackaged split_files/vae/wan_2.1_vae.safetensors`

Change FPS from 16 to 4 to get a longer video from picture
![Alt text](/code23/assets/images/2025/25-07-17-comfyui_files/i2vinput.png)
Video may not display properly online.
![Alt text](/code23/assets/images/2025/25-07-17-comfyui_files/i2v.mp4)

## 2 Flux Kontext
This model is from Black Forest Lab, Germany. And it's really advanced at picture modifications

The **workflow** is actually a picture.
![Alt Text](https://raw.githubusercontent.com/Comfy-Org/example_workflows/main/flux/kontext/dev/flux_1_kontext_dev_basic.png)

And model are listed under this [page](https://docs.comfy.org/tutorials/flux/flux-1-kontext-dev)
- Diffusion Model: `Comfy-Org/flux1-kontext-dev_ComfyUI split_files/diffusion_models/flux1-dev-kontext_fp8_scaled.safetensors`
- Text_encoder: `comfyanonymous/flux_text_encoders clip_l.safetensors t5xxl_fp8_e4m3fn_scaled.safetensors`
- VAE `Comfy-Org/Lumina_Image_2.0_Repackaged split_files/vae/ae.safetensors`

So I created a duck from the input picture style.
![Alt text](/code23/assets/images/2025/25-07-17-comfyui_files/fluxinput.png)
![Alt text](/code23/assets/images/2025/25-07-17-comfyui_files/fluxoutput.png)

## 3 MultiTalk
This would enable talking video through a picture, which is really what I needed.

- Workflow on Github Kijia's [WanVideoWrapper Mulitalk branch](https://github.com/kijai/ComfyUI-WanVideoWrapper/tree/multitalk) `example_workflows/wanvideo_multitalk_test_02.json`
- Diffusion model `Kijai/WanVideo_comfy WanVideo_2_1_Multitalk_14B_fp8_e4m3fn.safetensors`
- Diffusion on A100 fp16 `MeiGen-AI/MeiGen-MultiTalk multitalk.safetensors`
- LoRA `Kijai/WanVideo_comfy Wan21_T2V_14B_lightx2v_cfg_step_distill_lora_rank32.safetensors`

