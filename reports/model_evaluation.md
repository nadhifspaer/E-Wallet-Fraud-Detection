# Model Evaluation

Single LightGBM classifier on PaySim transactions. Temporal split by `step`: train on steps up to 594, test on steps 595 to 743. All metrics below are computed on the test split only. Hyperparameters and seed are fixed in `src/config.py` (300 trees, learning rate 0.05, 63 leaves, `class_weight="balanced"`, seed 42), with no tuning and no early stopping.

## Data analysis

Numbers come from `reports/eda_numbers.json`. Figures are in `reports/figures/`.

**Size and labels.** The file has 6,362,620 rows over steps 1 to 743 (24 steps per day) and 8,213 fraud rows (rate 0.129%).

**Fraud by type** (`fraud_by_type.png`).

| Type | Rows | Fraud | Fraud rate |
|---|---|---|---|
| CASH_IN | 1,399,284 | 0 | 0% |
| CASH_OUT | 2,237,500 | 4,116 | 0.184% |
| DEBIT | 41,432 | 0 | 0% |
| PAYMENT | 2,151,495 | 0 | 0% |
| TRANSFER | 532,909 | 4,097 | 0.769% |

All fraud rows are TRANSFER or CASH_OUT. No row with `nameDest` starting with `M` (2,151,495 rows) is fraud.

**Balance evidence** (`balance_evidence_by_label.png`), over TRANSFER and CASH_OUT rows (2,762,196 legitimate, 8,213 fraud), tolerance 0.01.

| Check | Legitimate | Fraud |
|---|---|---|
| Sender identity (`newbalanceOrig == oldbalanceOrg - amount`) | 9.49% | 99.45% |
| Receiver identity (`newbalanceDest == oldbalanceDest + amount`) | 77.42% | 43.50% |
| Both identities | 7.58% | 43.27% |
| Exact drain (`amount == oldbalanceOrg`) | 0.00004% (1 row) | 97.82% (8,034 rows) |
| `newbalanceOrig == 0` | 90.10% | 98.05% |
| `oldbalanceDest == 0` and `newbalanceDest == 0` | 0.062% | 49.63% |

**Legacy flag.** `isFlaggedFraud` marks 16 rows, all fraud (precision 100%, recall 0.195%, 8,197 fraud rows unflagged). It is not used as a feature.

**Time** (`fraud_per_step.png`, `fraud_rate_by_hour.png`). The train side (steps 1 to 594) has 6,239,040 rows and 6,559 fraud rows (0.105%). The test side (steps 595 to 743) has 123,580 rows and 1,654 fraud rows (1.338%).

**Amount** (`amount_by_label.png`). The distribution by label is shown on a log scale. Median legitimate amount in the test split is 162,603.89 for TRANSFER and CASH_OUT rows and 66,393.21 for all rows.

**Account repetition.** `nameOrig` has 6,353,307 unique values over 6,362,620 rows, and 0.29% of rows share their key with another row. `nameDest` has 2,722,362 unique values, and 64.44% of rows share their key. No account-level velocity feature is built.

## Ablation

Five additive variants, trained with the same split, hyperparameters, and seed. Test PR-AUC per variant. Variant 5 uses `newbalanceOrig` and `newbalanceDest`, which are outside the final feature list, and exists for measurement only.

| Variant | Features added | PR-AUC, TRANSFER and CASH_OUT | PR-AUC, all rows |
|---|---|---|---|
| 1 | `amount`, `hour_of_day` | 0.4035 | 0.3715 |
| 2 | type one-hot columns | 0.5036 | 0.5036 |
| 3 | `oldbalanceOrg`, `oldbalanceDest` | 0.9768 | 0.9768 |
| 4 | `orig_drain_ratio` (final feature list) | 0.9809 | 0.9807 |
| 5 | `newbalanceOrig`, `newbalanceDest` (measurement only) | 0.9972 | 0.9972 |

![Test PR-AUC by ablation variant](figures/ablation_pr_auc.png)

Variant 3 adds both old balance columns together, so the table does not separate their individual effects.

Adding the old balance columns raises PR-AUC by 0.4732 (TRANSFER and CASH_OUT). Adding the drain ratio raises it by 0.0041. Adding the new balance columns to the final feature list raises it by a further 0.0163. The new balance columns stay out of the final feature list.

## Metrics

Test split, final feature list. PR-AUC is the primary metric, computed with `sklearn.metrics.average_precision_score`. K values are 100, 500, 1,000, the number of test fraud rows, and 0.1% and 0.5% of the population size. Precision@K is skipped for K above the number of test fraud rows (1,654).

### TRANSFER and CASH_OUT rows

51,286 rows, 1,654 fraud rows, prevalence 3.225%. PR-AUC 0.9809.

| K | Precision@K | Recall@K |
|---|---|---|
| 51 | 1.0000 | 0.0308 |
| 100 | 1.0000 | 0.0605 |
| 256 | 1.0000 | 0.1548 |
| 500 | 1.0000 | 0.3023 |
| 1,000 | 0.9980 | 0.6034 |
| 1,654 | 0.9601 | 0.9601 |

| Target recall | Threshold | Flagged | True positives | False positives | FPR |
|---|---|---|---|---|---|
| 80% | 0.99976 | 1,328 | 1,324 | 4 | 0.0081% |
| 90% | 0.98794 | 1,523 | 1,489 | 34 | 0.0685% |

Cost at the threshold that reaches each target recall. Missed loss is the sum of `amount` over missed fraud rows. Friction is the number of false positives times the friction value. All values are in the units of the `amount` column.

| Target recall | Missed loss | Prevented loss | Friction at 0.1x (1,000 per FP) | Friction at 1x (10,000 per FP) | Friction at 10x (100,000 per FP) |
|---|---|---|---|---|---|
| 80% | 53,652,378 | 2,668,782,191 | 4,000 | 40,000 | 400,000 |
| 90% | 24,564,265 | 2,697,870,304 | 34,000 | 340,000 | 3,400,000 |

Total cost (missed loss plus friction):

| Target recall | 0.1x | 1x | 10x |
|---|---|---|---|
| 80% | 53,656,378 | 53,692,378 | 54,052,378 |
| 90% | 24,598,265 | 24,904,265 | 27,964,265 |

### All rows

123,580 rows, 1,654 fraud rows, prevalence 1.338%. PR-AUC 0.9807.

| K | Precision@K | Recall@K |
|---|---|---|
| 100 | 1.0000 | 0.0605 |
| 124 | 1.0000 | 0.0750 |
| 500 | 1.0000 | 0.3023 |
| 618 | 1.0000 | 0.3736 |
| 1,000 | 0.9980 | 0.6034 |
| 1,654 | 0.9601 | 0.9601 |

| Target recall | Threshold | Flagged | True positives | False positives | FPR |
|---|---|---|---|---|---|
| 80% | 0.99976 | 1,328 | 1,324 | 4 | 0.0033% |
| 90% | 0.98794 | 1,523 | 1,489 | 34 | 0.0279% |

The flagged sets, and therefore the cost values, are identical to the TRANSFER and CASH_OUT population. The cost tables above apply to both populations. The FPR differs because the legitimate row count in the denominator differs.

## Assumptions

- **Prevalence shift.** Fraud prevalence is 0.105% in the train split and 1.338% in the test split (3.225% among TRANSFER and CASH_OUT test rows). PR-AUC and Precision@K depend on prevalence, so they are not comparable with figures from the full dataset or from a random split.
- **Exact balance drain.** In this data, 97.82% of fraud rows in TRANSFER and CASH_OUT have `amount == oldbalanceOrg`, against 1 legitimate row. This is a regularity of the simulated data. Legitimate full withdrawals exist in production, so the strength of this signal and the PR-AUC reached with it should not be expected to transfer.
- **Balance columns.** The old balance columns and the drain ratio are in the final feature list because the ablation shows a measured gain. The new balance columns are excluded. `newbalanceOrig` and `newbalanceDest` are recorded after the transaction executes, so they are not available when a transaction is scored. This is why they are excluded even though they raise PR-AUC to 0.9972. The test metrics reflect how this simulator generates balances.
- **Friction cost.** The cost of one false positive is set to 10,000 in the units of the `amount` column. It is a business assumption that PaySim cannot supply. It equals 6.1% of the median legitimate amount in TRANSFER and CASH_OUT test rows. Sensitivity is reported at 0.1x (1,000) and 10x (100,000).
- **Cost threshold.** Cost is computed at the lowest score threshold that reaches the target recall (80% or 90%) on the test split, flagging every row with a score at or above it. The loss per missed fraud row is its transaction amount. Prevented loss is the amount of fraud rows flagged. The threshold is chosen using test labels, so it describes the achievable operating point and is not a deployed threshold.
- **Target recall and K values.** The recall targets (80%, 90%) and the K values are review-capacity assumptions, not derived from the data.
- **Single split and seed.** All results come from one temporal split and one seed. No confidence intervals are computed.
