---
title: "DSpark and DFlash: 10 Notes on Speculative Decoding"
mathjax: true
toc: true
categories:
  - Study
tags:
  - LLM
  - Inference
  - Speculative Decoding
---

I read Dmytro Dzhulgakov's [DSpark thread](https://x.com/dzhulgakov/status/2070922887595499930) and the related papers, and here is my learning note.

The short version:

```text
DFlash = parallel block drafting
DSpark = DFlash-style parallel drafting + cheap sequential correction + smarter verification
```

Both are trying to solve the same serving problem: large autoregressive models generate one token per full forward pass. Speculative decoding lets a cheap drafter guess multiple future tokens, then asks the large target model to verify them in one parallel pass.

The output distribution can stay identical to normal decoding, but the latency can drop a lot when the drafted tokens are accepted.

## 1 Batching Is the Hardware Trick

LLM decoding is often limited less by raw FLOPs and more by moving model weights from GPU memory into compute units.

That means:

```text
decode 1 token  -> load the model weights
decode 10 tokens in a batch -> load mostly the same weights
```

The second case is not 10x slower. This is why batching helps so much.

Speculative decoding uses the same trick inside a single request. Instead of forcing the large model to generate future tokens one by one, a small model proposes several tokens and the large model verifies them as a batch.

## 2 Speculative Decoding

Normal autoregressive decoding:

```text
target model -> token 1
target model -> token 2
target model -> token 3
```

Speculative decoding:

```text
draft model proposes: token 1, token 2, token 3
target model verifies all three in one pass
accepted prefix is kept
first rejected token is corrected by the target model
```

The verifier only accepts the longest prefix that is consistent with the target model. If token 1 and token 2 are accepted but token 3 is rejected, tokens after token 3 are discarded.

So the core metric is **accepted length**:

```text
how many drafted tokens survive each verify step?
```

## 3 Draft Model

The drafter can be a smaller LLM trained on the same distribution. For example, a small Qwen model could draft for a much larger Qwen target.

This is easy to understand, but it is not always efficient enough:

1. A separate small model still has real latency.
2. It may not match the target model well.
3. It may require separate serving infrastructure.

The goal is to make the drafter both cheap and accurate.

## 4 Speculation Is Not Free

Speculative decoding is only useful if the draft cost is low and acceptance is high.

A useful equation:

$$
\text{time per token}
=
\frac{\text{draft time} + \text{verify time}}{\text{accepted tokens}}
$$

If the drafter is slow, the numerator grows.

If the drafter guesses badly, the denominator shrinks.

If the system verifies too many doomed suffix tokens, verification wastes batch capacity.

This is the main engineering tension:

```text
draft more tokens -> more possible speedup
draft too many bad tokens -> wasted work
```

## 5 EAGLE and MTP

EAGLE and Multi-Token Prediction (MTP) improve the drafter by attaching lightweight prediction modules to the target model's hidden states.

Instead of asking an entirely separate model to guess, the drafter consumes rich latent information from the large model.

That makes the draft module:

1. Smaller than a standalone LLM.
2. Better aligned with the target model.
3. Often faster and more accurate.

But autoregressive drafters still have a bottleneck:

```text
to draft N tokens, run N sequential draft steps
```

That is better than N target-model steps, but still sequential.

## 6 DFlash

DFlash attacks the sequential draft bottleneck.

It uses a lightweight block diffusion drafter to generate a whole block in one forward pass. The drafter is conditioned on target-model context features, then predicts multiple future tokens in parallel.

The benefit:

```text
one draft pass -> many draft tokens
```

The DFlash paper reports strong speedups, including over 6x lossless acceleration across tested models and tasks, with up to 2.5x higher speedup than EAGLE-3 in their experiments.

The downside is that fully parallel prediction weakens dependency between positions inside the drafted block.

Example:

```text
valid continuation A: "of course"
valid continuation B: "no problem"

parallel drafter can accidentally mix modes:
"of problem"
"no course"
```

This is called suffix decay. Early draft positions can be good, but later positions are more likely to be rejected.

## 7 DSpark

DSpark keeps the fast parallel block idea, but adds a cheap sequential correction.

The paper describes DSpark as semi-autoregressive:

```text
parallel backbone -> base logits for the whole block
sequential head -> adjusts each token based on previous drafted tokens
```

So DSpark does not give up DFlash's main advantage. The expensive part remains parallel.

The sequential part is deliberately small. The paper describes Markov and RNN variants. The Markov head can be low-rank, so it adds local token-to-token information without running a full Transformer step per drafted position.

This fixes the core DFlash issue:

```text
DFlash knows the context well
DSpark also knows what it already sampled inside the block
```

## 8 Cheaper Sequential Block

EAGLE/MTP-style autoregressive drafting may run attention at every draft position.

DSpark's sequential head is much cheaper because the heavy contextual work is already done by the parallel backbone.

A rough mental model:

```text
DFlash backbone:
  "Given the target context, what are plausible tokens at each position?"

Markov/RNN head:
  "Given the previous sampled draft token, which next token now makes sense?"
```

That small second question is enough to remove many incoherent suffixes.

This is the important system-design move:

```text
do the expensive context modeling once in parallel
do only cheap local dependency modeling sequentially
```

## 9 Variable-Length Drafting and Hardware-Aware Scheduling

How many tokens should the system verify?

There is no single right answer.

Some tasks are easier to predict:

```text
code completion -> often more deterministic
open-ended chat -> often more uncertain
```

The best answer also depends on server load:

```text
low load -> verify more speculative tokens, because GPU capacity is available
high load -> verify fewer risky tokens, because batch slots are precious
```

DSpark adds a confidence head to estimate the probability that each prefix survives verification. Then a hardware-aware scheduler chooses how many draft tokens to verify for each request.

This is the serving-system part of DSpark. It is not just a better model head; it is also a better policy for spending verification budget.

## 10 Online Drafter Calibration

Confidence scores are only useful if they match reality.

Neural networks are often overconfident. A drafter might say "I am 90% sure" when the real acceptance rate is much lower. If the scheduler trusts raw confidence too much, it will verify too many doomed suffix tokens.

DSpark calibrates confidence using runtime behavior.

The idea:

```text
observe actual accepted lengths
compare them to predicted prefix survival probabilities
adjust thresholds/calibration online
```

Over time, the system can become more tolerant for workloads with high acceptance, such as code, and more conservative for workloads with lower acceptance, such as open-ended chat.

## DFlash vs DSpark

Here is the clean comparison I want to remember.

| Dimension | DFlash | DSpark |
|---|---|---|
| Draft style | Fully parallel block drafting | Semi-autoregressive block drafting |
| Main trick | Generate many draft tokens in one forward pass | Generate in parallel, then add cheap sequential dependency |
| Strength | Very fast drafter | Better accepted length and less verification waste |
| Weakness | Later positions can suffer suffix decay | More moving parts: sequential head, confidence head, scheduler |
| Dependency inside block | Weak, because positions are predicted in parallel | Stronger, because each position can depend on previous sampled draft tokens |
| Verification length | Usually fixed or statically chosen | Dynamic and hardware-aware |
| Best use case | Simple fast acceleration with a parallel drafter | Production serving where load, request type, and acceptance rate vary |

Another way:

```text
DFlash optimizes draft latency.
DSpark optimizes draft latency + accepted length + verification budget.
```

The DSpark paper reports that, on Qwen3 4B/8B/14B targets, DSpark improves macro-average accepted length over DFlash by roughly 16% to 18%. On DeepSeek-V4 serving, it reports 60% to 85% per-user generation speedup on V4-Flash and 57% to 78% on V4-Pro compared with their MTP-1 production baseline at matched throughput.

## Why This Matters

The most interesting part is not that any single component is brand new.

The interesting part is the integration:

```text
parallel drafter
+ cheap local dependency model
+ confidence prediction
+ hardware-aware verification scheduler
+ online calibration
= adaptive speculative decoding system
```

This is model and system co-design. The model predicts not only tokens, but also how useful its own guesses are likely to be. The serving system then decides how much GPU work those guesses deserve.

That is the deeper pattern:

```text
not just "make the model smaller"
but "make the whole decode loop spend compute where it has positive expected value"
```

## References

1. [Dmytro Dzhulgakov DSpark thread](https://x.com/dzhulgakov/status/2070922887595499930)
2. [DSpark: Confidence-Scheduled Speculative Decoding with Semi-Autoregressive Generation](https://arxiv.org/abs/2607.05147)
3. [DeepSpec repository](https://github.com/deepseek-ai/DeepSpec)
4. [DFlash: Block Diffusion for Flash Speculative Decoding](https://arxiv.org/abs/2602.06036)
5. [DFlash repository](https://github.com/z-lab/dflash)
