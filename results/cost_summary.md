# Estimated monthly AKS cost (USD, list prices accessed 2026-11-17)

|                     |   Baseline (Free, 1 node) |   Hardened (Standard, 3 nodes) |   Difference |
|:--------------------|--------------------------:|-------------------------------:|-------------:|
| Control plane       |                      0    |                          73    |        73    |
| Compute (B2s nodes) |                     35.04 |                         105.12 |        70.08 |
| OS disks (E10)      |                      9.6  |                          28.8  |        19.2  |
| Public IP           |                      3.65 |                           3.65 |         0    |
| Total               |                     48.29 |                         210.57 |       162.28 |

# E3: requested CPU per load burst (one run = 180 s load + 180 s idle)

| variant   |    mean |     std |   cpu_request_vcpu_h_per_run |   usd_per_run |   usd_per_month_1_burst_per_hour |
|:----------|--------:|--------:|-----------------------------:|--------------:|---------------------------------:|
| hpa50     | 2089.77 | 145.553 |                      0.05805 |       0.00139 |                          1.01702 |
| hpa80     | 1322.83 |  98.5   |                      0.03675 |       0.00088 |                          0.64378 |
