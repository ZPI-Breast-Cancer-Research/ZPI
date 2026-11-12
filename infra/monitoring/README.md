# Training machine monitoring

Prometheus and Grafana for the machine that trains models: GPU, system and nnU-Net progress.

**This is a development tool, not part of the MARIA system.** It has its own Compose file and the
main `docker-compose.yml` does not change. Running it in a hospital would be a new part of the
system: that needs an ADR, an update of `docs/ARCHITECTURE.md`, and a check that no patient data
reaches metric labels.

```
GPU             → gpu-exporter ─────────┐
CPU, RAM, disk  → node-exporter ────────┼→ Prometheus → Grafana
nnU-Net log     → nnunet_metrics.py ────┘
                  (file read by node-exporter)
```

## Requirements

Docker with Compose, the NVIDIA driver and the NVIDIA Container Toolkit. Check with:

```bash
docker run --rm --gpus all ubuntu nvidia-smi
```

## Run

On the training machine, from `infra/monitoring`:

```bash
cp .env.example .env              # set GRAFANA_ADMIN_PASSWORD
docker compose up -d
```

From the repo root, next to the training (for example in a `tmux` window). It needs
`nnUNet_results`, or `--results <path>`:

```bash
python3 infra/monitoring/exporters/nnunet_metrics.py
```

All ports listen on `127.0.0.1` only. To open them from another computer:

```bash
ssh -L 3000:localhost:3000 -L 9090:localhost:9090 user@training-machine
```

- Grafana: <http://localhost:3000>, user `admin`, dashboard **ZPI training**
- Prometheus: <http://localhost:9090>, alerts under *Alerts*

Stop with `docker compose down`. Add `-v` to also delete the stored metrics.

## Metrics from training

| Metric | Meaning |
|---|---|
| `nnunet_running` | 1 while an `nnUNetv2_train` process exists |
| `nnunet_epoch` | last finished epoch |
| `nnunet_train_loss`, `nnunet_val_loss` | losses of that epoch |
| `nnunet_pseudo_dice` | pseudo Dice on patches, not the final validation Dice |
| `nnunet_pseudo_dice_ema` | its moving average, as nnU-Net computes it to pick `checkpoint_best.pth` |
| `nnunet_epoch_seconds` | time of that epoch |
| `nnunet_last_epoch_timestamp_seconds` | when that epoch finished |

The script reads the newest training log under `nnUNet_results` and does not affect the training.
Metrics appear after the first finished epoch. MLflow stays the place to compare experiments (#55);
this answers whether the machine and the training are healthy now.

## Alerts

`alerts.yml` has rules for a silent exporter, GPU temperature, GPU memory, disk space, a stalled
training and a stale metrics file. They are only visible in Prometheus: no Alertmanager is
configured, so nothing sends a notification.

## Tests

```bash
cd infra/monitoring/exporters && python3 -m pytest test_nnunet_metrics.py -p no:cacheprovider
```

## Try it without a GPU

The GPU exporter has a demo mode with synthetic data. Create an untracked
`docker-compose.override.yml`:

```yaml
services:
  gpu-exporter:
    gpus: !reset []
    command: ["--collect.backend", "demo"]
```
