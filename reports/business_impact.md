# Business Impact

This report turns the test results into money terms: how much fraud is stopped, how much is missed, and what false alarms cost. Every number comes from `reports/model_evaluation.md`, `reports/metrics.json`, or simple arithmetic on those values. The test part covers steps 595 to 743 (123,580 rows, 1,654 fraud). All amounts use the same units as the `amount` column.

## Two settings

The model gives every transaction a score. A score cutoff decides which transactions are flagged. The two settings below use the lowest cutoff that finds 80% and 90% of all fraud.

| Item | 80% of fraud found | 90% of fraud found |
|---|---|---|
| Score cutoff | 0.99976 | 0.98794 |
| Flagged rows | 1,328 | 1,523 |
| Share of test rows flagged | 1.07% | 1.23% |
| Fraud found | 1,324 | 1,489 |
| False alarms | 4 | 34 |
| False alarm rate (all rows) | 0.0033% | 0.0279% |
| Precision (flagged rows that are fraud) | 99.70% | 97.77% |

## Loss and cost

The total fraud amount in the test part is 2,722,434,569 (prevented loss plus missed loss).

| Item | 80% of fraud found | 90% of fraud found |
|---|---|---|
| Prevented loss | 2,668,782,191 | 2,697,870,304 |
| Share of fraud amount prevented | 98.03% | 99.10% |
| Missed loss | 53,652,378 | 24,564,265 |
| False alarm cost at 1,000 each | 4,000 | 34,000 |
| False alarm cost at 10,000 each | 40,000 | 340,000 |
| False alarm cost at 100,000 each | 400,000 | 3,400,000 |
| Total cost at 10,000 each | 53,692,378 | 24,904,265 |

Going from the 80% setting to the 90% setting:

- Finds 165 more fraud rows.
- Adds 30 false alarms.
- Lowers missed loss by 29,088,113.
- Adds 300,000 of false alarm cost (at 10,000 each).
- Has the lower total cost at all three false alarm costs (at 100,000 each: 27,964,265 against 54,052,378).

## Review capacity

If a team can review only a fixed number of cases, the ranking still works well.

- **Precision@K:** 1.0000 up to K = 500, 0.9980 at K = 1,000, and 0.9601 at K = 1,654 (all test fraud).
- **Recall@K:** 0.3023 at K = 500 and 0.6034 at K = 1,000.

## Assumptions and limits

- **Cost of a false alarm.** It is set to 10,000, with 1,000 and 100,000 as other cases. PaySim has no data on what it costs to block a good customer, so this is an assumption. It is 6.1% of the median legitimate amount in TRANSFER and CASH_OUT test rows.
- **Loss from a missed fraud.** It is the transaction amount. Recovery, refunds, and other later losses are not included.
- **Prevented loss.** It is the amount of the fraud rows that were flagged. It assumes a flagged transaction is stopped before it is completed.
- **Score cutoff.** It is chosen using the test labels. It shows what is possible and is not a cutoff for real use. A real cutoff must be set on separate data.
- **Recall targets.** The 80% and 90% targets are assumptions about review capacity. They do not come from the data.
- **Both groups.** The number of flagged rows and false alarms is the same for TRANSFER and CASH_OUT rows and for all rows. Only the false alarm rate differs, because the number of legitimate rows differs.
- **Different fraud share.** Fraud is 0.105% in the train part and 1.338% in the test part. False alarm counts and precision change with this share, so they do not carry over to data with a different fraud rate.
- **A pattern of the simulator.** In this data, 97.82% of fraud rows in TRANSFER and CASH_OUT empty the sender balance, against 1 legitimate row. Real traffic has legitimate full withdrawals, so a real system may see more false alarms than shown here.
- **Scores.** Scores are model outputs, not true probabilities.
- **One split, one seed.** No confidence ranges are computed.