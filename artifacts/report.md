# Alarm Triage Co-Pilot - model report

Dataset: **PhysioNet/CinC Challenge 2015 training set**  
Trained: 2026-10-11T06:51:43+00:00  
Train / held-out test alarms: 599 / 151  
'Likely artifact' cut-off: p(true) < 0.010 (chosen in cross-validation so <= 1.0% of true alarms fall below it)

## Held-out test set (never seen in training)

| Alarm | n | true / false | AUC | false alarms flagged 'likely artifact' | TRUE alarms flagged 'likely artifact' | sens @0.5 | spec @0.5 | challenge score |
|---|---|---|---|---|---|---|---|---|
| All alarms | 151 | 58 / 93 | 0.960 | 56 (60.2%) | 0 (0.0%) | 0.83 | 0.95 | 0.712 |
| Asystole | 25 | 4 / 21 | 0.964 | 14 (66.7%) | 0 (0.0%) | 0.75 | 0.95 | 0.793 |
| Extreme brady | 18 | 9 / 9 | 0.975 | 4 (44.4%) | 0 (0.0%) | 0.89 | 0.89 | 0.727 |
| Extreme tachy | 28 | 26 / 2 | 0.923 | 0 (0.0%) | 0 (0.0%) | 1.00 | 0.50 | 0.964 |
| V-tach | 68 | 18 / 50 | 0.928 | 33 (66.0%) | 0 (0.0%) | 0.56 | 0.98 | 0.590 |
| V-fib / flutter | 12 | 1 / 11 | 1.000 | 5 (45.5%) | 0 (0.0%) | 1.00 | 0.91 | 0.917 |

## Cross-validation (training 80%)

| Alarm | n | true / false | AUC | false alarms flagged 'likely artifact' | TRUE alarms flagged 'likely artifact' | sens @0.5 | spec @0.5 | challenge score |
|---|---|---|---|---|---|---|---|---|
| All alarms | 599 | 236 / 363 | 0.960 | 190 (52.3%) | 2 (0.8%) | 0.89 | 0.91 | 0.767 |
| Asystole | 97 | 18 / 79 | 0.953 | 44 (55.7%) | 0 (0.0%) | 0.89 | 0.92 | 0.848 |
| Extreme brady | 71 | 37 / 34 | 0.972 | 15 (44.1%) | 1 (2.7%) | 0.92 | 0.91 | 0.783 |
| Extreme tachy | 112 | 105 / 7 | 0.997 | 0 (0.0%) | 0 (0.0%) | 1.00 | 0.57 | 0.973 |
| V-tach | 273 | 71 / 202 | 0.922 | 110 (54.5%) | 1 (1.4%) | 0.75 | 0.90 | 0.681 |
| V-fib / flutter | 46 | 5 / 41 | 0.751 | 21 (51.2%) | 0 (0.0%) | 0.40 | 0.95 | 0.707 |

## What the model relies on (permutation importance, held-out set)

- `type_Tachycardia`: 0.0880
- `ecg_b_bas`: 0.0153
- `ecg_a_hr_late`: 0.0075
- `ecg_a_vf_frac_late`: 0.0075
- `ecg_min_max_gap`: 0.0071
- `ecg_a_min_hr5`: 0.0069
- `abp_rr_cv`: 0.0060
- `ecg_a_tsqi`: 0.0051
- `ecg_a_dom_freq`: 0.0029
- `ecg_b_max_gap`: 0.0025
- `ecg_b_dom_freq`: 0.0021
- `ecg_a_amp`: 0.0021
- `ecg_leads_match`: 0.0018
- `ecg_min_vf_frac_late`: 0.0018
- `ecg_b_vf_frac`: 0.0017

Data: PhysioNet/CinC Challenge 2015 (ODC-By 1.0). Clifford GD et al., CinC 2015;42:273-276.
