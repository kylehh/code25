---
title: VLM Nemotron-Nano-VL-8B support
mathjax: true
toc: true
categories:
  - OSS
tags:
  - VLM
---

I started working on this a month ago since [Nemotron-Nano-VL-8B-V1](https://huggingface.co/nvidia/Llama-3.1-Nemotron-Nano-VL-8B-V1) released. I thought it would be a good choice for me to add a model from scratch, and get better undertanding of vLLM workflow. 

It's kind of funny that there are two merges since I submitted the [PR](https://github.com/vllm-project/vllm/pull/20349/) and they are kind of related to the work here. 

OK, here are the steps of adding support for a VLM model in vLLM

## 1 Model Configs
This model has its now config class `Llama_Nemotron_Nano_VL_Config` defined in [HF](https://huggingface.co/nvidia/Llama-3.1-Nemotron-Nano-VL-8B-V1/blob/main/configuration.py). So we need to convert this into vLLM's configs.
1. Define `Llama_Nemotron_Nano_VL_Config` inside `vllm/transformers_utils/configs` folder
I basically added the HF code into the `nemotron.py` file and the only changes are using `text_config` instead of `llm_config`, which will referred later in vLLM config code.
```
class Llama_Nemotron_Nano_VL_Config(PretrainedConfig):
  def __init__(...):
    # use text_config instead of llama_config
    if llm_config is None:
        #self.llm_config = LlamaConfig()
        self.text_config = LlamaConfig()
    else:
        #self.llm_config = LlamaConfig(**llm_config)
        self.text_config = LlamaConfig(**llm_config)
```
This code is mimic the `InternVLChatConfig` defined [here](https://github.com/vllm-project/vllm/blob/v0.9.1/vllm/transformers_utils/configs/internvl.py). But this [PR](https://github.com/vllm-project/vllm/pull/19992) removed this config for InternVL models. Will keep my config for now and see how it goes
2. Add `Llama_Nemotron_Nano_VL_Config` in `vllm/transformers_utils/config.py`
```python
from vllm.transformers_utils.configs import Llama_Nemotron_Nano_VL_Config
_CONFIG_REGISTRY: dict[str, type[PretrainedConfig]] = {
    ...
    "Llama_Nemotron_Nano_VL": Llama_Nemotron_Nano_VL_Config
}
```
3. There is `RADIOConfig` for the embedding video file define in [HF](https://huggingface.co/nvidia/C-RADIOv2-H/blob/main/hf_model.py) and it will be read in automatically when initializing `Llama_Nemotron_Nano_VL_Config`
```python
class Llama_Nemotron_Nano_VL_Config(PretrainedConfig):
  def __init__(self,...):
      ...
      if vision_config is not None:
          assert "auto_map" in vision_config and "AutoConfig" in vision_config[  # noqa: E501
              "auto_map"]
          vision_auto_config = get_class_from_dynamic_module(
              *vision_config["auto_map"]["AutoConfig"].split("--")[::-1])
          self.vision_config = vision_auto_config(**vision_config)
      else:
          self.vision_config = PretrainedConfig()
```
Here the `vision_config` is from the `config.json` file in HF, and it points to the C-RADIO config and model.
So it will read from `hf_model.py` under `nvidia/C-RADIOv2-H`
```sh
  "vision_config": {
    "auto_map": {
      "AutoConfig": "nvidia/C-RADIOv2-H--hf_model.RADIOConfig",
      "AutoModel": "nvidia/C-RADIOv2-H--hf_model.RADIOModel"
    }
    ...
  }
```
## 2 Multimodal placeholder
This is one changed I made but the latest vLLM [PR](https://github.com/vllm-project/vllm/pull/20355/) simplified the process.
1. Originally we need to add this model under `vllm/entrypoint/chat_utils.py` for placeholder
2. Now it moves to model defination to define the placeholder string.
```python
class Llama_Nemotron_Nano_VL_Model(...):
    @classmethod
    def get_placeholder_str(cls, modality: str, i: int) -> Optional[str]:
        if modality.startswith("image"):
            return "<image>"
        if modality.startswith("video"):
            return "<video>"

        raise ValueError("Only image or video modality is supported")
```
## 3 Model Registration
Since this model is based on InternVL, so the main model file is based on [internvl.py](https://github.com/vllm-project/vllm/blob/main/vllm/model_executor/models/internvl.py)
1. Added in `registry.py` under `vllm/model_executor/models/` folder
```python
_MULTIMODAL_MODELS = {
    # [Decoder-only]
    "Llama_Nemotron_Nano_VL": ("nemotron_vl", "Llama_Nemotron_Nano_VL_Model"),
    ...
}
```
2. Added `nemotron_vl.py` under `vllm/model_executor/models/` folder
- Change `IMG_CONTEXT` according to `tokenizer_config.json`. For InternVL, we can see it's defined as below. But I don't find it form the Nemotron model. Maybe `<image>` is used as default
```sh
    "151667": {
      "content": "<IMG_CONTEXT>",
      "lstrip": false,
      "normalized": false,
      "rstrip": false,
      "single_word": false,
      "special": true
    },
```
- Get config properly mapped.  
 Actually some of the config are not defined in `config.json` as InternVL but defined in `preprocessor_config.json`, which should be read differently based on [my previous post](https://kylehh.github.io/code23/2025/06/30/preprocessing-config/). So leave them as hard coded for now.
```python
class BaseInternVLProcessor(ABC):
    def __init__(...) -> None:
        super().__init__()
        self.config = config
        self.tokenizer = tokenizer
        image_size: int = config.force_image_size  #512
        patch_size: int = config.patch_size  #16
        if min_dynamic_patch is None:
            min_dynamic_patch = 1  #config.min_dynamic_patch
        assert isinstance(min_dynamic_patch, int)
        if max_dynamic_patch is None:
            max_dynamic_patch = 12  #config.max_dynamic_patch
        assert isinstance(max_dynamic_patch, int)
        if dynamic_image_size is None:
            dynamic_image_size = True  #config.dynamic_image_size
        assert isinstance(dynamic_image_size, bool)
```  
- Define the key model class `Llama_Nemotron_Nano_VL_Model`.  
Update The vision model. I used to copied all code from RADIOModel but changed to use `AutoModel` instead. 
```python
  def _init_vision_model():
      # return RADIOModel(config.vision_config,
      #                   quant_config=quant_config,
      #                   prefix=prefix)
      from transformers import AutoModel
      return AutoModel.from_config(config.vision_config, trust_remote_code=True)
```
- Update the key model class based on the HF code.  
HF repo has the [modeling.py](https://huggingface.co/nvidia/Llama-3.1-Nemotron-Nano-VL-8B-V1/blob/main/modeling.py) defined the exactly how the model should be processed. So update following to functions accordingly. Mostly is mapping config properly. 
And also removed any code related is `self.is_mono`
```python
    def _init_mlp1(self, config: PretrainedConfig) -> nn.Sequential:
    def extract_feature(self, pixel_values: torch.Tensor) -> torch.Tensor:
```
- Model loading  
This one took me a long time to debug (also learned how the model weights are loaded in vLLM). The actually fix is simple, just ignore attributes defined as `register_buffer`
```python
 def load_weights(..):
        ## Ignore registered_buffers
        ## see https://huggingface.co/nvidia/C-RADIOv2-H/blob/main/input_conditioner.py#L28 # noqa: E501
        skip_substrs = ["norm_mean", "norm_std"]
        loader = AutoWeightsLoader(self, skip_substrs=skip_substrs)
        return loader.load_weights(weights)
```