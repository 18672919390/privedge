"""Main experiment catalog; output names preserve historical evidence."""
GROUPS = {
    "G1": ("competitive_baselines", "G1_competitive_baselines.py", "formal_baseline_comparison"),
    "G2": ("protocol_baselines", "G2_protocol_baselines.py", "G1_protocol_baselines"),
    "G3": ("context_quality", "G3_context_quality.py", "G2_context_quality"),
    "G4": ("heterogeneous", "G4_heterogeneous.py", "G4_heterogeneous"),
    "G5": ("context_robustness", "G5_context_robustness.py", "G5_context_robustness"),
    "G6": ("source_robustness", "G6_source_robustness.py", "G6_source_robustness"),
    "G7": ("candidate_release", "G7_candidate_release.py", "G7_candidate_release"),
    "G8": ("parameter_sensitivity", "G8_parameter_sensitivity.py", "G8_parameter_sensitivity"),
}
