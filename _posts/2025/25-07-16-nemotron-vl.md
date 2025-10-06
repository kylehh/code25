---
title: Video support in Nemontron Nano VL
mathjax: true
toc: true
categories:
  - OSS
tags:
  - VLM
---

The PR for Nemotron Nano VL is still on going. There are more modifications as below
(Finally merged after I just finished this blog)
## 1 InternVL's video extention
Nemotron's support in Video is questionable, and the benchmark is "calculated with 1 tile per image". So I removed all the video related code, and here are some notes
1. The `BaseInternVLxxx` classes are for image-only
- `BaseInternVLProcessingInfo`
- `BaseInternVLDummyInputsBuilder`
- `BaseInternVLMultiModalProcessor`
2. `InternVLxxxx(BaseInternVLxxx)` are extended for video support
- `InternVLProcessingInfo(BaseInternVLProcessingInfo)`
- `InternVLDummyInputsBuilder(BaseInternVLDummyInputsBuilder)`
- `InternVLMultiModalProcessor(BaseInternVLMultiModalProcessor)`
3. Instead of inheritate from `InternVLxxx` and remove video support, the code should directly inheritate from `BaseInternVL`
4. Base classes are directly used in the decrator now
```python
@MULTIMODAL_REGISTRY.register_processor(
    BaseInternVLMultiModalProcessor[NemotronVLProcessingInfo],
    info=NemotronVLProcessingInfo,
    dummy_inputs=BaseInternVLDummyInputsBuilder[NemotronVLProcessingInfo])
class LlamaNemotronVLChatModel(nn.Module, SupportsMultiModal, SupportsPP,
                               SupportsLoRA):
```
## 2 Adding test dependency 
CI test failed with dependance, to fix it
- add dep at `requirements/test.in`
- run `pre-commit` and call `pip-compile` to generate `requirments/test.txt`
- Copy over `test.txt` from CI if it still failed pre-commit
- Fixed a bug in `docker/Dockerfile.cpu`
## 3 Config attributes mapping
We actually do NOT need to copy the [configuration.py](https://huggingface.co/nvidia/Llama-3.1-Nemotron-Nano-VL-8B-V1/blob/main/configuration.py) from HF just because of some attributes name mismatch.
- No `Llama_Nemotron_Nano_VL_Config` defined under `vllm/transformers_utis/config/nemotron_vl_config.py`
- No `Llama_Nemotron_Nano_VL_Config` referred under `vllm/transformers_utis/config/__init__.py`
- No `Llama_Nemotron_Nano_VL_Config` registerd in the `_CONFIG_REGISTRY` under `vllm/transformers_utis/config.py`
- Add Following mapping code to make the HF config to work under `vllm/transformers_utis/config.py`
```python
_CONFIG_ATTRS_MAPPING: dict[str, str] = {
    "llm_config": "text_config",
}
```
## 4 Class inheritance
Try to inheritage as much as possible to avoid write duplicate codes. The processor class can be directly inheritaged from `InternVLProcessor` but need to override methods as needed
```python
class NemotronVLProcessor(InternVLProcessor):
    def __init__(...):
      # This is combining InternVLProcessor.__init__ and BaseInternVLProcessor.__init__
    def _preprocess_image(...):
      # Due to Nemotron is using <image> as IMG_CONTEXT, which has conflict with vLLM's image placeholder
    @property
    def image_token_id(self) -> int:
      # Due to different IMG_CONTEXT from InternVL
    def get_image_repl(...):
      # Due to different IMG_CONTEXT from InternVL
```
## 5 LoRa support
The LoRA support does NOT actually need to be tested with LoRA adapters
It just need to test with engine initialization in `api_server.py`
```python
async def run_server(args, **uvicorn_kwargs) -> None:
    """Run a single-worker API server."""
    args.model="nvidia/Llama-3.1-Nemotron-Nano-VL-8B-V1"
    args.enable_lora=True
    args.trust_remote_code=True
    logger.info("args: %s", args)
    ...
```

## Appendix. 
1. Here is the working code for `nemotron_vl.py` with video code, in case we need to add back video support in the future
- gist [link](https://gist.github.com/kylehh/87451fc5e6b6390409963eeaf5cadbf4)
2. Here is the slights modified `nemotron_vl_config.py` with slightly modifed code
- gist [link](https://gist.github.com/kylehh/c0e76323f628207a58528ea64d98ccc0)