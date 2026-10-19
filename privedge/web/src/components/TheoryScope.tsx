/** Shared, reviewable scope for the two statistical guarantees; no performance claim. */
export function TheoryScope() {
  return <details className="theory-scope">
    <summary>定理的适用前提与局限</summary>
    <p><strong>来源与支持规则：</strong>n 为通过准入的不同来源数，f 为其中被攻破的来源数。注册表绑定来源与角色，每源只准入一份摘要。定理 1 保证每个输出类别至少有 t−f 个诚实来源支持；f &lt; t 时，任何诚实来源都未发布的类别不能进入输出。不保证已有类别名次不变。</p>
    <p><strong>定理 2 的前提：</strong>仅适用于无上下文融合；n≥3 且 f &lt; (n−1)/2，保证留出任意来源后仍有诚实严格多数。摘要须非空、类别不重复、频率有限、方差正且有限，诚实源发布频率非负；原始权重正且有限，权重封顶系数 κ≥1，截尾下限为 0。公开上下文分支不在该证明范围内。</p>
    <p><strong>影响界的含义：</strong>只约束当前这组输入下的恶意权重份额和融合分数，不是与无攻击输出的差距保证，不保证 Top-k 稳定或预测准确。诚实源最小、最大原始权重记为 w、W；α≤fκW/((n−f)w+fκW)。α≤2/11≈0.18 的示例要求 n=10、f=1、κ=2 且 W=w；诚实源权重相近时才可作相近权重的近似解释，相同样本量不能单独推出这一条件。</p>
  </details>;
}
