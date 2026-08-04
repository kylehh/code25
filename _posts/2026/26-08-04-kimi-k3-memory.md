---
title: "Kimi K3: From KV Cache to Selective Memory"
mathjax: true
toc: true
categories:
  - Study
tags:
  - LLM
  - Attention
  - Inference
---

I read through this [Waterloo Intern thread](https://x.com/waterloo_intern/status/2081762065392541951) on Kimi K3 and turned it into my own learning notes.

The fun part is that Kimi K3 is not just "GPT-2, but 22,000x bigger". The more interesting path is:

```text
GPT-2 attention
  -> KV cache
  -> linear attention
  -> DeltaNet
  -> Gated DeltaNet
  -> Kimi Delta Attention
  -> Kimi Linear
  -> Kimi K3
```

The recurring theme is **selective memory**:

1. Store history cheaply.
2. Avoid old facts interfering with new facts.
3. Learn what to keep, replace, or forget.
4. Mix compressed recurrent memory with full attention when exact retrieval is worth the cost.

## 1 GPT-2 Baseline

GPT-2 is a decoder-only Transformer. For every token, each layer does self-attention and an MLP, then the final hidden state is projected into vocabulary logits.

The classic self-attention formula is:

$$
O = \text{softmax}\left(\frac{QK^T}{\sqrt{d}}\right)V
$$

The intuition:

1. The query asks what this token needs.
2. Keys describe what every token contains.
3. Values are the information to retrieve.
4. Softmax turns query-key similarities into weights.
5. The output is a weighted sum of values.

This is expressive because every token can directly retrieve from every previous token.

The downside is obvious at long context length. During prefill or training, all-pairs attention scales with the sequence length. During generation, the model can use a KV cache, but every new token still reads more cached history as the context grows.

## 2 KV Cache: Less Recompute, More Memory

Autoregressive decoding generates one token at a time. Without a cache, when the model predicts token $t+1$, it would recompute keys and values for tokens $1..t$.

KV cache stores the old keys and values:

```text
new token -> new q, k, v
old tokens -> cached K, V
new q attends over cached K, V
```

This removes redundant computation. It is one of the reasons decoder-only Transformers are practical for serving.

But it moves pressure onto memory:

```text
longer context -> larger KV cache -> more HBM traffic
```

So KV cache solves recomputation, but it does not make long-context memory free.

## 3 Linear Attention: Compress the History

Linear attention changes the storage format. Instead of keeping one KV pair per token, it compresses history into a recurrent state.

One common view is to replace softmax attention with a feature map $\phi$:

$$
\text{Attention}(q, K, V)
\approx
\frac{\phi(q)^T \sum_i \phi(k_i)v_i^T}{\phi(q)^T \sum_i \phi(k_i)}
$$

Then define:

$$
S_t = S_{t-1} + \phi(k_t)v_t^T
$$

$$
z_t = z_{t-1} + \phi(k_t)
$$

The output becomes:

$$
o_t = \frac{\phi(q_t)^T S_t}{\phi(q_t)^T z_t}
$$

The key idea is that all old tokens are folded into fixed-size states $S_t$ and $z_t$.

That is a big win for long-context serving. The model no longer needs a separate KV slot for every old token in every linear-attention layer.

The tradeoff: a fixed-size state has finite capacity. If we keep adding facts forever, different memories collide.

## 4 Linear Attention as Associative Memory

A useful mental model:

```text
write: S = S + outer(k, v)
read:  output = q^T S
```

This is like an associative memory. A key points to a value. A query similar to that key retrieves the value.

But the memory is not infinite. If many keys and values are added into the same matrix, the model gets interference:

```text
fact A + fact B + fact C + ... -> blurry mixed state
```

This is the core limitation that the DeltaNet family tries to address.

## 5 DeltaNet: Read Old, Write Difference

Plain linear attention writes by addition:

$$
S_{t} = S_{t-1} + k_t v_t^T
$$

DeltaNet makes the write corrective. Before writing a new value, it reads what the memory currently returns for that key:

$$
\hat{v}_t = S_{t-1}^T k_t
$$

Then it writes the difference:

$$
\Delta_t = v_t - \hat{v}_t
$$

$$
S_t = S_{t-1} + k_t \Delta_t^T
$$

The intuition:

```text
linear attention: add this fact
DeltaNet: make this key retrieve this value
```

That is more like editing a memory than appending to a log. If the current state already returns stale information for a key, the delta update corrects it.

## 6 Gated DeltaNet: Add Forgetting

Delta updates help with targeted replacement, but sometimes the model needs broader forgetting. For example, when a document switches topics, old context should decay unless it is still useful.

Gated DeltaNet adds a decay gate:

$$
S_t = \alpha_t S_{t-1} + \text{delta_write}_t
$$

When $\alpha_t$ is close to 1, memory persists.

When $\alpha_t$ is close to 0, memory fades.

This is a nice step, but a scalar or coarse gate forgets too broadly. Some channels may contain information that should persist, while other channels should be cleared.

## 7 Kimi Delta Attention: Fine-Grained Forgetting

Kimi Delta Attention (KDA) extends Gated DeltaNet with finer-grained gating.

The [Kimi Linear paper](https://arxiv.org/abs/2510.26692) describes KDA as a linear attention module that improves Gated DeltaNet with a more fine-grained gate, making better use of limited finite-state RNN memory.

The mental model:

```text
Gated DeltaNet:
  one broad forget knob

Kimi Delta Attention:
  many channel-wise forget knobs
```

So instead of fading the whole memory state uniformly, the model can preserve some channels while decaying others.

This is the important shift:

```text
fixed compressed memory
  -> editable memory
  -> gated memory
  -> fine-grained gated memory
```

KDA is not only a speed trick. It is a better memory update rule.

## 8 Chunking: Make the Recurrence GPU-Friendly

A pure recurrence is sequential:

```python
for token in sequence:
    update_state(token)
    emit_output(token)
```

That is simple, but GPUs prefer large matrix multiplies.

Kimi Linear uses a chunkwise algorithm: process blocks of tokens efficiently, then carry a compact recurrent state between blocks.

There is a tradeoff:

| Chunk Size | Behavior |
|---|---|
| Small | More recurrent, less parallel |
| Medium | Better tensor-core utilization |
| Large | Closer to full attention cost |

This is why long-context architecture is not just math. The algorithm has to match GPU hardware.

## 9 Kimi Linear: Hybrid Memory

If KDA is efficient, why keep full attention at all?

Because full attention is still excellent at explicit retrieval. Compressed recurrent memory is cheaper, but exact token-to-token retrieval can still matter.

Kimi Linear uses a hybrid:

```text
mostly KDA layers
periodic MLA / global-attention layers
```

The paper reports that Kimi Linear reduces KV cache usage by up to 75% and reaches up to 6x decoding throughput at a 1M-token context, while outperforming full MLA under their matched comparisons.

The practical lesson:

```text
use compressed memory for efficiency
keep occasional full attention for retrieval quality
```

## 10 Kimi K3: Scale the Pattern

The official [Kimi K3 repository](https://github.com/MoonshotAI/Kimi-K3) describes K3 as a 2.8T-parameter MoE model built on KDA and Attention Residuals.

Useful architecture numbers:

| Item | Value |
|---|---|
| Total parameters | 2.8T |
| Activated parameters | 104B |
| Layers | 93 |
| Attention composition | 69 KDA + 24 Gated MLA |
| Experts | 896 |
| Selected experts per token | 16 |
| Context length | 1,048,576 |
| Quantization | MXFP4 weights / MXFP8 activations |
| Modality | Text, Image |

The MoE design is another version of selective capacity:

```text
do not activate every parameter for every token
route each token to useful experts
```

So K3 applies selectivity across multiple dimensions:

| Dimension | Old Pattern | K3-Style Pattern |
|---|---|---|
| Sequence | keep every KV pair | recurrent KDA + periodic MLA |
| Depth | add every residual equally | Attention Residuals |
| Parameters | dense MLP everywhere | route to selected experts |

## 11 Attention Residuals: Selective Depth Memory

The [Attention Residuals paper](https://arxiv.org/abs/2603.15031) points out another accumulation problem.

PreNorm residual connections add layer outputs with fixed weight:

$$
h_l = h_0 + \sum_{i=1}^{l-1} f_i(h_i)
$$

As depth increases, this can dilute individual layer contributions and grow hidden-state magnitude.

Attention Residuals replace fixed accumulation with learned attention over previous layer outputs:

$$
h_l = \sum_i \alpha_{i,l} v_i
$$

The model can choose which earlier depth representations matter now.

This mirrors the KDA story:

```text
KDA: learned selection over sequence memory
AttnRes: learned selection over depth memory
MoE: learned selection over parameter capacity
```

## 12 The Mental Model I Want to Remember

GPT-style full attention is powerful because it keeps explicit access to history. But long context makes the memory cost painful.

Linear attention compresses history, but compressed memory interferes.

DeltaNet makes the memory editable.

Gated DeltaNet makes the memory forgettable.

KDA makes forgetting fine-grained.

Kimi Linear mixes KDA with periodic global attention.

Kimi K3 scales that idea with MoE, AttnRes, quantization, and native multimodality.

The one-liner:

> Kimi K3 is not only larger; it spends memory, compute, and parameters more selectively.

## References

1. [Waterloo Intern thread](https://x.com/waterloo_intern/status/2081762065392541951)
2. [Kimi Linear: An Expressive, Efficient Attention Architecture](https://arxiv.org/abs/2510.26692)
3. [Kimi K3 official repository](https://github.com/MoonshotAI/Kimi-K3)
4. [Attention Residuals](https://arxiv.org/abs/2603.15031)
