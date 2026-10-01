# Censor-aware item-level fusion

For the second-stage derivation, precise joint-selection likelihood distinction,
and a separate convex simplex estimator, see [CENSOR_ESTIMATOR_V2.md](CENSOR_ESTIMATOR_V2.md).
The implementation described below remains the legacy comparator. A random
top-m threshold alone does not invalidate a joint observation likelihood under
independent continuous known-noise assumptions; those assumptions do not hold
automatically for the current LDP/transfer pipeline.

## Observation model

Source server `s` publishes the `m` largest LDP frequency estimates. Let
`y[s,i]` and `v[s,i]` denote a published estimate and its plug-in variance,
and let `tau[s]` be the smallest published estimate. For a candidate item that
is absent from source `s`, the available observation is the selection event

```text
Y[s,i] <= tau[s]
```

instead of a frequency equal to zero. Conditional on the observed threshold,
the implementation uses the Gaussian approximation

```text
Y[s,i] | theta[i] ~ Normal(theta[i], effective_variance[s,i]).
```

The threshold is a random top-m order statistic. Treating it as fixed after it
has been observed gives a tractable conditional approximation, not an exact
Tobit likelihood.

## Per-item objective

For each item in the selected releases' candidate union, the method minimizes

```text
L_i(theta) =
    prior_strength / (2 * context_scale^2) * (theta - q[i])^2
  + sum(reported s) w[s] * (theta - y[s,i])^2 / (2 * V[s,i])
  - sum(unreported s) w[s] * log Phi((tau[s] - theta) / sqrt(V[s,i])).
```

Here `q` is normalized public target context and `Phi` is the standard-normal
CDF. The last term is the censoring correction. It penalizes a candidate that
has a high score despite being absent from several source top-m lists, without
incorrectly setting every absence to zero.

`V[s,i]` adds a transfer component to the published LDP variance. The transfer
component grows when the source ranking agrees poorly with public context.
Source weights combine context agreement and release uncertainty, with a
median variance floor and utility clipping to limit unstable plug-in weights.
The scalar convex objective is minimized on `[0, 1]` by a deterministic
golden-section search, so SciPy is not required.

## Variants and information boundary

- `censor_aware_item_context` uses every available source.
- `adaptive_censor_aware_item_context` first selects the configured number of
  sources using only public context, released lists, and released variances.
- With no public target context, both methods fall back to `average`; no hidden
  target information is injected.
- The release threshold is derived from already published LDP estimates. This
  is post-processing and consumes no additional privacy budget.

The implementation never uses the hidden target distribution or the synthetic
true source-target similarities. Those values remain evaluation-only.

## Current limitations

- Normality is an approximation whose accuracy depends on the LDP estimator
  and source sample size.
- The random top-m threshold and dependencies among selected items are not
  modeled exactly.
- Public context is treated as a quadratic prior; misspecified context can
  still hurt ranking quality.
- The transfer-variance formula and its fixed hyperparameters require broader
  sensitivity analysis before publication claims.
